import logging
import time
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BadRequest, Conflict, NotFound
from app.models import Pod, PodExtraction, PodReview, Trip, UploadJob, aware, utcnow
from app.services.ai.base import AIProviderError, TripContext
from app.services.ai.factory import get_provider
from app.services.ai.schema import PROMPT_VERSION, SCHEMA_VERSION, PodExtractionResult
from app.services.ai.validation import Expected, evaluate
from app.services.audit import audit
from app.services.billing.eligibility import sync_billing_status
from app.services.pods.state import can_request_retake, pod_transition
from app.services.uploads.storage import get_storage, sharpness_score, validate_image

log = logging.getLogger("routeproof.pods")

EDITABLE_FIELDS = ("lr_number", "consignee", "delivered_quantity", "quantity_unit", "delivery_date",
                   "signature_visible", "stamp_visible", "shortage_detected", "damage_detected", "remarks")


def latest_pod(trip: Trip) -> Pod | None:
    return trip.pods[-1] if trip.pods else None


def pod_status_for_trip(trip: Trip) -> str:
    p = latest_pod(trip)
    return p.verification_status if p else "PENDING"


def latest_extraction(pod: Pod) -> PodExtraction | None:
    return pod.extractions[-1] if pod.extractions else None


def flat_values(extracted: dict | None) -> dict:
    if not extracted:
        return {}
    q = extracted.get("delivered_quantity") or {}
    return {
        "lr_number": (extracted.get("lr_number") or {}).get("value"),
        "consignee": (extracted.get("consignee") or {}).get("value"),
        "delivered_quantity": q.get("value"),
        "quantity_unit": q.get("unit"),
        "delivery_date": (extracted.get("delivery_date") or {}).get("value"),
        "signature_visible": extracted.get("signature_visible"),
        "stamp_visible": extracted.get("stamp_visible"),
        "shortage_detected": extracted.get("shortage_detected"),
        "damage_detected": extracted.get("damage_detected"),
        "remarks": extracted.get("remarks"),
    }


def effective_values(pod: Pod) -> dict:
    """AI extraction overlaid with the latest human corrections; the original extraction row is never modified."""
    ex = latest_extraction(pod)
    vals = flat_values(ex.extracted_data if ex else None)
    for r in pod.reviews:
        if r.corrected_values:
            vals.update(r.corrected_values)
    return vals


# ---------- upload ----------

def create_pod(db: Session, trip: Trip, *, user_id, data: bytes, idempotency_key: str, captured_at: datetime | None,
               latitude=None, longitude=None, accuracy=None, source="driver_app", original: bytes | None = None,
               retry_count: int = 0) -> tuple[Pod, bool]:
    """Returns (pod, created). Duplicate idempotency keys return the original resource."""
    existing = db.scalar(select(UploadJob).where(UploadJob.idempotency_key == idempotency_key))
    if existing:
        return _dup(db, existing, trip)
    if trip.trip_status == "CANCELLED":
        raise Conflict("trip_cancelled", "Trip is cancelled")
    ctype, ext = validate_image(data)
    last = latest_pod(trip)
    if last and last.verification_status not in ("RETAKE_REQUESTED", "REJECTED"):
        raise Conflict("pod_in_progress", f"A POD for this trip is already {last.verification_status}",
                       {"pod_id": str(last.id), "status": last.verification_status})
    if latitude is not None and not (-90 <= float(latitude) <= 90 and -180 <= float(longitude or 0) <= 180):
        raise BadRequest("invalid_location", "Latitude/longitude out of range")

    pod_id = uuid.uuid4()
    key = f"pods/{trip.id}/{pod_id}.{ext}"
    orig_key = key
    st = get_storage()
    st.put(key, data, ctype)
    if original:
        octype, oext = validate_image(original)
        orig_key = f"pods/{trip.id}/{pod_id}-original.{oext}"
        st.put(orig_key, original, octype)

    pod = Pod(
        id=pod_id, trip_id=trip.id, attempt_number=(last.attempt_number + 1) if last else 1,
        original_image_path=orig_key, uploaded_image_path=key, captured_at=captured_at,
        latitude=Decimal(str(latitude)) if latitude is not None else None,
        longitude=Decimal(str(longitude)) if longitude is not None else None,
        location_accuracy=accuracy, upload_status="UPLOADED", verification_status="UPLOADED",
        retake_count=last.retake_count if last else 0, source=source,
    )
    db.add(pod)
    db.flush()  # PostgreSQL enforces the upload_jobs.pod_id FK: the pod row must exist first
    job = UploadJob(pod_id=pod_id, trip_id=trip.id, idempotency_key=idempotency_key, upload_status="UPLOADED", retry_count=retry_count)
    db.add(job)
    if trip.trip_status == "IN_TRANSIT":
        trip.trip_status = "DELIVERED"
        trip.delivery_date = trip.delivery_date or date.today()
    trip.trip_status = "POD_PENDING"
    audit(db, user_id, "pod", pod_id, "pod.uploaded", None,
          {"trip": trip.trip_reference, "attempt": pod.attempt_number, "source": source},
          {"captured_at_client": captured_at.isoformat() if captured_at else None, "has_gps": latitude is not None,
           "bytes": len(data), "idempotency_key": idempotency_key})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(UploadJob).where(UploadJob.idempotency_key == idempotency_key))
        if existing:
            return _dup(db, existing, trip)
        raise
    db.refresh(pod)
    return pod, True


def _dup(db: Session, job: UploadJob, trip: Trip):
    if job.trip_id != trip.id:
        raise Conflict("idempotency_key_reused", "Idempotency key was already used for a different trip")
    job.retry_count += 1
    db.commit()
    return db.get(Pod, job.pod_id), False


# ---------- AI processing ----------

def process_pod(db: Session, pod_id, user_id=None) -> Pod:
    """UPLOADED (or NEEDS_REVIEW, for manual reprocess) -> AI_PROCESSING -> VERIFIED | NEEDS_REVIEW | RETAKE_REQUESTED.

    A provider failure never loses the POD: it is routed to NEEDS_REVIEW with the error recorded.
    """
    s = get_settings()
    pod = db.get(Pod, pod_id)
    if not pod:
        raise NotFound("POD")
    trip = pod.trip
    prev = pod_transition(pod, "AI_PROCESSING")
    audit(db, user_id, "pod", pod.id, "pod.ai_processing_started", {"status": prev}, {"status": "AI_PROCESSING"})
    db.commit()

    provider = get_provider()
    ctx = TripContext(trip.trip_reference, trip.lr_number, trip.consignee_name, trip.client.company_name)
    t0 = time.perf_counter()
    res: PodExtractionResult | None = None
    error: str | None = None
    try:
        data = get_storage().get(pod.uploaded_image_path)
        ctype = "image/" + pod.uploaded_image_path.rsplit(".", 1)[-1].replace("jpg", "jpeg")
        if sharpness_score(data) < 1.0:
            raise AIProviderError("unreadable", "Image appears blank or unreadable")
        res = provider.analyze_pod(data, ctype, ctx)
    except AIProviderError as e:
        error = f"{e.kind}: {e}"
    except Exception as e:  # storage/IO etc. must still not lose the POD
        log.exception("unexpected error during POD processing")
        error = f"internal: {type(e).__name__}"
    duration = int((time.perf_counter() - t0) * 1000)

    decision = evaluate(res, _expected(trip), threshold=s.ai_confidence_threshold, retakes_used=pod.retake_count,
                        max_retakes=s.max_retake_requests, today=date.today(), error=error)

    ex = PodExtraction(
        pod_id=pod.id,
        extracted_data=res.model_dump() if res else None,
        confidence_data=({k: getattr(res, k).confidence for k in ("lr_number", "consignee", "delivered_quantity", "delivery_date")} if res else None),
        validation_data={"checks": decision.checks, "reasons": decision.reasons, "decision": decision.decision,
                         "priority": decision.priority, "confidence_threshold": s.ai_confidence_threshold},
        model_provider=provider.name, model_identifier=provider.model, prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION, processing_status="FAILED" if res is None else "SUCCEEDED",
        processing_error=error, processing_duration_ms=duration,
    )
    db.add(ex)
    pod.review_reasons = decision.reasons
    pod.review_priority = decision.priority
    _apply_decision(db, pod, trip, decision.decision, user_id)
    audit(db, user_id, "pod", pod.id, "pod.ai_processed", None,
          {"decision": decision.decision, "reasons": decision.reasons},
          {"provider": provider.name, "model": provider.model, "duration_ms": duration, "error": error})
    db.commit()
    return pod


def _expected(trip: Trip) -> Expected:
    return Expected(trip.lr_number, trip.consignee_name, trip.delivery_date, trip.expected_quantity, trip.quantity_unit)


def _apply_decision(db: Session, pod: Pod, trip: Trip, decision: str, user_id) -> None:
    if decision == "RETAKE_REQUESTED":
        _retake(db, pod, trip, user_id, auto=True)
    elif decision == "VERIFIED":
        mark_verified(db, pod, trip, "ai", user_id)
    else:
        pod_transition(pod, "NEEDS_REVIEW")
        trip.trip_status = "POD_PENDING"


def _retake(db: Session, pod: Pod, trip: Trip, user_id, auto: bool) -> None:
    s = get_settings()
    if not can_request_retake(pod.retake_count, s.max_retake_requests):
        raise Conflict("retake_limit", f"At most {s.max_retake_requests} retake requests are allowed; send to manual review")
    pod_transition(pod, "RETAKE_REQUESTED")
    pod.retake_count += 1
    trip.trip_status = "POD_PENDING"
    audit(db, user_id, "pod", pod.id, "pod.retake_requested", None,
          {"retake_count": pod.retake_count, "automatic": auto, "reasons": pod.review_reasons})


def mark_verified(db: Session, pod: Pod, trip: Trip, method: str, user_id) -> None:
    pod_transition(pod, "VERIFIED")
    pod.verification_method = method
    pod.verified_at = utcnow()
    trip.trip_status = "POD_VERIFIED"
    became = sync_billing_status(trip)
    audit(db, user_id, "pod", pod.id, "pod.verified", None, {"method": method, "billing_ready": became})
    if became:
        audit(db, user_id, "trip", trip.id, "trip.billing_ready", {"billing_status": "NOT_READY"}, {"billing_status": "BILLING_READY"})


# ---------- human review ----------

def _coerce(field: str, value):
    if value in ("", None):
        return None
    if field in ("signature_visible", "stamp_visible", "shortage_detected", "damage_detected"):
        if isinstance(value, bool):
            return value
        raise BadRequest("invalid_correction", f"{field} must be true or false")
    if field == "delivered_quantity":
        try:
            return float(Decimal(str(value)))
        except (InvalidOperation, ValueError):
            raise BadRequest("invalid_correction", "delivered_quantity must be a number")
    if field == "delivery_date":
        try:
            return date.fromisoformat(str(value)).isoformat()
        except ValueError:
            raise BadRequest("invalid_correction", "delivery_date must be YYYY-MM-DD")
    return str(value).strip()[:300]


def review_pod(db: Session, pod: Pod, reviewer_id, *, decision: str, corrections: dict | None,
               correction_reason: str | None, rejection_reason: str | None) -> Pod:
    trip = pod.trip
    if pod.verification_status != "NEEDS_REVIEW":
        raise Conflict("invalid_transition", f"POD is {pod.verification_status}; only NEEDS_REVIEW can be reviewed")
    ex = latest_extraction(pod)
    original = flat_values(ex.extracted_data if ex else None)
    current = effective_values(pod)

    corrected: dict = {}
    for k, v in (corrections or {}).items():
        if k not in EDITABLE_FIELDS:
            raise BadRequest("invalid_correction", f"Field {k} cannot be corrected")
        nv = _coerce(k, v)
        if nv != current.get(k):
            corrected[k] = nv
    if corrected and not (correction_reason or "").strip():
        raise BadRequest("reason_required", "A correction reason is required when changing extracted values")

    if decision == "APPROVE":
        row = PodReview(pod_id=pod.id, reviewer_id=reviewer_id, original_values={k: original.get(k) for k in corrected} or original,
                        corrected_values=corrected or None, correction_reason=correction_reason, decision="APPROVED")
        db.add(row)
        if corrected:
            audit(db, reviewer_id, "pod", pod.id, "pod.fields_corrected",
                  {k: current.get(k) for k in corrected}, corrected, {"reason": correction_reason, "ai_original": {k: original.get(k) for k in corrected}})
        mark_verified(db, pod, trip, "human", reviewer_id)
    elif decision == "REJECT":
        if not (rejection_reason or "").strip():
            raise BadRequest("reason_required", "A rejection reason is required")
        db.add(PodReview(pod_id=pod.id, reviewer_id=reviewer_id, original_values=original, corrected_values=corrected or None,
                         correction_reason=rejection_reason, decision="REJECTED"))
        pod_transition(pod, "REJECTED")
        pod.rejection_reason = rejection_reason
        trip.trip_status = "POD_PENDING"
        audit(db, reviewer_id, "pod", pod.id, "pod.rejected", None, {"reason": rejection_reason})
    elif decision == "RETAKE":
        db.add(PodReview(pod_id=pod.id, reviewer_id=reviewer_id, original_values=original, corrected_values=None,
                         correction_reason=rejection_reason or correction_reason, decision="RETAKE_REQUESTED"))
        _retake(db, pod, trip, reviewer_id, auto=False)
    else:
        raise BadRequest("invalid_decision", "decision must be APPROVE, REJECT or RETAKE")
    db.commit()
    db.refresh(pod)
    return pod


def request_retake_manual(db: Session, pod: Pod, user_id) -> Pod:
    """Standalone retake endpoint (POST /pods/{id}/retake); same rules as a review-driven retake."""
    _retake(db, pod, pod.trip, user_id, auto=False)
    db.commit()
    return pod
