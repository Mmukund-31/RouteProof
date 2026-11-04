from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.errors import AppError
from app.services.ai.mock import result
from app.services.ai.schema import PodExtractionResult
from app.services.ai.validation import Expected, evaluate
from app.services.billing.csv_export import COLUMNS, safe_cell
from app.services.pods.state import POD_TRANSITIONS, can_pod, can_request_retake

EXP = Expected("LR-66141", "Indore Warehouse", date(2026, 11, 3), Decimal(100), "cartons")
TODAY = date(2026, 11, 4)


def ev(res, retakes=0, error=None, thr=0.85):
    return evaluate(res, EXP, threshold=thr, retakes_used=retakes, max_retakes=2, today=TODAY, error=error)


def good(**kw):
    base = dict(lr="LR-66141", consignee="Indore Warehouse", qty=100, unit="cartons", date="2026-11-03")
    base.update(kw)
    return result(**base)


def test_clean_document_is_verified():
    d = ev(good())
    assert d.decision == "VERIFIED" and d.reasons == []


@pytest.mark.parametrize("kw,reason", [
    (dict(shortage=True, remarks="Short by 6 cartons", qty=94), "SHORTAGE"),
    (dict(damage=True, remarks="damaged"), "DAMAGE"),
    (dict(lr="LR-99999"), "LR_MISMATCH"),
    (dict(consignee="Totally Different Ltd"), "CONSIGNEE_MISMATCH"),
    (dict(conf=0.7), "LOW_CONFIDENCE"),
    (dict(date="2027-01-01"), "DATE_IMPLAUSIBLE"),
    (dict(qty=94), "QUANTITY_MISMATCH"),
])
def test_review_routes(kw, reason):
    d = ev(good(**kw))
    assert d.decision == "NEEDS_REVIEW" and reason in d.reasons


def test_lr_normalisation_ignores_punctuation_and_case():
    assert ev(good(lr="lr 66141")).decision == "VERIFIED"


def test_threshold_is_configurable():
    assert ev(good(conf=0.8), thr=0.85).decision == "NEEDS_REVIEW"
    assert ev(good(conf=0.8), thr=0.75).decision == "VERIFIED"


def test_missing_stamp_requests_retake_then_review_after_cap():
    assert ev(good(stamp=False), retakes=0).decision == "RETAKE_REQUESTED"
    assert ev(good(stamp=False), retakes=1).decision == "RETAKE_REQUESTED"
    d = ev(good(stamp=False), retakes=2)
    assert d.decision == "NEEDS_REVIEW" and "RETAKE_LIMIT_REACHED" in d.reasons


def test_missing_lr_is_retake_not_approval():
    d = ev(good(lr=None))
    assert d.decision == "RETAKE_REQUESTED" and "MISSING_FIELD" in d.reasons


def test_unreadable_and_provider_error():
    assert ev(result(readable=False)).decision == "RETAKE_REQUESTED"
    d = ev(None, error="timeout: AI provider timed out")
    assert d.decision == "NEEDS_REVIEW" and d.reasons == ["AI_ERROR"]


def test_quantity_not_compared_without_expected_quantity():
    exp = Expected("LR-1", "X", None, None, None)
    d = evaluate(result(qty=5, unit="bags"), exp, threshold=0.85, retakes_used=0, max_retakes=2, today=TODAY)
    q = next(c for c in d.checks if c["check"] == "quantity")
    assert q["status"] == "na" and d.decision == "VERIFIED"


def test_high_confidence_alone_never_overrides_mismatch():
    assert ev(good(lr="LR-1", conf=0.99)).decision == "NEEDS_REVIEW"


def test_schema_rejects_extra_and_out_of_range():
    ok = good().model_dump()
    with pytest.raises(ValidationError):
        PodExtractionResult.model_validate({**ok, "invented": 1})
    ok["lr_number"]["confidence"] = 1.5
    with pytest.raises(ValidationError):
        PodExtractionResult.model_validate(ok)


def test_state_machine():
    assert can_pod("UPLOADED", "AI_PROCESSING")
    assert not can_pod("UPLOADED", "VERIFIED")  # cannot skip AI processing / review
    assert not can_pod("VERIFIED", "REJECTED")
    assert POD_TRANSITIONS["RETAKE_REQUESTED"] == set()
    assert can_request_retake(1, 2) and not can_request_retake(2, 2)


def test_csv_formula_injection_is_neutralised():
    assert safe_cell("=SUM(A1)") == "'=SUM(A1)"
    assert safe_cell("+91") == "'+91" and safe_cell("normal") == "normal" and safe_cell(None) == ""
    assert "freight_amount_inr" in COLUMNS
