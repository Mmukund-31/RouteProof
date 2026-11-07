from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header
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
from app.models import DriverLink, Trip, User, aware, utcnow
from app.schemas.requests import DriverLinkIn
from app.services.audit import audit
from app.services.notifications.sms import get_sms_provider, mask_phone
from app.services.pods.service import create_pod, latest_pod

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
