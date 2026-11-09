"""Deterministic post-extraction validation and routing. Model confidence alone never approves a document."""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from difflib import SequenceMatcher
from decimal import Decimal

from app.services.ai.schema import PodExtractionResult

# Every field here must be read reliably before a POD can be auto-verified, even when the trip record has nothing to
# compare it with (e.g. no expected quantity): "cannot compare" is not the same as "cannot read".
CRITICAL_FIELDS = ("lr_number", "consignee", "delivered_quantity", "delivery_date")

# Reason categories keep the review queue honest about *why* a document is there:
#   system           - our side failed (provider timeout, crash, stalled job). Says nothing about the delivery.
#   document_quality - the photo/document could not be read reliably. Usually fixed by a retake.
#   business         - the document was read and shows a real exception (shortage, damage, wrong LR, ...).
SYSTEM, QUALITY, BUSINESS = "system", "document_quality", "business"
CATEGORIES = (SYSTEM, QUALITY, BUSINESS)

# reason code -> (routing bucket, priority, category)
REASONS = {
    "AI_ERROR": ("review", "medium", SYSTEM),
    "PROCESSING_STALLED": ("review", "medium", SYSTEM),
    "LR_MISMATCH": ("review", "high", BUSINESS),
    "CONSIGNEE_MISMATCH": ("review", "high", BUSINESS),
    "SHORTAGE": ("review", "high", BUSINESS),
    "DAMAGE": ("review", "high", BUSINESS),
    "QUANTITY_MISMATCH": ("review", "high", BUSINESS),
    "DATE_IMPLAUSIBLE": ("review", "medium", BUSINESS),
    "DATE_DIFFERS_FROM_TRIP": ("review", "low", BUSINESS),
    "LOW_CONFIDENCE": ("review", "medium", QUALITY),
    "QUANTITY_UNREADABLE": ("review", "medium", QUALITY),
    "MISSING_FIELD": ("retake", "medium", QUALITY),
    "UNREADABLE": ("retake", "medium", QUALITY),
    "STAMP_NOT_VISIBLE": ("retake", "low", QUALITY),
    "SIGNATURE_NOT_VISIBLE": ("retake", "low", QUALITY),
    "RETAKE_LIMIT_REACHED": ("review", "medium", QUALITY),
}

# Business exceptions a reviewer may accept, but only with a recorded rationale.
EXCEPTION_REASONS = ("SHORTAGE", "DAMAGE", "QUANTITY_MISMATCH")


def reason_category(code: str) -> str:
    return REASONS.get(code, ("review", "medium", QUALITY))[2]


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


def _fold(s: str | None) -> str:
    """Unicode-aware folding for OCR'd text in any script (Latin, Devanagari, ...).

    NFKC unifies compatibility forms (full-width letters, ligatures), casefold handles case beyond ASCII, any Unicode
    decimal digit (e.g. Devanagari digits) becomes its ASCII digit, and diacritics on Latin letters are dropped.
    Combining marks on other scripts are kept: in Devanagari the vowel signs carry meaning and must not be stripped.
    """
    s = unicodedata.normalize("NFKC", s or "").casefold()
    out: list[str] = []
    for ch in unicodedata.normalize("NFD", s):
        if unicodedata.category(ch) == "Nd":
            out.append(str(unicodedata.decimal(ch)))
        elif unicodedata.combining(ch) and out and out[-1].isascii():
            continue  # accent on a Latin letter, e.g. "e" + combining acute -> "e"
        else:
            out.append(ch)
    return unicodedata.normalize("NFC", "".join(out))


def _norm_id(s: str | None) -> str:
    """Identifier comparison (LR numbers): letters, digits and marks of any script, case-insensitive."""
    return "".join(ch for ch in _fold(s) if ch.isalnum() or unicodedata.category(ch).startswith("M"))


_LR_PREFIXES = ("LRNO", "LRN", "LR", "NO")


def lr_core(s: str | None) -> str:
    """LR identity without the label printed around it: "LR No. 66141", "lr-66141" and "66141" all -> "66141".
    Only the LR/No. label is stripped; any other letters (series codes such as "CN" or "/2026/") stay significant."""
    n = _norm_id(s).upper()
    for p in _LR_PREFIXES:
        if n.startswith(p) and len(n) > len(p):
            return n[len(p):]
    return n


def _norm_name(s: str | None) -> str:
    """Name comparison: keep word characters of any script, collapse punctuation/whitespace to single spaces."""
    # Letters (L*), digits (N*) and combining marks (M*: Indic vowel signs, viramas) are kept for every script.
    kept = "".join(ch if unicodedata.category(ch)[0] in "LNM" else " " for ch in _fold(s))
    return " ".join(kept.split())


def name_similarity(a: str | None, b: str | None) -> float:
    a, b = _norm_name(a), _norm_name(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


# Canonical unit names. Anything not listed is compared by its folded form.
_UNIT_ALIASES = {
    "carton": {"carton", "cartons", "ctn", "ctns", "cs", "case", "cases", "box", "boxes"},
    "bag": {"bag", "bags", "bg", "bgs", "sack", "sacks"},
    "coil": {"coil", "coils"},
    "piece": {"piece", "pieces", "pc", "pcs", "nos", "no", "number", "numbers", "unit", "units"},
    "kg": {"kg", "kgs", "kilogram", "kilograms", "kilo", "kilos"},
    "tonne": {"t", "mt", "ton", "tons", "tonne", "tonnes", "metricton", "metrictons"},
    "litre": {"l", "ltr", "ltrs", "litre", "litres", "liter", "liters"},
}
_UNIT_LOOKUP = {alias: canon for canon, aliases in _UNIT_ALIASES.items() for alias in aliases}


def normalize_unit(u: str | None) -> str | None:
    """Canonical unit name, or None when no unit was given."""
    key = re.sub(r"[\W\d_]+", "", _fold(u))
    if not key:
        return None
    return _UNIT_LOOKUP.get(key) or _UNIT_LOOKUP.get(key.rstrip("s")) or key.rstrip("s")


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
        # A provider/system failure says nothing about the delivery itself: keep it distinct from document problems.
        add("ai_processing", "fail", f"System error, not a document problem: {error or 'AI processing failed'}", "AI_ERROR")
        return _route(reasons, checks, retakes_used, max_retakes)

    if not res.document_readable:
        add("legibility", "fail", "Document not readable", "UNREADABLE")
        return _route(reasons, checks, retakes_used, max_retakes)

    # LR number
    if not res.lr_number.value:
        add("lr_number", "missing", "LR number not found on document", "MISSING_FIELD")
    elif lr_core(res.lr_number.value) == lr_core(exp.lr_number):
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
            elif exp.delivery_date and d != exp.delivery_date:
                # Two sources disagree (trip record vs. consignee's document). Never pick one silently: the confirmed
                # date becomes the billing evidence, so a person decides.
                add("delivery_date", "fail", f"Document says {d} but the trip record says {exp.delivery_date}", "DATE_DIFFERS_FROM_TRIP")
            elif exp.delivery_date:
                add("delivery_date", "pass", f"Matches trip delivery date {exp.delivery_date}")
            else:
                add("delivery_date", "pass", "Date is plausible (no delivery date on the trip record yet)")
        except ValueError:
            add("delivery_date", "fail", "Date is not a valid calendar date", "DATE_IMPLAUSIBLE")

    # Quantity answers two independent questions:
    #   1. reading    - could we read the delivered quantity (value + unit) reliably? Always required.
    #   2. comparison - does it match the trip record? Only when the trip has an expected quantity.
    q = res.delivered_quantity
    q_unit = normalize_unit(q.unit)
    exp_unit = normalize_unit(exp.quantity_unit)
    if q.value is None:
        add("quantity_reading", "missing", "Delivered quantity could not be read from the document", "QUANTITY_UNREADABLE")
    elif q.confidence < threshold:
        add("quantity_reading", "fail",
            f"Delivered quantity read as {q.value:g} but confidence {q.confidence:.2f} is below {threshold:.2f}", "QUANTITY_UNREADABLE")
    elif q_unit is None:
        add("quantity_reading", "fail", f"Delivered quantity {q.value:g} has no readable unit", "QUANTITY_UNREADABLE")
    else:
        add("quantity_reading", "pass", f"Read {q.value:g} {q_unit} at {q.confidence:.2f} confidence")

    if exp.expected_quantity is None:
        add("quantity", "na", "No expected quantity on trip record; not compared (the reading is still validated)")
    elif q.value is None:
        add("quantity", "missing", "Delivered quantity not read; cannot compare with the trip record")
    elif exp_unit and q_unit and q_unit != exp_unit:
        add("quantity", "fail", f"Unit '{q.unit}' ({q_unit}) differs from expected '{exp.quantity_unit}' ({exp_unit})", "QUANTITY_MISMATCH")
    elif Decimal(str(q.value)) != exp.expected_quantity:
        add("quantity", "fail", f"Delivered {q.value:g} vs expected {exp.expected_quantity}", "QUANTITY_MISMATCH")
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

    # Confidence on critical fields (configurable threshold). Missing values are reported by their own checks above, and
    # quantity confidence is reported by quantity_reading, so neither is double-counted here.
    low = [f for f in CRITICAL_FIELDS if f != "delivered_quantity"
           and getattr(res, f).value is not None and getattr(res, f).confidence < threshold]
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
