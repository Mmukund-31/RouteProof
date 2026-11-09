"""Labelled POD evaluation set: routing regression (always) and extraction evaluation (opt-in, real model)."""
import io
import os

import pytest
from PIL import Image

from app.services.ai import eval_set as ev
from app.services.ai.base import AIProviderError


@pytest.mark.parametrize("case", ev.CASES, ids=[c.id for c in ev.CASES])
def test_correct_reading_routes_as_labelled(case):
    """Business rules pinned per document type: a perfect reading must produce the labelled decision."""
    d = ev.route(case, ev.oracle_extraction(case))
    assert d.decision == case.expected_decision, (case.id, d.reasons)
    assert set(case.expected_reasons) <= set(d.reasons), (case.id, d.reasons)


def test_set_covers_every_required_variation():
    covered = {t for c in ev.CASES for t in c.tags}
    assert ev.REQUIRED_TAGS <= covered, ev.REQUIRED_TAGS - covered
    assert len({c.id for c in ev.CASES}) == len(ev.CASES)


def test_low_confidence_never_auto_verifies_anything():
    """Lowering certainty must only ever move documents towards people, never towards auto-verification."""
    for c in ev.CASES:
        assert ev.route(c, ev.oracle_extraction(c, confidence=0.6)).decision != "VERIFIED", c.id


@pytest.mark.parametrize("case", ev.CASES[:: max(1, len(ev.CASES) // 8)], ids=lambda c: c.id)
def test_cases_render_to_valid_jpeg(case):
    data = ev.render_case(case)
    with Image.open(io.BytesIO(data)) as im:
        assert im.format == "JPEG" and im.width > 500


class _Perfect:
    name, model = "oracle", "oracle"

    def __init__(self, misread=()):
        self.misread = set(misread)

    def analyze_pod(self, image, media_type, ctx):
        case = next(c for c in ev.CASES if f"EVAL-{c.id}" == ctx.trip_reference)
        if case.id in self.misread:  # confidently wrong quantity: the dangerous kind of error
            r = ev.oracle_extraction(case)
            r.delivered_quantity.value = (r.delivered_quantity.value or 0) + 6
            return r
        if case.id == "photo_tilted" and "timeout" in self.misread:
            raise AIProviderError("timeout", "slow")
        return ev.oracle_extraction(case)


def test_harness_reports_extraction_and_routing_separately():
    images = {c.id: b"x" for c in ev.CASES}  # skip rendering: the fake provider reads the case directly
    perfect = ev.run(_Perfect(), images=images)["summary"]
    assert perfect["routing_agreement"] == 1.0 and perfect["false_auto_verified"] == []
    assert perfect["auto_verified_with_misread_fields"] == []
    assert all(v == 1.0 for v in perfect["field_accuracy"].values())
    assert perfect["auto_verification_rate"] == perfect["expected_auto_verification_rate"]

    flawed = ev.run(_Perfect(misread={"qty_no_expected", "printed_clean", "timeout"}), images=images)["summary"]
    assert flawed["field_accuracy"]["delivered_quantity"] < 1.0
    # A wrong quantity on a trip with an expected quantity is caught by routing; with nothing to compare it to, routing
    # still "agrees" - only the extraction metric exposes it. That is why the two are reported separately.
    assert "printed_clean" not in flawed["auto_verified_with_misread_fields"]
    assert flawed["auto_verified_with_misread_fields"] == ["qty_no_expected"] and flawed["false_auto_verified"] == []
    assert flawed["provider_errors"] == ["photo_tilted"]


def test_manifest_loader(tmp_path):
    img = tmp_path / "a.jpg"
    Image.new("RGB", (10, 10)).save(img)
    (tmp_path / "m.json").write_text('[{"id": "a", "image": "a.jpg", "expected_decision": "VERIFIED", '
                                     '"printed": {"lr": "LR-1", "consignee": "X", "qty": 5, "unit": "bags", "date": "2026-11-01"}, '
                                     '"trip": {"lr": "LR-1", "consignee": "X", "delivery_date": "2026-11-01", "expected_qty": 5, "unit": "bags"}}]')
    cases, images = ev.load_manifest(tmp_path / "m.json")
    assert cases[0].trip.expected_qty == 5 and images["a"] == img.read_bytes()


@pytest.mark.skipif(not os.environ.get("RUN_LIVE_AI_EVAL"), reason="set RUN_LIVE_AI_EVAL=1 (and AI_API_KEY) to run against the real model")
def test_live_model_never_auto_verifies_an_exception():
    from app.services.ai.claude import ClaudeVisionProvider

    report = ev.run(ClaudeVisionProvider(api_key=os.environ["AI_API_KEY"]))
    assert report["summary"]["false_auto_verified"] == [], report["summary"]
    assert report["summary"]["auto_verified_with_misread_fields"] == [], report["summary"]
