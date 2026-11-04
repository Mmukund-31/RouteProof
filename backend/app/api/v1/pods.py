import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import BILLING, current_user, load_trip, require_billing
from app.core.db import get_db
from app.core.errors import Conflict, NotFound
from app.models import Pod, Trip, User, aware
from app.schemas.requests import ReviewIn
from app.schemas.serializers import page, pod_out
from app.services.pods.service import process_pod, request_retake_manual, review_pod
from app.services.uploads.storage import get_storage

router = APIRouter(tags=["pods"])

_PRIO = {"high": 0, "medium": 1, "low": 2, None: 3}


def load_pod(db: Session, pod_id: uuid.UUID, user: User) -> Pod:
    pod = db.get(Pod, pod_id)
    if not pod:
        raise NotFound("POD")
    load_trip(db, pod.trip_id, user)  # resource-level authorization via the owning trip
    return pod


@router.get("/pods/{pod_id}")
def get_pod(pod_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return pod_out(load_pod(db, pod_id, user), driver_view=user.role != BILLING)


@router.get("/pods/{pod_id}/image")
def get_image(pod_id: uuid.UUID, variant: str = Query("upload", pattern="^(upload|original)$"),
              user: User = Depends(current_user), db: Session = Depends(get_db)):
    pod = load_pod(db, pod_id, user)
    path = pod.original_image_path if variant == "original" else pod.uploaded_image_path
    try:
        data = get_storage().get(path)
    except Exception:
        raise NotFound("Image")
    ext = path.rsplit(".", 1)[-1].replace("jpg", "jpeg")
    return Response(data, media_type=f"image/{ext}", headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/pods/{pod_id}/process")
def reprocess(pod_id: uuid.UUID, user: User = Depends(require_billing), db: Session = Depends(get_db)):
    pod = load_pod(db, pod_id, user)
    if pod.verification_status not in ("UPLOADED", "NEEDS_REVIEW"):
        raise Conflict("invalid_transition", f"POD in state {pod.verification_status} cannot be processed")
    return pod_out(process_pod(db, pod.id, user.id))


@router.post("/pods/{pod_id}/retake")
def retake(pod_id: uuid.UUID, user: User = Depends(require_billing), db: Session = Depends(get_db)):
    pod = load_pod(db, pod_id, user)
    return pod_out(request_retake_manual(db, pod, user.id))


@router.post("/pods/{pod_id}/review")
def review(pod_id: uuid.UUID, body: ReviewIn, user: User = Depends(require_billing), db: Session = Depends(get_db)):
    pod = load_pod(db, pod_id, user)
    return pod_out(review_pod(db, pod, user.id, decision=body.decision, corrections=body.corrections,
                              correction_reason=body.correction_reason, rejection_reason=body.rejection_reason))


@router.get("/reviews")
def review_queue(status: str = Query("NEEDS_REVIEW", pattern="^(NEEDS_REVIEW|RETAKE_REQUESTED|REJECTED|VERIFIED)$"),
                 reason: str | None = None, priority: str | None = Query(None, pattern="^(high|medium|low)$"),
                 client_id: uuid.UUID | None = None, q: str | None = None, page_no: int = Query(1, alias="page", ge=1),
                 page_size: int = Query(20, ge=1, le=100), user: User = Depends(require_billing), db: Session = Depends(get_db)):
    stmt = select(Pod).join(Trip, Trip.id == Pod.trip_id).where(Pod.verification_status == status)
    if client_id:
        stmt = stmt.where(Trip.client_id == client_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(Trip.trip_reference.ilike(like) | Trip.lr_number.ilike(like))
    pods = list(db.scalars(stmt).unique())
    if reason:
        pods = [p for p in pods if reason in (p.review_reasons or [])]
    if priority:
        pods = [p for p in pods if p.review_priority == priority]
    pods.sort(key=lambda p: (_PRIO.get(p.review_priority, 3), aware(p.server_received_at)))
    total = len(pods)
    start = (page_no - 1) * page_size
    out = []
    for p in pods[start:start + page_size]:
        o = pod_out(p)
        o.pop("extractions_history", None)
        out.append(o)
    return page(out, total, page_no, page_size)
