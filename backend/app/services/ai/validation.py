"""Deterministic post-extraction validation and routing. Model confidence alone never approves a document."""
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from difflib import SequenceMatcher
from decimal import Decimal

from app.services.ai.schema import PodExtractionResult

CRITICAL_FIELDS = ("lr_number", "consignee", "delivery_date")

# reason code -> (routing bucket, priority)
REASONS = {
    "AI_ERROR": ("review", "medium"),
    "LR_MISMATCH": ("review", "high"),
    "CONSIGNEE_MISMATCH": ("review", "high"),
    "SHORTAGE": ("review", "high"),
    "DAMAGE": ("review", "high"),
    "QUANTITY_MISMATCH": ("review", "high"),
    "LOW_CONFIDENCE": ("review", "medium"),
    "DATE_IMPLAUSIBLE": ("review", "medium"),
    "MISSING_FIELD": ("retake", "medium"),
    "UNREADABLE": ("retake", "medium"),
    "STAMP_NOT_VISIBLE": ("retake", "low"),
    "SIGNATURE_NOT_VISIBLE": ("retake", "low"),
}


@dataclass
class Expected:
    lr_number: str
    consignee_name: str | None
    delivery_date: date | None
    expected_quantity: Decimal | None
    quantity_unit: str | None


@dataclass
class Decision:
    decision: str  # VERIFIED | NEEDS_REVIEW | RETAKE_REQUESTED
    reasons: list[str] = field(default_factory=list)
    priority: str | None = None
    checks: list[dict] = field(default_factory=list)


def _norm_id(s: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _norm_name(s: str | None) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()


def name_similarity(a: str | None, b: str | None) -> float:
    a, b = _norm_name(a), _norm_name(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _norm_unit(u: str | None) -> str:
    return re.sub(r"[^a-z]", "", (u or "").lower()).rstrip("s")


def evaluate(res: PodExtractionResult | None, exp: Expected, *, threshold: float, retakes_used: int,
             max_retakes: int, today: date, error: str | None = None) -> Decision:
    checks: list[dict] = []
    reasons: list[str] = []

    def add(check, status, detail, reason=None):
        checks.append({"check": check, "status": status, "detail": detail})
        if reason and reason not in reasons:
            reasons.append(reason)

    if res is None and error and error.startswith("unreadable"):
        add("legibility", "fail", "Image appears blank or unreadable", "UNREADABLE")
        return _route(reasons, checks, retakes_used, max_retakes)

    if res is None:
        add("ai_processing", "fail", error or "AI processing failed", "AI_ERROR")
        return _route(reasons, checks, retakes_used, max_retakes)

    if not res.document_readable:
        add("legibility", "fail", "Document not readable", "UNREADABLE")
        return _route(reasons, checks, retakes_used, max_retakes)

    # LR number
    if not res.lr_number.value:
        add("lr_number", "missing", "LR number not found on document", "MISSING_FIELD")
    elif _norm_id(res.lr_number.value) == _norm_id(exp.lr_number):
        add("lr_number", "pass", f"Matches trip LR {exp.lr_number}")
    else:
        add("lr_number", "fail", f"Extracted {res.lr_number.value} but trip LR is {exp.lr_number}", "LR_MISMATCH")

    # Consignee
    if not res.consignee.value:
        add("consignee", "missing", "Consignee not found on document", "MISSING_FIELD")
    elif not exp.consignee_name:
        add("consignee", "na", "No expected consignee on trip record")
    else:
        sim = name_similarity(res.consignee.value, exp.consignee_name)
        if sim >= 0.7:
            add("consignee", "pass", f"Matches expected consignee ({sim:.0%} similarity)")
        else:
            add("consignee", "fail", f"Extracted '{res.consignee.value}' vs expected '{exp.consignee_name}'", "CONSIGNEE_MISMATCH")

    # Delivery date plausibility
    if not res.delivery_date.value:
        add("delivery_date", "missing", "Delivery date not found", "MISSING_FIELD")
    else:
        try:
            d = date.fromisoformat(res.delivery_date.value)
            lo = (exp.delivery_date - timedelta(days=7)) if exp.delivery_date else None
            hi = (exp.delivery_date + timedelta(days=30)) if exp.delivery_date else None
            if d > today + timedelta(days=1):
                add("delivery_date", "fail", "Delivery date is in the future", "DATE_IMPLAUSIBLE")
            elif lo and not (lo <= d <= hi):
                add("delivery_date", "fail", f"Date {d} outside plausible window around trip delivery date {exp.delivery_date}", "DATE_IMPLAUSIBLE")
            else:
                add("delivery_date", "pass", "Date is plausible")
        except ValueError:
            add("delivery_date", "fail", "Date is not a valid calendar date", "DATE_IMPLAUSIBLE")

    # Quantity: only compared when the trip record actually has an expected quantity.
    q = res.delivered_quantity
    if exp.expected_quantity is None:
        add("quantity", "na", "No expected quantity on trip record; not compared")
    elif q.value is None:
        add("quantity", "missing", "Delivered quantity not found", "MISSING_FIELD")
    else:
        unit_ok = (not exp.quantity_unit) or (not q.unit) or _norm_unit(q.unit) == _norm_unit(exp.quantity_unit)
        if not unit_ok:
            add("quantity", "fail", f"Unit '{q.unit}' differs from expected '{exp.quantity_unit}'", "QUANTITY_MISMATCH")
        elif Decimal(str(q.value)) != exp.expected_quantity:
            add("quantity", "fail", f"Delivered {q.value} vs expected {exp.expected_quantity}", "QUANTITY_MISMATCH")
        else:
            add("quantity", "pass", "Delivered quantity equals expected quantity")

    # Remarks policy: any shortage or damage remark forces human review.
    if res.shortage_detected:
        add("shortage", "fail", f"Shortage remark: {res.remarks or 'flagged'}", "SHORTAGE")
    else:
        add("shortage", "pass", "No shortage remark detected")
    if res.damage_detected:
        add("damage", "fail", f"Damage remark: {res.remarks or 'flagged'}", "DAMAGE")
    else:
        add("damage", "pass", "No damage remark detected")

    # Visibility only (not authenticity).
    for key, label, code in (("stamp_visible", "Consignee stamp", "STAMP_NOT_VISIBLE"),
                             ("signature_visible", "Signature", "SIGNATURE_NOT_VISIBLE")):
        v = getattr(res, key)
        if v is True:
            add(key, "pass", f"{label} appears visible (authenticity is not verified)")
        else:
            add(key, "fail", f"{label} not visible" if v is False else f"{label} visibility unknown", code)

    # Confidence on critical fields (configurable threshold).
    low = [f for f in CRITICAL_FIELDS if getattr(res, f).value and getattr(res, f).confidence < threshold]
    if low:
        add("confidence", "fail", f"Below {threshold:.2f} on: {', '.join(low)}", "LOW_CONFIDENCE")
    else:
        add("confidence", "pass", f"Critical fields at or above {threshold:.2f}")

    return _route(reasons, checks, retakes_used, max_retakes)


def _route(reasons, checks, retakes_used, max_retakes) -> Decision:
    if not reasons:
        return Decision("VERIFIED", [], None, checks)
    buckets = {REASONS[r][0] for r in reasons}
    prio_rank = {"low": 0, "medium": 1, "high": 2}
    priority = max((REASONS[r][1] for r in reasons), key=lambda p: prio_rank[p])
    if "review" in buckets:
        return Decision("NEEDS_REVIEW", reasons, priority, checks)
    if retakes_used < max_retakes:
        return Decision("RETAKE_REQUESTED", reasons, priority, checks)
    return Decision("NEEDS_REVIEW", reasons + ["RETAKE_LIMIT_REACHED"], priority, checks)
