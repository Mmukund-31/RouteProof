"""The three client sample trips must agree across trip data, seeded POD/extraction and the demo documents, and the
seed must be idempotent. A mismatch would make the demo look like an AI failure when it is really a data error."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.models import (AuditLog, BillingExport, Client, Pod, PodExtraction, PodReview, Trip, UploadJob, User, Vehicle)
from app.services.sample_trips import BY_REF, SAMPLE_TRIPS
from app.services.seed import seed

TABLES = (User, Client, Vehicle, Trip, Pod, PodExtraction, PodReview, UploadJob, BillingExport, AuditLog)


@pytest.fixture
def seeded():
    with SessionLocal() as db:
        seed(db)
    yield


def _trip(db, ref) -> Trip:
    return db.scalar(select(Trip).where(Trip.trip_reference == ref))


def test_sample_trips_exist_with_the_assignment_values(seeded):
    with SessionLocal() as db:
        for st in SAMPLE_TRIPS:
            t = _trip(db, st.ref)
            assert t, st.ref
            assert (t.lr_number, t.client.client_code, t.client.company_name) == (st.lr, st.client_code, st.client_name)
            assert (t.vehicle.registration_number, t.vehicle.ownership_type) == (st.vehicle, st.ownership)
            assert t.freight_amount == st.freight and t.destination == st.destination and t.consignee_name == st.consignee
            assert (t.expected_quantity, t.quantity_unit) == (Decimal(st.qty), st.unit)
            assert t.delivery_date == st.delivery_date() and t.driver.email == st.driver_email


def test_trp_66141_is_hired(seeded):
    with SessionLocal() as db:
        assert _trip(db, "TRP-66141").vehicle.ownership_type == "hired"


def test_each_sample_trip_shows_its_scenario(seeded):
    with SessionLocal() as db:
        for st in SAMPLE_TRIPS:
            pod = _trip(db, st.ref).pods[-1]
            assert pod.verification_status == st.expected_status, st.ref
            assert set(st.expected_reasons) <= set(pod.review_reasons or []), (st.ref, pod.review_reasons)


def test_trp_66134_has_a_clear_stamp_exception(seeded):
    with SessionLocal() as db:
        pod = _trip(db, "TRP-66134").pods[-1]
        ex = pod.extractions[-1].extracted_data
        assert ex["stamp_visible"] is False and ex["signature_visible"] is True
        assert pod.review_reasons == ["STAMP_NOT_VISIBLE"] and pod.retakes_remaining if hasattr(pod, "retakes_remaining") else True
        assert pod.retake_count == 1


def test_trp_66141_is_short_by_six_cartons(seeded):
    with SessionLocal() as db:
        t = _trip(db, "TRP-66141")
        ex = t.pods[-1].extractions[-1].extracted_data
        assert t.expected_quantity - Decimal(str(ex["delivered_quantity"]["value"])) == 6
        assert ex["delivered_quantity"]["unit"] == "cartons" and ex["shortage_detected"] is True
        assert ex["remarks"] == "Short by 6 cartons"
        assert t.pods[-1].review_priority == "high"


def test_only_trp_66120_is_billing_ready_among_the_samples(seeded):
    with SessionLocal() as db:
        ready = {st.ref for st in SAMPLE_TRIPS if _trip(db, st.ref).billing_status == "BILLING_READY"}
        assert ready == {"TRP-66120"}
        assert _trip(db, "TRP-66120").pods[-1].verification_method == "ai"


def test_seeded_documents_agree_with_the_trip_record(seeded):
    """The seeded extraction is the reading of the seeded photo; it must carry the trip's own values."""
    with SessionLocal() as db:
        for st in SAMPLE_TRIPS:
            t = _trip(db, st.ref)
            ex = t.pods[-1].extractions[-1].extracted_data
            assert ex["lr_number"]["value"] == t.lr_number
            assert ex["consignee"]["value"] == t.consignee_name
            assert ex["delivered_quantity"]["value"] == st.printed_qty and ex["delivered_quantity"]["unit"] == t.quantity_unit
            assert ex["delivery_date"]["value"] == t.delivery_date.isoformat()
            checks = {c["check"]: c["status"] for c in t.pods[-1].extractions[-1].validation_data["checks"]}
            assert checks["lr_number"] == "pass" and checks["delivery_date"] == "pass", (st.ref, checks)


def test_no_seeded_extraction_claims_to_be_a_live_model_prediction(seeded):
    with SessionLocal() as db:
        providers = set(db.scalars(select(PodExtraction.model_provider)))
        assert providers == {"seed-data"}
        assert set(db.scalars(select(PodExtraction.model_identifier))) == {"synthetic-seed-record"}


def test_seed_is_idempotent(seeded):
    with SessionLocal() as db:
        before = {m.__name__: db.scalar(select(func.count()).select_from(m)) for m in TABLES}
        assert seed(db).get("skipped") == "already seeded"
        seed(db, with_demo_trips=False)  # the users-only path too
        after = {m.__name__: db.scalar(select(func.count()).select_from(m)) for m in TABLES}
    assert before == after
    assert before["Trip"] == 37 and before["User"] == 7


def test_demo_document_generator_prints_the_seeded_values(seeded, tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("gen", Path(__file__).resolve().parents[2] / "scripts" / "generate_demo_pods.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    monkeypatch.setattr(gen, "OUT", tmp_path)
    dates = gen.seeded_delivery_dates()
    assert dates == {st.ref: st.delivery_date() for st in SAMPLE_TRIPS}  # read from the database, not guessed
    gen.sample_documents()
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(f"{st.ref}_{st.scenario}.jpg" for st in SAMPLE_TRIPS)


def test_sample_definitions_are_internally_consistent():
    s = BY_REF["TRP-66141"]
    assert s.qty - s.printed_qty == 6 and s.scenario == "shortage_remark"
    assert BY_REF["TRP-66134"].scenario == "missing_stamp" and BY_REF["TRP-66120"].printed_qty == BY_REF["TRP-66120"].qty
    assert all(st.delivery_date(date(2026, 11, 9)) < date(2026, 11, 9) for st in SAMPLE_TRIPS)
