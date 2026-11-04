from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_driver
from app.core.db import get_db
from app.models import Pod, Trip, UploadJob, User
from app.schemas.requests import SyncIn
from app.schemas.serializers import pod_out, trip_out

router = APIRouter(prefix="/driver", tags=["driver"])


@router.get("/trips")
def my_trips(user: User = Depends(require_driver), db: Session = Depends(get_db)):
    trips = db.scalars(select(Trip).where(Trip.driver_id == user.id, Trip.trip_status != "CANCELLED")
                       .order_by(Trip.trip_status, Trip.delivery_date.desc().nullslast())).unique()
    return {"items": [trip_out(t, driver_view=True) for t in trips]}


@router.get("/uploads")
def my_uploads(user: User = Depends(require_driver), db: Session = Depends(get_db)):
    pods = db.scalars(select(Pod).join(Trip, Trip.id == Pod.trip_id).where(Trip.driver_id == user.id)
                      .order_by(Pod.server_received_at.desc()).limit(50)).unique()
    return {"items": [pod_out(p, driver_view=True) for p in pods]}


@router.post("/uploads/sync")
def sync(body: SyncIn, user: User = Depends(require_driver), db: Session = Depends(get_db)):
    """Server acknowledgement: tells the device which queued captures the server holds, so originals can be released."""
    jobs = {j.idempotency_key: j for j in db.scalars(
        select(UploadJob).join(Trip, Trip.id == UploadJob.trip_id).where(UploadJob.idempotency_key.in_(body.keys), Trip.driver_id == user.id))}
    items = []
    for k in body.keys:
        j = jobs.get(k)
        pod = db.get(Pod, j.pod_id) if j else None
        items.append({"idempotency_key": k, "received": bool(j), "pod_id": str(j.pod_id) if j else None,
                      "verification_status": pod.verification_status if pod else None,
                      "retakes_remaining": pod_out(pod, driver_view=True)["retakes_remaining"] if pod else None})
    return {"items": items}
