import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import BILLING, current_user, load_trip, require_billing
from app.core.config import get_settings
from app.core.db import SessionLocal, get_db
from app.core.errors import BadRequest
from app.models import AuditLog, BillingExport, BillingExportItem, Client, Trip, User, aware
from app.repositories.trips import TripFilters, query_trips
from app.schemas.serializers import page, pod_out, trip_out
from app.services.audit import audit
from app.services.pods.service import create_pod, process_pod
from app.services.trips_import import import_trips

router = APIRouter(tags=["trips"])


def run_ai(pod_id) -> None:
    """Background task: opens its own session so the upload response is never blocked on (or lost to) inference."""
    with SessionLocal() as db:
        try:
            process_pod(db, pod_id)
        except Exception:  # process_pod already routes provider failures to review; this guards unexpected faults
            db.rollback()
            import logging

            logging.getLogger("routeproof").exception("background POD processing failed for %s", pod_id)


def read_limited(f: UploadFile) -> bytes:
    limit = get_settings().upload_max_size_bytes
    data = f.file.read(limit + 1)
    return data


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        raise BadRequest("invalid_timestamp", "captured_at must be an ISO-8601 timestamp")
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


@router.get("/meta/options")
def options(user: User = Depends(require_billing), db: Session = Depends(get_db)):
    clients = db.scalars(select(Client).order_by(Client.company_name)).all()
    branches = sorted({b for b in db.scalars(select(Trip.branch).distinct()) if b})
    cycles = sorted({c for c in db.scalars(select(Trip.billing_cycle).distinct()) if c}, reverse=True)
    return {"clients": [{"id": str(c.id), "name": c.company_name, "code": c.client_code} for c in clients],
            "branches": branches, "billing_cycles": cycles, "data_source": get_settings().data_mode}


@router.get("/trips")
def list_trips(q: str | None = None, client_id: uuid.UUID | None = None, branch: str | None = None, destination: str | None = None,
               vehicle: str | None = None, trip_status: str | None = None, pod_status: str | None = None,
               billing_status: str | None = None, billing_cycle: str | None = None, date_from: date | None = None,
               date_to: date | None = None, page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(20, ge=1, le=100),
               user: User = Depends(require_billing), db: Session = Depends(get_db)):
    f = TripFilters(q, client_id, branch, destination, vehicle, trip_status, pod_status, billing_status, billing_cycle,
                    None, date_from, date_to)
    items, total = query_trips(db, f, page_no, page_size)
    return page([trip_out(t) for t in items], total, page_no, page_size)


@router.post("/trips/import")
def import_csv(file: UploadFile = File(...), dry_run: bool = Query(False), user: User = Depends(require_billing),
               db: Session = Depends(get_db)):
    data = read_limited(file)
    if len(data) > 2 * 1024 * 1024:
        raise BadRequest("file_too_large", "CSV must be under 2 MB")
    return import_trips(db, user.id, data, dry_run)


@router.get("/trips/{trip_id}")
def trip_detail(trip_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = load_trip(db, trip_id, user)
    driver_view = user.role != BILLING
    out = trip_out(t, driver_view=driver_view)
    out["pods"] = [pod_out(p, driver_view=driver_view) for p in t.pods]
    if not driver_view:
        exports = db.scalars(select(BillingExport).join(BillingExportItem, BillingExportItem.export_id == BillingExport.id)
                             .where(BillingExportItem.trip_id == t.id).order_by(BillingExport.created_at)).unique()
        out["billing_history"] = [{"export_id": str(e.id), "export_reference": e.export_reference, "is_reexport": e.is_reexport,
                                   "created_at": aware(e.created_at).isoformat()} for e in exports]
    return out


@router.get("/trips/{trip_id}/history")
def trip_history(trip_id: uuid.UUID, user: User = Depends(require_billing), db: Session = Depends(get_db)):
    t = load_trip(db, trip_id, user)
    ids = [str(t.id)] + [str(p.id) for p in t.pods]
    rows = db.scalars(select(AuditLog).where(AuditLog.entity_id.in_(ids)).order_by(AuditLog.timestamp)).unique()
    return {"items": [{"id": str(r.id), "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id,
                       "user": r.user.name if r.user else None, "timestamp": aware(r.timestamp).isoformat(),
                       "previous_values": r.previous_values, "new_values": r.new_values, "metadata": r.meta} for r in rows]}


@router.post("/trips/{trip_id}/pods")
def upload_pod(trip_id: uuid.UUID, background: BackgroundTasks, file: UploadFile = File(...),
                     original: UploadFile | None = File(None), captured_at: str | None = Form(None),
                     latitude: float | None = Form(None), longitude: float | None = Form(None),
                     accuracy: float | None = Form(None), idempotency_key: str | None = Form(None),
                     idem_header: str | None = Header(None, alias="Idempotency-Key"),
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    trip = load_trip(db, trip_id, user)
    key = idempotency_key or idem_header
    if not key or not (8 <= len(key) <= 80):
        raise BadRequest("idempotency_key_required", "Idempotency-Key (8-80 chars) is required")
    pod, created = create_pod(
        db, trip, user_id=user.id, data=read_limited(file), idempotency_key=key, captured_at=parse_dt(captured_at),
        latitude=latitude, longitude=longitude, accuracy=accuracy,
        source="driver_app" if user.role != BILLING else "staff", original=read_limited(original) if original else None,
    )
    if created:
        background.add_task(run_ai, pod.id)
    body = {"created": created, "pod": pod_out(pod, driver_view=user.role != BILLING)}
    return JSONResponse(body, status_code=201 if created else 200)
