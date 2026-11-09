from datetime import timedelta

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import load_trip, require_billing
from app.api.v1.trips import parse_dt, read_limited, run_ai
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import AppError, BadRequest, NotFound
from app.core.observability import request_id_var
from app.core.ratelimit import limit
from app.core.security import hash_token, new_link_token
from app.models import DriverLink, Pod, SmsLog, Trip, User, aware, utcnow
from app.schemas.requests import DriverLinkIn
from app.services.audit import audit
from app.services.notifications.sms import get_sms_provider, mask_phone
from app.services.pods.service import attach_original, create_pod, latest_pod

router = APIRouter(prefix="/driver-links", tags=["driver-links"])


@router.post("", status_code=201)
def create_link(body: DriverLinkIn, user: User = Depends(require_billing), db: Session = Depends(get_db)):
    trip = load_trip(db, body.trip_id, user)
    s = get_settings()
    token = new_link_token()
    link = DriverLink(token_hash=hash_token(token), trip_id=trip.id, created_by=user.id, phone_masked=mask_phone(body.phone),
                      expires_at=utcnow() + timedelta(minutes=body.expires_in_minutes or s.upload_link_expiry_minutes))
    db.add(link)
    db.flush()
    sms = get_sms_provider().send(db, body.phone, link.id)
    audit(db, user.id, "driver_link", link.id, "driver_link.created", None,
          {"trip": trip.trip_reference, "expires_at": link.expires_at.isoformat()}, {"sms_provider": sms.provider, "sms_status": sms.status})
    db.commit()
    # The raw token is returned exactly once and never stored; only its SHA-256 hash is persisted.
    return {"id": str(link.id), "url": f"{s.public_app_url.rstrip('/')}/upload/{token}", "expires_at": aware(link.expires_at).isoformat(),
            "sms": {"provider": sms.provider, "status": sms.status, "to": sms.to_masked,
                    "note": "Mock provider: no SMS was actually sent. Share this link manually in the demo."}}


def _link_out(link: DriverLink, sms: list[SmsLog]) -> dict:
    now = utcnow()
    state = "revoked" if link.revoked else "expired" if aware(link.expires_at) < now else "active"
    return {"id": str(link.id), "trip_id": str(link.trip_id), "state": state, "phone_masked": link.phone_masked,
            "created_at": aware(link.created_at).isoformat(), "expires_at": aware(link.expires_at).isoformat(),
            "revoked_at": aware(link.revoked_at).isoformat() if link.revoked_at else None, "use_count": link.use_count,
            "sms_log": [{"to": m.to_masked, "provider": m.provider, "status": m.status, "created_at": aware(m.created_at).isoformat()}
                        for m in sms]}


@router.get("")
def list_links(trip_id: uuid.UUID = Query(...), user: User = Depends(require_billing), db: Session = Depends(get_db)):
    """Links issued for one trip, newest first, with the mock SMS delivery log (the raw token is never retrievable)."""
    trip = load_trip(db, trip_id, user)
    links = db.scalars(select(DriverLink).where(DriverLink.trip_id == trip.id).order_by(DriverLink.created_at.desc())).all()
    logs = db.scalars(select(SmsLog).where(SmsLog.link_id.in_([lk.id for lk in links]))).all() if links else []
    return {"items": [_link_out(lk, [m for m in logs if m.link_id == lk.id]) for lk in links]}


@router.post("/{link_id}/revoke")
def revoke_link(link_id: uuid.UUID, user: User = Depends(require_billing), db: Session = Depends(get_db)):
    link = db.get(DriverLink, link_id)
    if not link:
        raise NotFound("Upload link")
    load_trip(db, link.trip_id, user)
    if not link.revoked:
        link.revoked, link.revoked_at, link.revoked_by = True, utcnow(), user.id
        audit(db, user.id, "driver_link", link.id, "driver_link.revoked", {"revoked": False}, {"revoked": True})
        db.commit()
    return _link_out(link, list(db.scalars(select(SmsLog).where(SmsLog.link_id == link.id))))


def _resolve(db: Session, token: str) -> tuple[DriverLink, Trip]:
    link = db.scalar(select(DriverLink).where(DriverLink.token_hash == hash_token(token)))
    if not link:
        raise NotFound("Upload link")
    if link.revoked or aware(link.expires_at) < utcnow():
        raise AppError(410, "link_expired", "This upload link has expired")
    return link, db.get(Trip, link.trip_id)


def _view(trip: Trip) -> dict:
    p = latest_pod(trip)
    return {"lr_number": trip.lr_number, "trip_reference": trip.trip_reference, "destination": trip.destination,
            "pod_status": p.verification_status if p else "PENDING",
            "retakes_remaining": max(get_settings().max_retake_requests - (p.retake_count if p else 0), 0)}


@router.get("/{token}", dependencies=[Depends(limit("link", 60))])
def get_link(token: str, db: Session = Depends(get_db)):
    link, trip = _resolve(db, token)
    audit(db, None, "driver_link", link.id, "driver_link.opened", None, None, {"trip": trip.trip_reference})
    db.commit()
    return _view(trip)


@router.post("/{token}/pods", dependencies=[Depends(limit("link_upload", 20))])
def link_upload(token: str, background: BackgroundTasks, file: bytes = File(...), captured_at: str | None = Form(None),
                latitude: float | None = Form(None), longitude: float | None = Form(None), accuracy: float | None = Form(None),
                location_status: str | None = Form(None, max_length=20),
                idempotency_key: str | None = Form(None), idem_header: str | None = Header(None, alias="Idempotency-Key"),
                db: Session = Depends(get_db)):
    link, trip = _resolve(db, token)  # token scopes access to exactly this one trip
    key = idempotency_key or idem_header
    if not key or not (8 <= len(key) <= 80):
        raise BadRequest("idempotency_key_required", "Idempotency-Key (8-80 chars) is required")
    if len(file) > get_settings().upload_max_size_bytes:
        raise AppError(413, "file_too_large", "Image too large")
    pod, created = create_pod(db, trip, user_id=None, data=file, idempotency_key=key, captured_at=parse_dt(captured_at),
                              latitude=latitude, longitude=longitude, accuracy=accuracy, location_status=location_status,
                              source="sms_link")
    if created:
        link.use_count += 1
        audit(db, None, "driver_link", link.id, "driver_link.upload", None, {"pod_id": str(pod.id), "attempt": pod.attempt_number})
        db.commit()
        background.add_task(run_ai, pod.id, request_id_var.get())
    mini = {"id": str(pod.id), "verification_status": pod.verification_status, "attempt_number": pod.attempt_number,
            "retakes_remaining": max(get_settings().max_retake_requests - pod.retake_count, 0)}
    return JSONResponse({"created": created, "pod": mini}, status_code=201 if created else 200)


@router.post("/{token}/pods/{pod_id}/original", dependencies=[Depends(limit("link_upload", 20))])
def link_original(token: str, pod_id: uuid.UUID, response: Response, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Full-resolution original for a POD this same link uploaded. A link can never touch another trip's POD."""
    link, trip = _resolve(db, token)
    pod = db.get(Pod, pod_id)
    if not pod or pod.trip_id != trip.id:
        raise NotFound("POD")
    pod, created = attach_original(db, pod, read_limited(file, get_settings().original_max_size_bytes), None)
    response.status_code = 201 if created else 200
    return {"pod_id": str(pod.id), "attached": created}
