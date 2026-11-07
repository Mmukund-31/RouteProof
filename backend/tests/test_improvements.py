"""Regression tests for the reliability / audit review findings (issues 1-6 and the follow-up improvements)."""
import csv
import io
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import AuditLog, BillingExport, Pod, PodReviewReason, Trip
from app.services.ai.base import AIProviderError
from app.services.ai.mock import MockProvider, result
from app.services.ai.validation import Expected, _norm_id, evaluate, name_similarity, normalize_unit
from app.services.uploads import storage
from app.services.uploads.cleanup import find_orphans, sweep_orphans
from tests.helpers import make_trip, upload

TODAY = date.today()
YESTERDAY = (TODAY - timedelta(days=1)).isoformat()


def good(**kw):
    base = dict(lr="LR-66141", consignee="Indore Warehouse", qty=100, unit="cartons", date=YESTERDAY)
    base.update(kw)
    return result(**base)


def pod_of(client, hdr, pod_id):
    return client.get(f"/api/v1/pods/{pod_id}", headers=hdr).json()


@pytest.fixture
def own_storage(tmp_path):
    st = storage.LocalStorage(str(tmp_path / "storage"))
    storage.set_storage(st)
    yield st
    storage.set_storage(None)


def ev(res, exp=None, **kw):
    exp = exp or Expected("LR-66141", "Indore Warehouse", TODAY - timedelta(days=1), Decimal(100), "cartons")
    return evaluate(res, exp, threshold=0.85, retakes_used=0, max_retakes=2, today=TODAY, **kw)


# ---------- Issue 1: delivery date is never inferred from the upload ----------
def test_upload_does_not_set_delivery_date(client, driver, billing, img):
    tid = make_trip(status="IN_TRANSIT")
    with SessionLocal() as db:
        t = db.get(Trip, uuid.UUID(tid))
        t.delivery_date = None
        db.commit()
    MockProvider.enqueue(AIProviderError("timeout", "slow"))  # stays in review: nothing verified yet
    r, _ = upload(client, driver, tid, img)
    trip = client.get(f"/api/v1/trips/{tid}", headers=billing).json()
    assert trip["trip_status"] == "POD_PENDING" and trip["delivery_date"] is None  # upload date NOT used
    pod = pod_of(client, billing, r.json()["pod"]["id"])
    assert pod["captured_at"].startswith("2026-11-03T09:30") and pod["server_received_at"]  # kept separately


def test_verified_pod_date_becomes_trip_delivery_date(client, driver, billing, img):
    tid = make_trip(status="IN_TRANSIT")
    with SessionLocal() as db:
        db.get(Trip, uuid.UUID(tid)).delivery_date = None
        db.commit()
    pod_date = (TODAY - timedelta(days=3)).isoformat()
    MockProvider.enqueue(good(date=pod_date))
    r, _ = upload(client, driver, tid, img)
    pod = pod_of(client, billing, r.json()["pod"]["id"])
    assert pod["verification_status"] == "VERIFIED" and pod["proposed_delivery_date"] == pod_date
    trip = client.get(f"/api/v1/trips/{tid}", headers=billing).json()
    assert trip["delivery_date"] == pod_date and trip["delivery_date_source"] == "pod_ai"
    with SessionLocal() as db:
        assert db.scalar(select(AuditLog).where(AuditLog.action == "trip.delivery_date_confirmed"))


def test_human_approval_requires_a_delivery_date(client, driver, billing, img):
    tid = make_trip()
    MockProvider.enqueue(good(date=None, stamp=True, conf=0.6))  # review (low confidence), date missing
    r, _ = upload(client, driver, tid, img)
    pid = r.json()["pod"]["id"]
    with SessionLocal() as db:  # force review even though missing date alone would request a retake
        p = db.get(Pod, uuid.UUID(pid))
        if p.verification_status != "NEEDS_REVIEW":
            p.verification_status = "NEEDS_REVIEW"
            db.commit()
    bad = client.post(f"/api/v1/pods/{pid}/review", headers=billing, json={"decision": "APPROVE"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "delivery_date_required"
    ok = client.post(f"/api/v1/pods/{pid}/review", headers=billing, json={
        "decision": "APPROVE", "corrections": {"delivery_date": YESTERDAY}, "correction_reason": "Date on stamp"})
    assert ok.status_code == 200, ok.text
    trip = client.get(f"/api/v1/trips/{tid}", headers=billing).json()
    assert trip["delivery_date"] == YESTERDAY and trip["delivery_date_source"] == "pod_human"


# ---------- Issue 2: quantity is a critical field ----------
def test_low_confidence_quantity_without_expected_quantity_goes_to_review():
    exp = Expected("LR-1", "X", None, None, None)
    res = result(lr="LR-1", consignee="X", qty=40, unit="bags", conf=0.97)
    res.delivered_quantity.confidence = 0.48
    d = ev(res, exp)
    checks = {c["check"]: c["status"] for c in d.checks}
    assert d.decision == "NEEDS_REVIEW" and "QUANTITY_UNREADABLE" in d.reasons
    assert checks["quantity"] == "na" and checks["quantity_reading"] == "fail"  # cannot compare != cannot read


def test_missing_quantity_goes_to_review_even_without_expected():
    exp = Expected("LR-1", "X", None, None, None)
    d = ev(result(lr="LR-1", consignee="X", qty=None), exp)
    assert d.decision == "NEEDS_REVIEW" and "QUANTITY_UNREADABLE" in d.reasons


def test_quantity_without_unit_is_not_readable():
    d = ev(good(unit=None))
    assert "QUANTITY_UNREADABLE" in d.reasons


@pytest.mark.parametrize("unit", ["Cartons", "ctns", "CTN", "boxes", "cases"])
def test_unit_aliases_match(unit):
    assert ev(good(unit=unit)).decision == "VERIFIED"


def test_unit_mismatch_is_flagged():
    d = ev(good(unit="kg"))
    assert "QUANTITY_MISMATCH" in d.reasons
    assert normalize_unit("MT") == normalize_unit("tonnes") == "tonne" and normalize_unit("") is None


# ---------- OCR validation: Unicode-aware normalisation ----------
def test_unicode_name_matching():
    assert name_similarity("श्री गणेश ट्रेडर्स", "श्री गणेश ट्रेडर्स प्रा. लि.") == 1.0  # Devanagari kept intact
    assert name_similarity("Café Mahalaxmi", "CAFE MAHALAXMI") == 1.0  # Latin diacritics folded
    assert name_similarity("ＩＮＤＯＲＥ Warehouse", "Indore Warehouse") == 1.0  # full-width forms
    assert name_similarity("श्री गणेश", "Shree Ganesh") < 0.7  # different scripts are not silently "equal"


def test_unicode_lr_matching():
    assert _norm_id("LR-६६१४१") == _norm_id("LR 66141")  # Devanagari digits
    assert _norm_id("ＬＲ－６６１４１") == _norm_id("lr66141")


# ---------- Issue 3: processing recovery ----------
def test_provider_init_failure_does_not_strand_pod(client, driver, billing, img, monkeypatch):
    import app.services.pods.service as svc

    def boom():
        raise RuntimeError("bad config")

    monkeypatch.setattr(svc, "get_provider", boom)
    tid = make_trip()
    r, _ = upload(client, driver, tid, img)
    pod = pod_of(client, billing, r.json()["pod"]["id"])
    assert pod["verification_status"] == "NEEDS_REVIEW" and pod["review_reasons"] == ["AI_ERROR"]
    assert pod["review_categories"] == ["system"] and "internal" in pod["processing"]["last_error"]


def test_unexpected_crash_after_claim_routes_to_review(client, driver, billing, img, monkeypatch):
    import app.services.pods.service as svc

    def crash(*a, **k):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(svc, "_apply_decision", crash)
    MockProvider.enqueue(good())
    tid = make_trip()
    r, _ = upload(client, driver, tid, img)
    pod = pod_of(client, billing, r.json()["pod"]["id"])
    assert pod["verification_status"] == "NEEDS_REVIEW" and pod["extraction"]["processing_status"] == "FAILED"
    assert pod["processing"]["attempts"] == 1


def test_transient_errors_are_retried(client, driver, billing, img, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_max_attempts", 3)
    MockProvider.enqueue(AIProviderError("rate_limit", "429"))
    MockProvider.enqueue(AIProviderError("timeout", "slow"))
    MockProvider.enqueue(good())
    tid = make_trip()
    r, _ = upload(client, driver, tid, img)
    pod = pod_of(client, billing, r.json()["pod"]["id"])
    assert pod["verification_status"] == "VERIFIED"
    assert pod["extraction"]["attempt_count"] == 3 and len(pod["extraction"]["validation_data"]["attempt_errors"]) == 2


def test_permanent_errors_are_not_retried(client, driver, billing, img, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_max_attempts", 3)
    MockProvider.enqueue(AIProviderError("invalid_output", "bad schema"))
    tid = make_trip()
    r, _ = upload(client, driver, tid, img)
    pod = pod_of(client, billing, r.json()["pod"]["id"])
    assert pod["verification_status"] == "NEEDS_REVIEW" and pod["extraction"]["attempt_count"] == 1


def _stick(pod_id, status, minutes_ago):
    with SessionLocal() as db:
        p = db.get(Pod, uuid.UUID(pod_id))
        p.verification_status = status
        p.processing_started_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
        p.server_received_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
        db.commit()


def test_stale_processing_is_recovered(client, driver, billing, img):
    MockProvider.enqueue(AIProviderError("timeout", "x"))
    r, _ = upload(client, driver, make_trip(), img)
    pid = r.json()["pod"]["id"]
    _stick(pid, "AI_PROCESSING", minutes_ago=2)
    assert client.post("/api/v1/pods/maintenance/recover", headers=billing).json()["recovered"] == []  # not stale yet
    assert client.post(f"/api/v1/pods/{pid}/process", headers=billing).status_code == 409
    _stick(pid, "AI_PROCESSING", minutes_ago=30)
    out = client.post("/api/v1/pods/maintenance/recover", headers=billing).json()
    assert out["recovered"] == [pid]
    pod = pod_of(client, billing, pid)
    assert pod["verification_status"] == "NEEDS_REVIEW" and pod["review_reasons"] == ["PROCESSING_STALLED"]
    MockProvider.enqueue(good())  # manual reprocess then succeeds
    assert client.post(f"/api/v1/pods/{pid}/process", headers=billing).json()["verification_status"] == "VERIFIED"


def test_manual_reprocess_unsticks_stale_pod(client, driver, billing, img):
    MockProvider.enqueue(AIProviderError("timeout", "x"))
    r, _ = upload(client, driver, make_trip(), img)
    pid = r.json()["pod"]["id"]
    _stick(pid, "AI_PROCESSING", minutes_ago=60)
    MockProvider.enqueue(good())
    rr = client.post(f"/api/v1/pods/{pid}/process", headers=billing)
    assert rr.status_code == 200 and rr.json()["verification_status"] == "VERIFIED"


def test_orphaned_upload_is_requeued(client, driver, billing, img):
    MockProvider.enqueue(AIProviderError("timeout", "x"))
    r, _ = upload(client, driver, make_trip(), img)
    pid = r.json()["pod"]["id"]
    _stick(pid, "UPLOADED", minutes_ago=30)  # e.g. the worker restarted before the background task ran
    MockProvider.enqueue(good())
    assert client.post("/api/v1/pods/maintenance/recover", headers=billing).json()["requeued"] == 1
    assert pod_of(client, billing, pid)["verification_status"] == "VERIFIED"


def test_ai_errors_are_distinct_from_business_exceptions_in_queue(client, driver, billing, img):
    a, b = make_trip("TRP-A", "LR-1"), make_trip("TRP-B", "LR-2")
    MockProvider.enqueue(AIProviderError("timeout", "provider timed out"))
    MockProvider.enqueue(good(lr="LR-2", shortage=True, remarks="Short by 6", qty=94))
    upload(client, driver, a, img)
    upload(client, driver, b, img)
    sys_q = client.get("/api/v1/reviews?category=system", headers=billing).json()
    biz_q = client.get("/api/v1/reviews?category=business", headers=billing).json()
    assert [p["trip"]["trip_reference"] for p in sys_q["items"]] == ["TRP-A"]
    assert [p["trip"]["trip_reference"] for p in biz_q["items"]] == ["TRP-B"]
    assert "System error, not a document problem" in sys_q["items"][0]["extraction"]["validation_data"]["checks"][0]["detail"]


def test_review_queue_paginates_in_sql(client, driver, billing, img):
    for i in range(5):
        tid = make_trip(f"TRP-P{i}", f"LR-P{i}")
        MockProvider.enqueue(good(lr=f"LR-P{i}", shortage=i % 2 == 0, remarks="short" if i % 2 == 0 else None))
        upload(client, driver, tid, img)
    page1 = client.get("/api/v1/reviews?page_size=2&page=1", headers=billing).json()
    page2 = client.get("/api/v1/reviews?page_size=2&page=2", headers=billing).json()
    assert page1["total"] == 3 and len(page1["items"]) == 2 and len(page2["items"]) == 1
    assert client.get("/api/v1/reviews?reason=SHORTAGE&priority=high", headers=billing).json()["total"] == 3
    with SessionLocal() as db:
        assert db.scalar(select(PodReviewReason).where(PodReviewReason.reason == "SHORTAGE")).category == "business"


# ---------- Issue 4: storage / database atomicity ----------
def test_failed_db_commit_removes_stored_images(client, driver, img, monkeypatch, own_storage):
    import app.services.pods.service as svc

    def fail(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(svc, "audit", fail)
    tid = make_trip()
    with pytest.raises(RuntimeError):
        upload(client, driver, tid, img)
    assert list(storage.get_storage().list("pods/")) == []
    with SessionLocal() as db:
        assert db.scalar(select(Pod)) is None


def test_failed_export_removes_csv(client, driver, billing, img, monkeypatch, own_storage):
    import app.services.billing.service as bsvc

    tid = make_trip()
    MockProvider.enqueue(good())
    upload(client, driver, tid, img)

    def fail(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(bsvc, "_record_export", fail)
    with pytest.raises(RuntimeError):
        client.post("/api/v1/billing/exports", headers=billing, json={"trip_ids": [tid]})
    assert list(storage.get_storage().list("exports/")) == []


def test_orphan_sweep(client, driver, img, own_storage):
    MockProvider.enqueue(good())
    upload(client, driver, make_trip(), img)
    st = storage.get_storage()
    st.put("pods/ghost/ghost.jpg", img, "image/jpeg")
    future = datetime.now(timezone.utc) + timedelta(hours=48)
    with SessionLocal() as db:
        assert find_orphans(db, st) == []  # within the grace period: could be an in-flight upload
        assert find_orphans(db, st, now=future) == ["pods/ghost/ghost.jpg"]
        assert sweep_orphans(db, st, now=future)["removed"] == []  # dry run by default
        assert sweep_orphans(db, st, delete=True, now=future)["removed"] == ["pods/ghost/ghost.jpg"]
    assert len(list(st.list("pods/"))) == 1  # the referenced image is untouched


def test_export_locks_trip_rows():
    from app.services.billing import service as bsvc

    captured = {}

    class FakeDB:
        def scalars(self, stmt):
            captured["sql"] = str(stmt.compile(dialect=postgresql.dialect()))

            class R:
                def unique(self):
                    return []
            return R()

    bsvc.lock_trips(FakeDB(), [uuid.uuid4()])
    assert "FOR UPDATE OF trips" in captured["sql"] and "ORDER BY trips.id" in captured["sql"]


# ---------- Issue 5: HttpOnly cookie session + CSRF ----------
def test_cookie_session_and_csrf(client):
    r = client.post("/api/v1/auth/login", json={"email": "billing@routeproof.demo", "password": "Demo@12345", "mode": "cookie"})
    assert r.status_code == 200 and "access_token" not in r.json()
    set_cookie = r.headers.get_list("set-cookie") if hasattr(r.headers, "get_list") else r.headers.get("set-cookie")
    session_cookie = next(c for c in set_cookie if c.startswith("rp_session="))
    assert "HttpOnly" in session_cookie and "SameSite=lax" in session_cookie
    csrf = r.json()["csrf_token"]
    assert client.get("/api/v1/auth/me").status_code == 200  # cookie alone is enough for reads
    assert client.post("/api/v1/auth/logout").json()["error"]["code"] == "csrf_failed"  # writes need the CSRF header
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "forged"}).status_code == 403
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401  # logout cleared the session cookie


def test_session_absolute_lifetime(monkeypatch):
    from app.core.security import create_access_token, decode_token

    old = int((datetime.now(timezone.utc) - timedelta(hours=13)).timestamp())
    token, _ = create_access_token(str(uuid.uuid4()), "driver", auth_time=old)
    assert decode_token(token) is None  # refreshed or not, a 13h-old login is over


def test_api_security_headers_and_request_id(client):
    r = client.get("/health", headers={"X-Request-ID": "req-abcdef12"})
    assert r.headers["X-Request-ID"] == "req-abcdef12"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"] and r.headers["X-Frame-Options"] == "DENY"
    e = client.get("/api/v1/trips")
    assert e.json()["error"]["request_id"] == e.headers["X-Request-ID"]


# ---------- Issue 6: approving an exception needs a rationale ----------
def test_shortage_approval_requires_rationale_and_is_recorded(client, driver, billing, img):
    tid = make_trip("TRP-66141", "LR-66141")
    MockProvider.enqueue(good(shortage=True, remarks="Short by 6 cartons", qty=94))
    r, _ = upload(client, driver, tid, img)
    pid = r.json()["pod"]["id"]
    bad = client.post(f"/api/v1/pods/{pid}/review", headers=billing, json={"decision": "APPROVE"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "approval_reason_required"
    assert bad.json()["error"]["details"]["exceptions"] == ["QUANTITY_MISMATCH", "SHORTAGE"]
    # Clearing the shortage flag does not dodge the rationale: the AI-raised exception still counts.
    sneaky = client.post(f"/api/v1/pods/{pid}/review", headers=billing, json={
        "decision": "APPROVE", "corrections": {"shortage_detected": False}, "correction_reason": "looks fine"})
    assert sneaky.json()["error"]["code"] == "approval_reason_required"
    ok = client.post(f"/api/v1/pods/{pid}/review", headers=billing, json={
        "decision": "APPROVE", "approval_reason": "Client confirmed by email they accept the 6-carton shortage"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["verification_status"] == "VERIFIED" and body["approved_exceptions"] == ["QUANTITY_MISMATCH", "SHORTAGE"]
    rev = body["reviews"][-1]
    assert rev["approval_reason"].startswith("Client confirmed") and rev["accepted_exceptions"] == ["QUANTITY_MISMATCH", "SHORTAGE"]
    assert rev["reviewer_id"] and rev["reviewed_at"]
    assert body["extraction"]["extracted_data"]["shortage_detected"] is True  # original AI flag preserved
    with SessionLocal() as db:
        a = db.scalar(select(AuditLog).where(AuditLog.action == "pod.exception_approved"))
        assert a.meta["rationale"].startswith("Client confirmed") and a.meta["ai_flags"]["shortage_detected"] is True
    exp = client.post("/api/v1/billing/exports", headers=billing, json={"trip_ids": [tid]}).json()
    raw = client.get(f"/api/v1/billing/exports/{exp['id']}/download", headers=billing).content.decode("utf-8-sig")
    assert list(csv.DictReader(io.StringIO(raw)))[0]["pod_exceptions"] == "QUANTITY_MISMATCH;SHORTAGE"


def test_clean_pod_has_no_exception(client, driver, billing, img):
    MockProvider.enqueue(good())
    r, _ = upload(client, driver, make_trip(), img)
    assert pod_of(client, billing, r.json()["pod"]["id"])["approved_exceptions"] == []


# ---------- GPS status ----------
@pytest.mark.parametrize("sent,expected", [("permission_denied", "permission_denied"), ("timeout", "timeout"),
                                           (None, "not_provided"), ("captured", "not_provided"), ("junk", "not_provided")])
def test_location_status_without_coordinates(client, driver, billing, img, sent, expected):
    tid = make_trip()
    MockProvider.enqueue(good())
    data = {"captured_at": "2026-11-03T09:30:00Z"}
    if sent:
        data["location_status"] = sent
    r = client.post(f"/api/v1/trips/{tid}/pods", headers={**driver, "Idempotency-Key": uuid.uuid4().hex},
                    files={"file": ("pod.jpg", img, "image/jpeg")}, data=data)
    pod = pod_of(client, billing, r.json()["pod"]["id"])
    assert pod["location_status"] == expected and pod["latitude"] is None


def test_location_status_with_coordinates(client, driver, billing, img):
    MockProvider.enqueue(good())
    r, _ = upload(client, driver, make_trip(), img, location_status="permission_denied")
    pod = pod_of(client, billing, r.json()["pod"]["id"])
    assert pod["location_status"] == "captured" and pod["latitude"] == pytest.approx(19.87)


def test_half_a_coordinate_is_rejected(client, driver, img):
    r = client.post(f"/api/v1/trips/{make_trip()}/pods", headers={**driver, "Idempotency-Key": uuid.uuid4().hex},
                    files={"file": ("pod.jpg", img, "image/jpeg")}, data={"latitude": "19.8"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_location"


# ---------- Dashboard: consistent billing timestamps ----------
def test_billing_milestones_are_stamped(client, driver, billing, img):
    tid = make_trip()
    MockProvider.enqueue(good())
    upload(client, driver, tid, img)
    client.post("/api/v1/billing/exports", headers=billing, json={"trip_ids": [tid]})
    trip = client.get(f"/api/v1/trips/{tid}", headers=billing).json()
    assert trip["billing_ready_at"] and trip["exported_at"] and trip["exported_at"] >= trip["billing_ready_at"]
    m = client.get("/api/v1/dashboard/metrics", headers=billing).json()
    assert m["avg_upload_to_billing_ready_hours"] is not None and m["avg_billing_ready_to_export_hours"] is not None
    assert "never the upload date" in m["metric_definitions"]["delivery_date"]
    with SessionLocal() as db:
        assert db.scalar(select(BillingExport)) is not None


# ---------- AI confidence calibration ----------
def test_calibration_measures_error_rate_per_threshold():
    from app.services.ai.calibration import Reading, summarise

    rs = [Reading("lr_number", 0.95, True, "s", "none")] * 40 + [Reading("lr_number", 0.80, False, "s", "none")] * 10
    for f in ("consignee", "delivered_quantity", "delivery_date"):
        rs += [Reading(f, 0.95, True, "s", "none")] * 40
    rep = summarise(rs, samples=50, provider_errors=0, target_error_rate=0.01, min_accepted=30)
    by = {r["threshold"]: r for r in rep.per_threshold}
    assert by[0.75]["fields"]["lr_number"]["error_rate"] == 0.2 and not by[0.75]["meets_target"]
    assert by[0.85]["meets_target"] and rep.recommended_threshold == 0.85


def test_calibration_runs_end_to_end_with_a_provider():
    from app.services.ai.calibration import calibrate, make_samples

    truths = [t for _, t in make_samples(6)]
    MockProvider.default = staticmethod(lambda ctx: result(lr=ctx.lr_number, consignee=ctx.consignee_name, qty=None, date=None))
    try:
        rep = calibrate(MockProvider(), n=6, min_accepted=1)
    finally:
        MockProvider.default = None
    assert rep.samples == 6 and rep.per_field["lr_number"]["readings"] == 6 and len(truths) == 6
    assert rep.per_field["lr_number"]["accuracy"] == 1.0


# ---------- Observability ----------
def test_structured_log_drops_personal_fields():
    import json
    import logging

    from app.core.observability import JsonFormatter, processing_id_var, request_id_var

    rec = logging.LogRecord("routeproof.pods", logging.INFO, __file__, 1, "pod.uploaded", None, None)
    rec.pod_id, rec.consignee, rec.phone, rec.latitude = "p-1", "Indore Warehouse", "9000000001", 19.8
    t1, t2 = request_id_var.set("req-12345678"), processing_id_var.set("proc-1")
    try:
        out = json.loads(JsonFormatter().format(rec))
    finally:
        request_id_var.reset(t1)
        processing_id_var.reset(t2)
    assert out["pod_id"] == "p-1" and out["request_id"] == "req-12345678" and out["processing_id"] == "proc-1"
    assert not {"consignee", "phone", "latitude"} & set(out)
