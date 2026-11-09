"""Retention and controlled deletion (see docs/data-protection.md).

What is removed, and what is kept:

* POD **images** (the part carrying signatures, stamps and handwriting) are deleted from storage once the record no longer
  needs them. The trip, POD metadata, extraction values, review decisions and audit trail stay: they are the business
  and accounting record. The POD row records when and why its images were purged, and image endpoints answer 410.
* **Access-log** audit rows (link opened, image viewed) are deleted after ACCESS_LOG_RETENTION_DAYS. State-change audit
  rows (uploads, reviews, exports, revocations) are kept with the records they describe.

Legal hold: images of a trip that is not yet INVOICED, or whose latest POD is still open (UPLOADED / AI_PROCESSING /
NEEDS_REVIEW), are never purged by the schedule.

Nothing is deleted automatically. The schedule is a dry run unless --apply is given; targeted erasure (e.g. a
data-principal request the business has approved) needs an explicit reason and is audited.

    python -m app.services.retention                       # dry run: what the schedule would purge
    python -m app.services.retention --apply               # purge per schedule
    python -m app.services.retention --erase-pod <uuid> --reason "DPR-2026-014 approved by DPO" [--override-hold]
"""
import argparse
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, BadRequest, NotFound
from app.models import AuditLog, ClientViewLink, DriverLink, Pod, Trip, aware, utcnow
from app.services.audit import audit
from app.services.uploads.storage import Storage, get_storage

log = logging.getLogger("routeproof.retention")

ACCESS_ACTIONS = ("client_link.opened", "client_link.image_viewed", "client_link.access_denied", "driver_link.opened")
OPEN_STATES = ("UPLOADED", "AI_PROCESSING", "NEEDS_REVIEW")
SUPERSEDED = ("REJECTED", "RETAKE_REQUESTED")


def _hold_reason(pod: Pod, trip: Trip) -> str | None:
    last = trip.pods[-1] if trip.pods else None
    if last and last.verification_status in OPEN_STATES:
        return "trip has an open POD"
    if pod.verification_status in SUPERSEDED and pod is not last:
        return None  # superseded attempt: not billing evidence
    if trip.billing_status != "INVOICED":
        return f"trip billing status is {trip.billing_status}"
    return None


def due_for_purge(db: Session, now: datetime | None = None) -> list[tuple[Pod, str]]:
    s = get_settings()
    now = now or utcnow()
    out = []
    pods = db.scalars(select(Pod).where(Pod.images_purged_at.is_(None), Pod.uploaded_image_path.isnot(None))).unique()
    for p in pods:
        trip = p.trip
        if _hold_reason(p, trip):
            continue
        last = trip.pods[-1] if trip.pods else None
        if p.verification_status in SUPERSEDED and p is not last:
            age_from, days, why = aware(p.server_received_at), s.superseded_image_retention_days, "superseded attempt past retention"
        else:
            age_from = aware(trip.invoiced_at) or aware(p.verified_at) or aware(p.server_received_at)
            days, why = s.pod_image_retention_days, "invoiced POD past retention"
        if age_from and age_from < now - timedelta(days=days):
            out.append((p, why))
    return out


def purge_pod_images(db: Session, pod: Pod, *, reason: str, actor_id=None, st: Storage | None = None,
                     override_hold: bool = False) -> Pod:
    """Delete a POD's image objects and mark the row. Idempotent. Metadata and audit are kept."""
    if not (reason or "").strip():
        raise BadRequest("reason_required", "A reason is required to erase POD images")
    if pod.images_purged_at:
        return pod
    hold = _hold_reason(pod, pod.trip)
    if hold and not override_hold:
        raise AppError(409, "legal_hold", f"Images are on hold: {hold}")
    st = st or get_storage()
    keys = list(dict.fromkeys(k for k in (pod.uploaded_image_path, pod.original_image_path) if k))
    for k in keys:
        st.delete(k)  # missing objects are fine; a storage error aborts before the row is changed
    pod.images_purged_at = utcnow()
    pod.images_purge_reason = reason.strip()[:300]
    audit(db, actor_id, "pod", pod.id, "pod.images_purged", {"objects": len(keys)}, {"images_purged": True},
          {"reason": pod.images_purge_reason, "override_hold": bool(hold and override_hold)})
    db.commit()
    log.info("retention.pod_images_purged", extra={"pod_id": str(pod.id), "count": len(keys)})
    return pod


def purge_access_logs(db: Session, now: datetime | None = None, *, apply: bool = False) -> int:
    cutoff = (now or utcnow()) - timedelta(days=get_settings().access_log_retention_days)
    cond = (AuditLog.action.in_(ACCESS_ACTIONS), AuditLog.timestamp < cutoff)
    rows = db.scalars(select(AuditLog.id).where(*cond)).all()
    if apply and rows:
        db.execute(delete(AuditLog).where(*cond))
        audit(db, None, "retention", "access_logs", "retention.access_logs_purged", None, {"rows": len(rows)},
              {"older_than": cutoff.isoformat()})  # the purge itself is recorded, without the purged content
        db.commit()
    return len(rows)


def record_link_expiries(db: Session, now: datetime | None = None) -> int:
    """Expiry is passive (a timestamp), so write one audit event per link the moment it is noticed as expired."""
    now = now or utcnow()
    done = set(db.scalars(select(AuditLog.entity_id).where(AuditLog.action.in_(("client_link.expired", "driver_link.expired")))))
    n = 0
    for model, etype in ((ClientViewLink, "client_link"), (DriverLink, "driver_link")):
        for link in db.scalars(select(model).where(model.expires_at < now)).unique():
            revoked = link.revoked_at is not None if model is ClientViewLink else bool(link.revoked)
            if revoked or str(link.id) in done:  # a revoked link ended by revocation, which is already audited
                continue
            audit(db, None, etype, link.id, f"{etype}.expired", {"state": "active"}, {"state": "expired"},
                  {"expires_at": aware(link.expires_at).isoformat()})
            n += 1
    if n:
        db.commit()
    return n


def run(db: Session, *, apply: bool = False, now: datetime | None = None) -> dict:
    due = due_for_purge(db, now)
    purged = []
    if apply:
        for pod, why in due:
            purge_pod_images(db, pod, reason=f"retention schedule: {why}")
            purged.append(str(pod.id))
    return {"dry_run": not apply, "pods_due": [{"pod_id": str(p.id), "trip": p.trip.trip_reference, "why": w} for p, w in due],
            "pods_purged": purged, "access_log_rows": purge_access_logs(db, now, apply=apply),
            "links_expired_recorded": record_link_expiries(db, now)}


def main() -> None:
    from app.core.db import SessionLocal

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually purge (default is a dry run)")
    ap.add_argument("--erase-pod", type=uuid.UUID, help="erase the images of one POD")
    ap.add_argument("--reason", help="required with --erase-pod (e.g. the approved request reference)")
    ap.add_argument("--override-hold", action="store_true", help="erase even if the trip is not yet invoiced or under review")
    a = ap.parse_args()
    with SessionLocal() as db:
        if a.erase_pod:
            pod = db.get(Pod, a.erase_pod)
            if not pod:
                raise NotFound("POD")
            purge_pod_images(db, pod, reason=a.reason or "", override_hold=a.override_hold)
            print(f"erased images of POD {pod.id} ({pod.trip.trip_reference}); metadata and audit trail kept")
            return
        r = run(db, apply=a.apply)
    for p in r["pods_due"]:
        print(("purged " if r["pods_purged"] else "due    ") + f"{p['pod_id']} {p['trip']}  ({p['why']})")
    print(f"{len(r['pods_due'])} POD(s) due; {len(r['pods_purged'])} purged; {r['access_log_rows']} access-log row(s) "
          f"{'deleted' if a.apply else 'due'}; {r['links_expired_recorded']} link expiry event(s) recorded; dry_run={r['dry_run']}")


if __name__ == "__main__":
    main()
