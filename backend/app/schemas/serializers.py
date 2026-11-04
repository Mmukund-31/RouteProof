from app.core.config import get_settings
from app.models import Pod, Trip, aware
from app.services.pods.service import effective_values, flat_values, latest_extraction, latest_pod, pod_status_for_trip


def trip_out(t: Trip, *, driver_view: bool = False) -> dict:
    p = latest_pod(t)
    out = {
        "id": str(t.id), "trip_reference": t.trip_reference, "lr_number": t.lr_number, "eway_bill_number": t.eway_bill_number,
        "client": {"id": str(t.client.id), "name": t.client.company_name, "code": t.client.client_code},
        "vehicle": {"registration": t.vehicle.registration_number, "type": t.vehicle.vehicle_type, "ownership": t.vehicle.ownership_type},
        "driver": {"id": str(t.driver.id), "name": t.driver.name} if t.driver else None,
        "origin": t.origin, "destination": t.destination, "branch": t.branch, "commodity": t.commodity,
        "consignee_name": t.consignee_name,
        "expected_quantity": float(t.expected_quantity) if t.expected_quantity is not None else None,
        "quantity_unit": t.quantity_unit,
        "delivery_date": t.delivery_date.isoformat() if t.delivery_date else None,
        "trip_status": t.trip_status, "pod_status": p.verification_status if p else "PENDING",
        "latest_pod_id": str(p.id) if p else None,
        "retakes_remaining": max(get_settings().max_retake_requests - (p.retake_count if p else 0), 0),
        "rejection_reason": p.rejection_reason if p and p.verification_status == "REJECTED" else None,
    }
    if not driver_view:  # drivers do not need commercial data (data minimisation)
        out.update(freight_amount=f"{t.freight_amount:.2f}", billing_status=t.billing_status,
                   billing_cycle=t.billing_cycle, invoice_reference=t.invoice_reference)
    return out


def _extraction_out(ex) -> dict | None:
    if not ex:
        return None
    return {
        "id": str(ex.id), "extracted_data": ex.extracted_data, "confidence_data": ex.confidence_data,
        "validation_data": ex.validation_data, "model_provider": ex.model_provider, "model_identifier": ex.model_identifier,
        "prompt_version": ex.prompt_version, "schema_version": ex.schema_version, "processing_status": ex.processing_status,
        "processing_error": ex.processing_error, "processing_duration_ms": ex.processing_duration_ms,
        "created_at": aware(ex.created_at).isoformat(),
    }


def pod_out(p: Pod, *, driver_view: bool = False) -> dict:
    ex = latest_extraction(p)
    out = {
        "id": str(p.id), "trip_id": str(p.trip_id), "attempt_number": p.attempt_number,
        "verification_status": p.verification_status, "upload_status": p.upload_status, "source": p.source,
        "captured_at": aware(p.captured_at).isoformat() if p.captured_at else None,
        "captured_at_note": "Reported by the capturing device; not independently verified",
        "server_received_at": aware(p.server_received_at).isoformat(),
        "latitude": float(p.latitude) if p.latitude is not None else None,
        "longitude": float(p.longitude) if p.longitude is not None else None,
        "location_accuracy": p.location_accuracy, "location_note": "Device-reported GPS; not proof of presence",
        "retake_count": p.retake_count,
        "retakes_remaining": max(get_settings().max_retake_requests - p.retake_count, 0),
        "review_reasons": p.review_reasons or [], "review_priority": p.review_priority,
        "verification_method": p.verification_method,
        "verified_at": aware(p.verified_at).isoformat() if p.verified_at else None,
        "rejection_reason": p.rejection_reason, "image_url": f"/api/v1/pods/{p.id}/image",
        "has_separate_original": bool(p.original_image_path and p.original_image_path != p.uploaded_image_path),
        "trip": trip_out(p.trip, driver_view=driver_view),
    }
    if driver_view:
        return out
    out.update(
        extraction=_extraction_out(ex),
        original_values=flat_values(ex.extracted_data) if ex else {},
        effective_values=effective_values(p),
        expected={
            "lr_number": p.trip.lr_number, "consignee": p.trip.consignee_name,
            "delivery_date": p.trip.delivery_date.isoformat() if p.trip.delivery_date else None,
            "expected_quantity": float(p.trip.expected_quantity) if p.trip.expected_quantity is not None else None,
            "quantity_unit": p.trip.quantity_unit,
        },
        extractions_history=[_extraction_out(e) for e in p.extractions],
        reviews=[{"id": str(r.id), "reviewer_id": str(r.reviewer_id), "decision": r.decision, "original_values": r.original_values,
                  "corrected_values": r.corrected_values, "correction_reason": r.correction_reason,
                  "reviewed_at": aware(r.reviewed_at).isoformat()} for r in p.reviews],
        confidence_threshold=get_settings().ai_confidence_threshold,
    )
    return out


def page(items: list, total: int, page_no: int, size: int) -> dict:
    return {"items": items, "total": total, "page": page_no, "page_size": size}
