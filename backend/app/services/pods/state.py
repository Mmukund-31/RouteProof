"""Explicit POD / trip / billing state machines. All transitions are validated here and audited by callers."""
from app.core.errors import Conflict

POD_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"UPLOADED"},
    "UPLOADED": {"AI_PROCESSING"},
    "AI_PROCESSING": {"VERIFIED", "NEEDS_REVIEW", "RETAKE_REQUESTED"},
    "NEEDS_REVIEW": {"VERIFIED", "REJECTED", "RETAKE_REQUESTED", "AI_PROCESSING"},  # AI_PROCESSING = manual reprocess
    "RETAKE_REQUESTED": set(),  # the next attempt is a new POD row that starts at UPLOADED
    "VERIFIED": set(),
    "REJECTED": set(),
}

BILLING_TRANSITIONS: dict[str, set[str]] = {
    "NOT_READY": {"BILLING_READY"},
    "BILLING_READY": {"EXPORTED", "NOT_READY"},
    "EXPORTED": {"EXPORTED", "INVOICED", "BILLING_READY"},  # EXPORTED->EXPORTED = explicit re-export
    "INVOICED": set(),
}


def can_pod(frm: str, to: str) -> bool:
    return to in POD_TRANSITIONS.get(frm, set())


def pod_transition(pod, to: str) -> str:
    frm = pod.verification_status
    if not can_pod(frm, to):
        raise Conflict("invalid_transition", f"POD cannot move from {frm} to {to}", {"from": frm, "to": to})
    pod.verification_status = to
    return frm


_MILESTONE = {"BILLING_READY": "billing_ready_at", "EXPORTED": "exported_at", "INVOICED": "invoiced_at"}


def billing_transition(trip, to: str, at=None) -> str:
    """Move billing status and stamp the milestone time (first time only, so re-exports keep the original clock)."""
    from app.models import utcnow

    frm = trip.billing_status
    if to not in BILLING_TRANSITIONS.get(frm, set()):
        raise Conflict("invalid_transition", f"Billing status cannot move from {frm} to {to}", {"from": frm, "to": to})
    trip.billing_status = to
    attr = _MILESTONE.get(to)
    if attr and getattr(trip, attr, None) is None:
        setattr(trip, attr, at or utcnow())
    return frm


def can_request_retake(retake_count: int, max_retakes: int) -> bool:
    return retake_count < max_retakes
