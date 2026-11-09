import uuid

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy import case, exists, func, select
from sqlalchemy.orm import Session

from app.api.deps import BILLING, current_user, load_trip, require_billing
from app.core.db import get_db
from app.core.errors import Conflict, NotFound
from app.models import Pod, PodReviewReason, Trip, User
from app.schemas.requests import ReviewIn
from app.schemas.serializers import page, pod_out
from app.api.v1.trips import read_limited
from app.core.config import get_settings
from app.services.pods.service import (
    attach_original, fail_to_review, is_stale, process_pod, recover_stale, request_retake_manual, review_pod,
)
from app.services.uploads.storage import get_storage

router = APIRouter(tags=["pods"])

_PRIORITY_ORDER = case((Pod.review_priority == "high", 0), (Pod.review_priority == "medium", 1),
                       (Pod.review_priority == "low", 2), else_=3)


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


@router.post("/pods/{pod_id}/original")
def upload_original(pod_id: uuid.UUID, response: Response, file: UploadFile = File(...), user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    """Second step of a driver upload: the full-resolution original, sent after the compressed copy was accepted."""
    pod = load_pod(db, pod_id, user)
    pod, created = attach_original(db, pod, read_limited(file, get_settings().original_max_size_bytes), user.id)
    response.status_code = 201 if created else 200
    return {"pod_id": str(pod.id), "attached": created, "original_bytes": pod.original_bytes}


@router.post("/pods/{pod_id}/process")
def reprocess(pod_id: uuid.UUID, user: User = Depends(require_billing), db: Session = Depends(get_db)):
    """Manual (re)process. Also the escape hatch for a POD stuck in AI_PROCESSING once it is stale."""
    pod = load_pod(db, pod_id, user)
    if pod.verification_status == "AI_PROCESSING":
        if not is_stale(pod):
            raise Conflict("processing_in_progress", "This POD is being processed; try again in a few minutes")
        pod = fail_to_review(db, pod.id, user.id, "PROCESSING_STALLED", "stalled: manually recovered before reprocessing")
    if pod.verification_status not in ("UPLOADED", "NEEDS_REVIEW"):
        raise Conflict("invalid_transition", f"POD in state {pod.verification_status} cannot be processed")
    return pod_out(process_pod(db, pod.id, user.id))


@router.post("/pods/maintenance/recover")
def recover(user: User = Depends(require_billing), db: Session = Depends(get_db)):
    """Run the stale-job sweep now (it also runs periodically in the background)."""
    return recover_stale(db)


@router.post("/pods/{pod_id}/retake")
def retake(pod_id: uuid.UUID, user: User = Depends(require_billing), db: Session = Depends(get_db)):
    pod = load_pod(db, pod_id, user)
    return pod_out(request_retake_manual(db, pod, user.id))


@router.post("/pods/{pod_id}/review")
def review(pod_id: uuid.UUID, body: ReviewIn, user: User = Depends(require_billing), db: Session = Depends(get_db)):
    pod = load_pod(db, pod_id, user)
    return pod_out(review_pod(db, pod, user.id, decision=body.decision, corrections=body.corrections,
                              correction_reason=body.correction_reason, rejection_reason=body.rejection_reason,
                              approval_reason=body.approval_reason))


@router.get("/reviews")
def review_queue(status: str = Query("NEEDS_REVIEW", pattern="^(NEEDS_REVIEW|RETAKE_REQUESTED|REJECTED|VERIFIED|AI_PROCESSING|UPLOADED)$"),
                 reason: str | None = Query(None, max_length=40),
                 category: str | None = Query(None, pattern="^(system|document_quality|business)$"),
                 priority: str | None = Query(None, pattern="^(high|medium|low)$"),
                 client_id: uuid.UUID | None = None, q: str | None = None, page_no: int = Query(1, alias="page", ge=1),
                 page_size: int = Query(20, ge=1, le=100), user: User = Depends(require_billing), db: Session = Depends(get_db)):
    # All filtering, ordering and pagination happen in SQL; only one page of rows is loaded.
    conds = [Pod.verification_status == status]
    if client_id:
        conds.append(Trip.client_id == client_id)
    if q:
        like = f"%{q.strip()}%"
        conds.append(Trip.trip_reference.ilike(like) | Trip.lr_number.ilike(like))
    if priority:
        conds.append(Pod.review_priority == priority)
    if reason:
        conds.append(exists().where(PodReviewReason.pod_id == Pod.id, PodReviewReason.reason == reason))
    if category:
        conds.append(exists().where(PodReviewReason.pod_id == Pod.id, PodReviewReason.category == category))

    total = db.scalar(select(func.count(Pod.id)).join(Trip, Trip.id == Pod.trip_id).where(*conds))
    stmt = (select(Pod).join(Trip, Trip.id == Pod.trip_id).where(*conds)
            .order_by(_PRIORITY_ORDER, Pod.server_received_at, Pod.id)
            .limit(page_size).offset((page_no - 1) * page_size))
    out = []
    for p in db.scalars(stmt).unique():
        o = pod_out(p)
        o.pop("extractions_history", None)
        out.append(o)
    return page(out, total, page_no, page_size)
