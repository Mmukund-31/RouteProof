"""Read-only client POD-view links.

A billing executive shares delivery evidence with one client: either an explicit list of that client's trips or one
billing cycle. The link holder can see trip reference, LR, delivery date, POD status and the *verified* POD image -
nothing else (no driver, phone, freight, GPS or other clients' trips). Tokens are random, stored only as a SHA-256
hash, expire, can be revoked, and every creation, access and revocation is audited.

This is intentionally a different table and URL space from hired-driver upload links: those may write one POD for one
trip; these may only read. A token of one kind can never be resolved as the other.
"""
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, BadRequest, NotFound
from app.core.security import hash_token, new_link_token
from app.models import Client, ClientViewLink, Pod, Trip, aware, utcnow
from app.services.audit import audit
from app.services.billing.eligibility import pod_reference


def create_link(db: Session, user_id, *, client_id: uuid.UUID, trip_ids: list[uuid.UUID] | None, billing_cycle: str | None,
                expires_in_days: int, label: str | None) -> tuple[ClientViewLink, str]:
    s = get_settings()
    client = db.get(Client, client_id)
    if not client:
        raise NotFound("Client")
    if bool(trip_ids) == bool(billing_cycle):
        raise BadRequest("invalid_scope", "Choose either a list of trips or one billing cycle")
    if not 1 <= expires_in_days <= s.client_link_max_days:
        raise BadRequest("invalid_expiry", f"Expiry must be between 1 and {s.client_link_max_days} days")
    if trip_ids:
        ids = list(dict.fromkeys(trip_ids))
        trips = list(db.scalars(select(Trip).where(Trip.id.in_(ids))).unique())
        if len(trips) != len(ids):
            raise NotFound("One or more trips")
        foreign = [t.trip_reference for t in trips if t.client_id != client.id]
        if foreign:  # a link must never reveal another client's trips
            raise BadRequest("trip_not_for_client", "Some trips belong to a different client", {"trips": foreign})
    token = new_link_token()
    link = ClientViewLink(token_hash=hash_token(token), client_id=client.id, scope_type="trips" if trip_ids else "billing_cycle",
                          trip_ids=[str(t) for t in dict.fromkeys(trip_ids)] if trip_ids else None,
                          billing_cycle=billing_cycle, label=(label or "").strip() or None, created_by=user_id,
                          expires_at=utcnow() + timedelta(days=expires_in_days))
    db.add(link)
    db.flush()
    audit(db, user_id, "client_link", link.id, "client_link.created", None,
          {"client": client.client_code, "scope": link.scope_type, "trips": len(link.trip_ids or []), "billing_cycle": billing_cycle,
           "expires_at": link.expires_at.isoformat()})
    db.commit()
    return link, token  # the raw token exists only in this response


def revoke_link(db: Session, user_id, link: ClientViewLink) -> ClientViewLink:
    if link.revoked_at is None:
        link.revoked_at, link.revoked_by = utcnow(), user_id
        audit(db, user_id, "client_link", link.id, "client_link.revoked", {"revoked": False}, {"revoked": True})
        db.commit()
    return link


def link_state(link: ClientViewLink) -> str:
    if link.revoked_at:
        return "revoked"
    return "expired" if aware(link.expires_at) < utcnow() else "active"


def resolve(db: Session, token: str) -> ClientViewLink:
    link = db.scalar(select(ClientViewLink).where(ClientViewLink.token_hash == hash_token(token)))
    if not link:
        raise NotFound("Link")
    state = link_state(link)
    if state != "active":
        # Attempts after expiry/revocation are recorded too (who keeps trying an old link is worth knowing).
        audit(db, None, "client_link", link.id, "client_link.access_denied", None, None, {"state": state})
        db.commit()
        raise AppError(410, "link_expired", "This link has expired or was withdrawn")
    return link


def scoped_trips(db: Session, link: ClientViewLink) -> list[Trip]:
    """Only the link's own client, always: the client filter applies even to an explicit trip list."""
    q = select(Trip).where(Trip.client_id == link.client_id, Trip.trip_status != "CANCELLED")
    if link.scope_type == "trips":
        q = q.where(Trip.id.in_([uuid.UUID(t) for t in (link.trip_ids or [])]))
    else:
        q = q.where(Trip.billing_cycle == link.billing_cycle)
    return list(db.scalars(q.order_by(Trip.delivery_date.desc().nullslast(), Trip.trip_reference)).unique())


def verified_pod(trip: Trip) -> Pod | None:
    """Clients only ever see evidence that passed verification; drafts, rejected or retaken photos stay internal."""
    last = trip.pods[-1] if trip.pods else None
    return last if last and last.verification_status == "VERIFIED" and not last.images_purged_at else None


def record_access(db: Session, link: ClientViewLink, what: str, trip: Trip | None = None) -> None:
    link.access_count = (link.access_count or 0) + 1
    link.last_accessed_at = utcnow()
    audit(db, None, "client_link", link.id, f"client_link.{what}", None, None,
          {"trip": trip.trip_reference if trip else None, "access_count": link.access_count})
    db.commit()


def view_payload(link: ClientViewLink, trips: list[Trip]) -> dict:
    rows = []
    for t in trips:
        p = verified_pod(t)
        rows.append({
            "trip_id": str(t.id), "trip_reference": t.trip_reference, "lr_number": t.lr_number,
            "delivery_date": t.delivery_date.isoformat() if t.delivery_date else None, "destination": t.destination,
            "pod_status": "VERIFIED" if p else "PENDING",
            "pod_reference": pod_reference(t, p) if p else None,
            "pod_verified_at": aware(p.verified_at).isoformat() if p and p.verified_at else None,
            "has_image": bool(p),
        })
    return {"client": link.client.company_name, "label": link.label, "scope": link.scope_type, "billing_cycle": link.billing_cycle,
            "expires_at": aware(link.expires_at).isoformat(), "trips": rows,
            "note": "Read-only delivery evidence. Only verified proofs of delivery are shown."}


def link_out(link: ClientViewLink) -> dict:
    return {"id": str(link.id), "client": {"id": str(link.client_id), "name": link.client.company_name}, "label": link.label,
            "scope": link.scope_type, "billing_cycle": link.billing_cycle, "trip_count": len(link.trip_ids or []) or None,
            "state": link_state(link), "expires_at": aware(link.expires_at).isoformat(), "created_at": aware(link.created_at).isoformat(),
            "revoked_at": aware(link.revoked_at).isoformat() if link.revoked_at else None, "access_count": link.access_count or 0,
            "last_accessed_at": aware(link.last_accessed_at).isoformat() if link.last_accessed_at else None}
