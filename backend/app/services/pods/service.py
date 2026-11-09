import logging
import time
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, BadRequest, Conflict, NotFound
from app.core.observability import processing_id_var
from app.models import Pod, PodExtraction, PodReview, Trip, UploadJob, aware, utcnow
from app.services.ai.base import AIProviderError, TripContext
from app.services.ai.factory import get_provider
from app.services.ai.schema import PROMPT_VERSION, SCHEMA_VERSION, PodExtractionResult
from app.services.ai.validation import EXCEPTION_REASONS, Expected, evaluate, reason_category
from app.services.audit import audit
from app.services.billing.eligibility import sync_billing_status
from app.services.pods.state import can_pod, can_request_retake, pod_transition
from app.services.uploads.storage import delete_quietly, get_storage, sharpness_score, validate_image, validate_original

log = logging.getLogger("routeproof.pods")

EDITABLE_FIELDS = ("lr_number", "consignee", "delivered_quantity", "quantity_unit", "delivery_date",
                   "signature_visible", "stamp_visible", "shortage_detected", "damage_detected", "remarks")

# Provider failures worth retrying inside one processing run. Everything else fails fast to review.
TRANSIENT_ERRORS = {"timeout", "rate_limit", "network", "unavailable"}

# What the device told us about GPS when no coordinates came with the upload.
LOCATION_STATUSES = {"captured", "permission_denied", "unavailable", "timeout", "unsupported", "not_provided"}


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


def _as_date(v) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)) if v else None
    except ValueError:
        return None


def size_policy(n_bytes: int) -> str:
    """'OK' when the compressed upload is strictly under the product limit (300 KB = 307,200 bytes), else 'OVERSIZE'."""
    return "OK" if n_bytes < get_settings().compressed_upload_limit_bytes else "OVERSIZE"


def location_status_for(latitude, longitude, reported: str | None) -> str:
    """Distinguish real coordinates from 'the device said no' and from 'we were told nothing'."""
    if latitude is not None and longitude is not None:
        return "captured"
    r = (reported or "").strip().lower()
    return r if r in LOCATION_STATUSES - {"captured"} else "not_provided"


# ---------- upload ----------

def create_pod(db: Session, trip: Trip, *, user_id, data: bytes, idempotency_key: str, captured_at: datetime | None,
               latitude=None, longitude=None, accuracy=None, source="driver_app", original: bytes | None = None,
               retry_count: int = 0, location_status: str | None = None) -> tuple[Pod, bool]:
    """Returns (pod, created). Duplicate idempotency keys return the original resource.

    Three timestamps are kept apart and never substituted for each other:
      * pod.captured_at        - the device clock at capture (unverified, may be hours old after offline queueing)
      * pod.server_received_at - when this server received the upload
      * trip.delivery_date     - only changed when a POD is *verified* (see mark_verified); never inferred from upload
    """
    existing = db.scalar(select(UploadJob).where(UploadJob.idempotency_key == idempotency_key))
    if existing:
        return _dup(db, existing, trip)
    if trip.trip_status == "CANCELLED":
        raise Conflict("trip_cancelled", "Trip is cancelled")
    # Validate everything before writing anything to storage.
    ctype, ext = validate_image(data)
    octype, oext = validate_original(original) if original else (None, None)
    policy = size_policy(len(data))
    last = latest_pod(trip)
    if last and last.verification_status not in ("RETAKE_REQUESTED", "REJECTED"):
        raise Conflict("pod_in_progress", f"A POD for this trip is already {last.verification_status}",
                       {"pod_id": str(last.id), "status": last.verification_status})
    if (latitude is None) != (longitude is None):
        raise BadRequest("invalid_location", "Latitude and longitude must be sent together")
    if latitude is not None and not (-90 <= float(latitude) <= 90 and -180 <= float(longitude) <= 180):
        raise BadRequest("invalid_location", "Latitude/longitude out of range")
    loc_status = location_status_for(latitude, longitude, location_status)

    # Deterministic object keys derived from the POD id: a key can always be traced back to (or ruled out as) a row.
    pod_id = uuid.uuid4()
    key = f"pods/{trip.id}/{pod_id}.{ext}"
    orig_key = f"pods/{trip.id}/{pod_id}-original.{oext}" if original else key
    st = get_storage()
    written: list[str] = []
    try:
        st.put(key, data, ctype)
        written.append(key)
        if original:
            st.put(orig_key, original, octype)
            written.append(orig_key)

        pod = Pod(
            id=pod_id, trip_id=trip.id, attempt_number=(last.attempt_number + 1) if last else 1,
            original_image_path=orig_key, uploaded_image_path=key, captured_at=captured_at,
            latitude=Decimal(str(latitude)) if latitude is not None else None,
            longitude=Decimal(str(longitude)) if longitude is not None else None,
            location_accuracy=accuracy if latitude is not None else None, location_status=loc_status,
            upload_bytes=len(data), original_bytes=len(original) if original else None, upload_size_policy=policy,
            upload_status="UPLOADED", verification_status="UPLOADED",
            retake_count=last.retake_count if last else 0, source=source, processing_attempts=0,
        )
        db.add(pod)
        db.flush()  # PostgreSQL enforces the upload_jobs.pod_id FK: the pod row must exist first
        db.add(UploadJob(pod_id=pod_id, trip_id=trip.id, idempotency_key=idempotency_key, upload_status="UPLOADED",
                         retry_count=retry_count))
        prev_trip_status = trip.trip_status
        if trip.trip_status in ("IN_TRANSIT", "DELIVERED"):
            # A POD upload means the driver says it was delivered, but *when* is decided by the verified document.
            trip.trip_status = "POD_PENDING"
        audit(db, user_id, "pod", pod_id, "pod.uploaded", None,
              {"trip": trip.trip_reference, "attempt": pod.attempt_number, "source": source},
              {"captured_at_client": captured_at.isoformat() if captured_at else None, "location_status": loc_status,
               "bytes": len(data), "size_policy": policy, "limit_bytes": get_settings().compressed_upload_limit_bytes,
               "idempotency_key": idempotency_key, "trip_status_before": prev_trip_status, "object_keys": written})
        if policy == "OVERSIZE":
            # Policy: keep the evidence (rejecting would lose a delivered POD), but flag it for the office.
            audit(db, user_id, "pod", pod_id, "pod.upload_oversize", None,
                  {"bytes": len(data), "limit_bytes": get_settings().compressed_upload_limit_bytes})
        db.commit()
    except IntegrityError:
        db.rollback()
        delete_quietly(st, written)  # compensate: these objects belong to a POD row that was never committed
        existing = db.scalar(select(UploadJob).where(UploadJob.idempotency_key == idempotency_key))
        if existing:
            return _dup(db, existing, trip)
        raise
    except BaseException:
        db.rollback()
        delete_quietly(st, written)
        raise
    db.refresh(pod)
    log.info("pod.uploaded", extra={"pod_id": str(pod.id), "trip_id": str(trip.id), "attempt": pod.attempt_number})
    return pod, True


def attach_original(db: Session, pod: Pod, data: bytes, user_id=None) -> tuple[Pod, bool]:
    """Attach the full-resolution camera original to a POD after the compressed copy was accepted.

    The phone sends the small copy first (fast, cheap on highway networks) and the original when the network allows,
    so the only server-side evidence is never just the compressed copy. Idempotent: a POD keeps its first original.
    """
    if pod.original_image_path and pod.original_image_path != pod.uploaded_image_path:
        return pod, False
    ctype, ext = validate_original(data)
    key = f"pods/{pod.trip_id}/{pod.id}-original.{ext}"
    st = get_storage()
    st.put(key, data, ctype)
    try:
        pod.original_image_path = key
        pod.original_bytes = len(data)
        audit(db, user_id, "pod", pod.id, "pod.original_attached", None, {"bytes": len(data)}, {"object_key": key})
        db.commit()
    except BaseException:
        db.rollback()
        delete_quietly(st, [key])
        raise
    return pod, True


def _dup(db: Session, job: UploadJob, trip: Trip):
    if job.trip_id != trip.id:
        raise Conflict("idempotency_key_reused", "Idempotency key was already used for a different trip")
    job.retry_count += 1
    db.commit()
    return db.get(Pod, job.pod_id), False


# ---------- AI processing ----------

def is_stale(pod: Pod, now: datetime | None = None) -> bool:
    if pod.verification_status != "AI_PROCESSING":
        return False
    started = aware(pod.processing_started_at) or aware(pod.server_received_at)
    return started is None or started < (now or utcnow()) - timedelta(minutes=get_settings().ai_processing_stale_minutes)


def process_pod(db: Session, pod_id, user_id=None) -> Pod:
    """UPLOADED (or NEEDS_REVIEW, for manual reprocess) -> AI_PROCESSING -> VERIFIED | NEEDS_REVIEW | RETAKE_REQUESTED.

    Guarantees: the AI_PROCESSING claim is atomic (two workers cannot process the same POD), and once claimed, *any*
    failure - provider init, storage, inference, validation or persistence - ends in NEEDS_REVIEW with the error
    recorded. If the process dies outright, recover_stale() picks the POD up later.
    """
    pod = db.get(Pod, pod_id)
    if not pod:
        raise NotFound("POD")
    frm = pod.verification_status
    if not can_pod(frm, "AI_PROCESSING"):
        raise Conflict("invalid_transition", f"POD cannot move from {frm} to AI_PROCESSING", {"from": frm, "to": "AI_PROCESSING"})
    claimed = db.execute(
        update(Pod).where(Pod.id == pod.id, Pod.verification_status == frm)
        .values(verification_status="AI_PROCESSING", processing_started_at=utcnow(),
                processing_attempts=func.coalesce(Pod.processing_attempts, 0) + 1)
        .execution_options(synchronize_session=False)
    ).rowcount
    if claimed != 1:
        db.rollback()
        raise Conflict("processing_in_progress", "This POD is already being processed")
    audit(db, user_id, "pod", pod.id, "pod.ai_processing_started", {"status": frm}, {"status": "AI_PROCESSING"})
    db.commit()
    db.refresh(pod)

    processing_id = str(uuid.uuid4())
    token = processing_id_var.set(processing_id)
    try:
        log.info("pod.processing_started", extra={"pod_id": str(pod.id), "from_status": frm, "attempt": pod.processing_attempts})
        try:
            return _run_extraction(db, pod, user_id, processing_id)
        except Exception as e:
            log.exception("pod.processing_crashed", extra={"pod_id": str(pod_id), "error_kind": "internal"})
            db.rollback()
            return fail_to_review(db, pod_id, user_id, "AI_ERROR", f"internal: {type(e).__name__}", processing_id=processing_id)
    finally:
        processing_id_var.reset(token)


def _run_extraction(db: Session, pod: Pod, user_id, processing_id: str) -> Pod:
    s = get_settings()
    trip = pod.trip
    provider = None
    res: PodExtractionResult | None = None
    error: str | None = None
    error_kind: str | None = None
    attempt_errors: list[str] = []
    calls = 0
    max_attempts = max(1, s.ai_max_attempts)
    t0 = time.perf_counter()
    try:
        provider = get_provider()  # inside the guarded block: a misconfigured provider must not strand the POD
        data = get_storage().get(pod.uploaded_image_path)
        ctype = "image/" + pod.uploaded_image_path.rsplit(".", 1)[-1].replace("jpg", "jpeg")
        if sharpness_score(data) < 1.0:
            raise AIProviderError("unreadable", "Image appears blank or unreadable")
        ctx = TripContext(trip.trip_reference, trip.lr_number, trip.consignee_name, trip.client.company_name)
        for attempt in range(1, max_attempts + 1):
            calls = attempt
            try:
                res = provider.analyze_pod(data, ctype, ctx)
                break
            except AIProviderError as e:
                attempt_errors.append(f"attempt {attempt}: {e.kind}: {e}")
                if e.kind not in TRANSIENT_ERRORS or attempt == max_attempts:
                    raise
                log.warning("pod.provider_retry", extra={"pod_id": str(pod.id), "attempt": attempt, "error_kind": e.kind})
                time.sleep(s.ai_retry_backoff_seconds * attempt)
    except AIProviderError as e:
        error, error_kind = f"{e.kind}: {e}", e.kind
    except Exception as e:  # storage/IO etc. must still not lose the POD
        log.exception("pod.processing_error", extra={"pod_id": str(pod.id), "error_kind": "internal"})
        error, error_kind = f"internal: {type(e).__name__}", "internal"
    duration = int((time.perf_counter() - t0) * 1000)

    decision = evaluate(res, _expected(trip), threshold=s.ai_confidence_threshold, retakes_used=pod.retake_count,
                        max_retakes=s.max_retake_requests, today=date.today(), error=error)

    ex = PodExtraction(
        pod_id=pod.id,
        extracted_data=res.model_dump() if res else None,
        confidence_data=({k: getattr(res, k).confidence for k in ("lr_number", "consignee", "delivered_quantity", "delivery_date")} if res else None),
        validation_data={"checks": decision.checks, "reasons": decision.reasons, "decision": decision.decision,
                         "priority": decision.priority, "confidence_threshold": s.ai_confidence_threshold,
                         "categories": sorted({reason_category(r) for r in decision.reasons}),
                         "error_kind": error_kind, "attempt_errors": attempt_errors},
        model_provider=provider.name if provider else "unavailable", model_identifier=provider.model if provider else "unavailable",
        prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION, processing_status="FAILED" if res is None else "SUCCEEDED",
        processing_error=error, processing_duration_ms=duration, processing_id=processing_id, attempt_count=calls,
    )
    db.add(ex)
    pod.proposed_delivery_date = _as_date(res.delivery_date.value) if res else None
    pod.review_reasons = decision.reasons
    pod.review_priority = decision.priority
    pod.last_processing_error = error
    _apply_decision(db, pod, trip, decision.decision, user_id, proposed_date=pod.proposed_delivery_date)
    audit(db, user_id, "pod", pod.id, "pod.ai_processed", None,
          {"decision": decision.decision, "reasons": decision.reasons},
          {"provider": ex.model_provider, "model": ex.model_identifier, "duration_ms": duration, "error": error,
           "error_kind": error_kind, "provider_calls": calls, "processing_id": processing_id})
    db.commit()
    log.info("pod.processing_finished", extra={
        "pod_id": str(pod.id), "extraction_id": str(ex.id), "decision": decision.decision, "reasons": decision.reasons,
        "categories": ex.validation_data["categories"], "duration_ms": duration, "attempts": calls,
        "provider": ex.model_provider, "error_kind": error_kind})
    return pod


def fail_to_review(db: Session, pod_id, user_id, reason: str, error: str, *, processing_id: str | None = None) -> Pod:
    """Last-resort exit from AI_PROCESSING: record a FAILED extraction and route to NEEDS_REVIEW. Idempotent."""
    pod = db.get(Pod, pod_id)
    db.refresh(pod)
    if pod.verification_status != "AI_PROCESSING":
        return pod
    s = get_settings()
    db.add(PodExtraction(
        pod_id=pod.id, extracted_data=None, confidence_data=None,
        validation_data={"checks": [{"check": "ai_processing", "status": "fail", "detail": f"System error, not a document problem: {error}"}],
                         "reasons": [reason], "decision": "NEEDS_REVIEW", "priority": "medium",
                         "confidence_threshold": s.ai_confidence_threshold, "categories": [reason_category(reason)],
                         "error_kind": error.split(":", 1)[0], "attempt_errors": []},
        model_provider="unavailable", model_identifier="unavailable", prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION,
        processing_status="FAILED", processing_error=error, processing_id=processing_id, attempt_count=0,
    ))
    pod.review_reasons = [reason]
    pod.review_priority = "medium"
    pod.last_processing_error = error
    pod_transition(pod, "NEEDS_REVIEW")
    pod.trip.trip_status = "POD_PENDING"
    audit(db, user_id, "pod", pod.id, "pod.ai_processing_failed", {"status": "AI_PROCESSING"}, {"status": "NEEDS_REVIEW", "reason": reason},
          {"error": error, "processing_id": processing_id, "attempts": pod.processing_attempts})
    db.commit()
    log.warning("pod.routed_to_review", extra={"pod_id": str(pod.id), "reasons": [reason], "error_kind": error.split(":", 1)[0]})
    return pod


def recover_stale(db: Session, now: datetime | None = None, requeue_limit: int = 20) -> dict:
    """Maintenance sweep for work a crash or restart left behind (FastAPI BackgroundTasks are not durable).

    * AI_PROCESSING older than AI_PROCESSING_STALE_MINUTES -> NEEDS_REVIEW (PROCESSING_STALLED); a reviewer can reprocess.
    * UPLOADED older than the same window (processing never started) -> processed now.
    """
    now = now or utcnow()
    cutoff = now - timedelta(minutes=get_settings().ai_processing_stale_minutes)
    stalled = db.scalars(select(Pod.id).where(
        Pod.verification_status == "AI_PROCESSING",
        or_(Pod.processing_started_at < cutoff, and_(Pod.processing_started_at.is_(None), Pod.server_received_at < cutoff)),
    )).all()
    for pid in stalled:
        try:
            fail_to_review(db, pid, None, "PROCESSING_STALLED",
                           f"stalled: no result within {get_settings().ai_processing_stale_minutes} minutes (worker restart or crash)")
        except Exception:
            db.rollback()
            log.exception("pod.recover_failed", extra={"pod_id": str(pid)})
    waiting = db.scalars(select(Pod.id).where(Pod.verification_status == "UPLOADED", Pod.server_received_at < cutoff)
                         .order_by(Pod.server_received_at).limit(requeue_limit)).all()
    requeued = 0
    for pid in waiting:
        try:
            process_pod(db, pid)
            requeued += 1
        except AppError:
            db.rollback()  # claimed by another worker in the meantime
    if stalled or waiting:
        log.info("pod.recovery_sweep", extra={"recovered": len(stalled), "requeued": requeued})
    return {"recovered": [str(p) for p in stalled], "requeued": requeued}


def _expected(trip: Trip) -> Expected:
    return Expected(trip.lr_number, trip.consignee_name, trip.delivery_date, trip.expected_quantity, trip.quantity_unit)


def _apply_decision(db: Session, pod: Pod, trip: Trip, decision: str, user_id, proposed_date: date | None) -> None:
    if decision == "RETAKE_REQUESTED":
        _retake(db, pod, trip, user_id, auto=True)
    elif decision == "VERIFIED":
        mark_verified(db, pod, trip, "ai", user_id, delivery_date=proposed_date)
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


def mark_verified(db: Session, pod: Pod, trip: Trip, method: str, user_id, *, delivery_date: date | None,
                  approved_exceptions: list[str] | None = None) -> None:
    """The only place a trip's delivery date is written from a POD: the verified document's date, by AI checks that
    passed (method=ai) or as confirmed by a reviewer (method=human)."""
    pod_transition(pod, "VERIFIED")
    pod.verification_method = method
    pod.verified_at = utcnow()
    pod.approved_exceptions = approved_exceptions or []
    trip.trip_status = "POD_VERIFIED"
    d = _as_date(delivery_date)
    if d:
        prev = trip.delivery_date
        trip.delivery_date = d
        trip.delivery_date_source = f"pod_{method}"
        trip.delivery_date_confirmed_at = pod.verified_at
        audit(db, user_id, "trip", trip.id, "trip.delivery_date_confirmed",
              {"delivery_date": prev.isoformat() if prev else None},
              {"delivery_date": d.isoformat(), "source": trip.delivery_date_source},
              {"pod_id": str(pod.id), "captured_at_client": aware(pod.captured_at).isoformat() if pod.captured_at else None,
               "server_received_at": aware(pod.server_received_at).isoformat() if pod.server_received_at else None,
               "changed": prev != d})
    became = sync_billing_status(trip)
    audit(db, user_id, "pod", pod.id, "pod.verified", None,
          {"method": method, "billing_ready": became, "approved_exceptions": pod.approved_exceptions})
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


def open_exceptions(pod: Pod, values: dict) -> list[str]:
    """Business exceptions on this POD: those the checks raised, plus any shortage/damage flag on the final values
    (a reviewer may not quietly clear or add one without it counting)."""
    found = {r for r in (pod.review_reasons or []) if r in EXCEPTION_REASONS}
    if values.get("shortage_detected"):
        found.add("SHORTAGE")
    if values.get("damage_detected"):
        found.add("DAMAGE")
    return sorted(found)


def review_pod(db: Session, pod: Pod, reviewer_id, *, decision: str, corrections: dict | None,
               correction_reason: str | None, rejection_reason: str | None, approval_reason: str | None = None) -> Pod:
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
        final = {**current, **corrected}
        confirmed = _as_date(final.get("delivery_date"))
        if not confirmed:
            raise BadRequest("delivery_date_required",
                             "Enter the delivery date shown on the POD before approving; it becomes the trip's delivery date")
        if confirmed > date.today() + timedelta(days=1):
            raise BadRequest("invalid_correction", "Delivery date cannot be in the future")
        exceptions = open_exceptions(pod, final)
        rationale = (approval_reason or "").strip()
        if exceptions and not rationale:
            raise BadRequest("approval_reason_required",
                             f"Approving with an open exception ({', '.join(exceptions)}) requires a review rationale",
                             {"exceptions": exceptions})
        row = PodReview(pod_id=pod.id, reviewer_id=reviewer_id, original_values={k: original.get(k) for k in corrected} or original,
                        corrected_values=corrected or None, correction_reason=correction_reason, decision="APPROVED",
                        approval_reason=rationale or None, accepted_exceptions=exceptions or None)
        db.add(row)
        if corrected:
            audit(db, reviewer_id, "pod", pod.id, "pod.fields_corrected",
                  {k: current.get(k) for k in corrected}, corrected, {"reason": correction_reason, "ai_original": {k: original.get(k) for k in corrected}})
        if exceptions:
            audit(db, reviewer_id, "pod", pod.id, "pod.exception_approved", None, {"exceptions": exceptions},
                  {"rationale": rationale, "ai_flags": {"shortage_detected": original.get("shortage_detected"),
                                                         "damage_detected": original.get("damage_detected")},
                   "final_flags": {"shortage_detected": final.get("shortage_detected"), "damage_detected": final.get("damage_detected")}})
        mark_verified(db, pod, trip, "human", reviewer_id, delivery_date=confirmed, approved_exceptions=exceptions)
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
