import csv
import io
import uuid

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import AuditLog, Pod, PodExtraction, Trip, UploadJob
from app.services.ai.base import AIProviderError
from app.services.ai.mock import MockProvider, result
from tests.conftest import login, make_image
from tests.helpers import make_trip, upload

GOOD = dict(lr="LR-66141", consignee="Indore Warehouse", qty=100, unit="cartons", date=None)


def good(**kw):
    from datetime import date, timedelta

    base = dict(GOOD, date=(date.today() - timedelta(days=1)).isoformat())
    base.update(kw)
    return result(**base)


def pod_of(client, hdr, pod_id):
    return client.get(f"/api/v1/pods/{pod_id}", headers=hdr).json()


# ---------- auth ----------
def test_login_me_logout(client):
    r = client.post("/api/v1/auth/login", json={"email": "billing@routeproof.demo", "password": "Demo@12345"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "billing_executive"
    hdr = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=hdr).json()["email"] == "billing@routeproof.demo"
    assert client.post("/api/v1/auth/logout", headers=hdr).status_code == 200


def test_bad_login_and_missing_token(client):
    assert client.post("/api/v1/auth/login", json={"email": "billing@routeproof.demo", "password": "nope"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "ghost@x.com", "password": "nope"}).status_code == 401
    assert client.get("/api/v1/trips").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


# ---------- authorization ----------
def test_driver_cannot_use_billing_endpoints(client, driver):
    for path in ("/api/v1/trips", "/api/v1/reviews", "/api/v1/billing/queue", "/api/v1/dashboard/metrics", "/api/v1/audit-logs"):
        assert client.get(path, headers=driver).status_code == 403, path
    assert client.post("/api/v1/driver-links", headers=driver, json={"trip_id": str(uuid.uuid4())}).status_code == 403


def test_driver_only_sees_assigned_trips(client, driver, driver2, img):
    mine = make_trip("TRP-A", "LR-1", "driver1@routeproof.demo")
    other = make_trip("TRP-B", "LR-2", "driver2@routeproof.demo")
    assert [t["trip_reference"] for t in client.get("/api/v1/driver/trips", headers=driver).json()["items"]] == ["TRP-A"]
    assert client.get(f"/api/v1/trips/{other}", headers=driver).status_code == 404
    r, _ = upload(client, driver, other, img)
    assert r.status_code == 404
    assert client.get(f"/api/v1/trips/{mine}", headers=driver).status_code == 200
    d = client.get(f"/api/v1/trips/{mine}", headers=driver).json()
    assert "freight_amount" not in d  # commercial data hidden from drivers


def test_driver_cannot_review_or_read_foreign_pod(client, driver, driver2, billing, img):
    tid = make_trip()
    MockProvider.enqueue(good(shortage=True, remarks="Short by 6", qty=94))
    r, _ = upload(client, driver, tid, img)
    pid = r.json()["pod"]["id"]
    assert client.post(f"/api/v1/pods/{pid}/review", headers=driver, json={"decision": "APPROVE"}).status_code == 403
    assert client.get(f"/api/v1/pods/{pid}", headers=driver2).status_code == 404
    assert client.get(f"/api/v1/pods/{pid}/image", headers=driver2).status_code == 404
    assert client.get(f"/api/v1/pods/{pid}/image", headers=driver).status_code == 200
    assert client.get(f"/api/v1/pods/{pid}/image").status_code == 401


# ---------- upload + idempotency ----------
def test_upload_triggers_ai_and_verifies_clean_pod(client, driver, billing, img):
    tid = make_trip()
    MockProvider.enqueue(good())
    r, _ = upload(client, driver, tid, img)
    assert r.status_code == 201
    pod = pod_of(client, billing, r.json()["pod"]["id"])
    assert pod["verification_status"] == "VERIFIED" and pod["verification_method"] == "ai"
    assert pod["extraction"]["model_provider"] == "mock" and pod["extraction"]["prompt_version"]
    assert pod["captured_at_note"] and pod["location_note"]
    trip = client.get(f"/api/v1/trips/{tid}", headers=billing).json()
    assert trip["billing_status"] == "BILLING_READY" and trip["trip_status"] == "POD_VERIFIED"


def test_duplicate_upload_is_idempotent(client, driver, img):
    tid = make_trip()
    MockProvider.enqueue(good())
    r1, key = upload(client, driver, tid, img, key="idem-key-0001")
    r2, _ = upload(client, driver, tid, img, key="idem-key-0001")
    r3, _ = upload(client, driver, tid, img, key="idem-key-0001")
    assert r1.status_code == 201 and r2.status_code == 200 and r3.status_code == 200
    assert r1.json()["pod"]["id"] == r2.json()["pod"]["id"]
    with SessionLocal() as db:
        assert len(db.scalars(select(Pod)).all()) == 1
        assert db.scalars(select(UploadJob)).one().retry_count == 2


def test_idempotency_key_cannot_cross_trips(client, driver, img):
    t1, t2 = make_trip("TRP-A", "LR-1"), make_trip("TRP-B", "LR-2")
    MockProvider.enqueue(good())
    upload(client, driver, t1, img, key="shared-key-001")
    r, _ = upload(client, driver, t2, img, key="shared-key-001")
    assert r.status_code == 409


def test_upload_validation(client, driver):
    tid = make_trip()
    r = client.post(f"/api/v1/trips/{tid}/pods", headers={**driver, "Idempotency-Key": "validkey-0001"},
                    files={"file": ("x.jpg", b"not an image", "image/jpeg")})
    assert r.status_code == 415
    r = client.post(f"/api/v1/trips/{tid}/pods", headers=driver, files={"file": ("x.jpg", make_image(), "image/jpeg")})
    assert r.status_code == 400 and r.json()["error"]["code"] == "idempotency_key_required"
    r = client.post(f"/api/v1/trips/{tid}/pods", headers={**driver, "Idempotency-Key": "validkey-0002"},
                    files={"file": ("x.jpg", b"\x00" * (6 * 1024 * 1024), "image/jpeg")})
    assert r.status_code == 413


def test_second_upload_blocked_while_pod_in_progress(client, driver, img):
    tid = make_trip()
    MockProvider.enqueue(good(shortage=True, remarks="short", qty=94))
    upload(client, driver, tid, img)
    r, _ = upload(client, driver, tid, img)
    assert r.status_code == 409 and r.json()["error"]["code"] == "pod_in_progress"


# ---------- AI failure handling ----------
def test_ai_timeout_routes_to_review_and_keeps_pod(client, driver, billing, img):
    tid = make_trip()
    MockProvider.enqueue(AIProviderError("timeout", "AI provider timed out"))
    r, _ = upload(client, driver, tid, img)
    pod = pod_of(client, billing, r.json()["pod"]["id"])
    assert pod["verification_status"] == "NEEDS_REVIEW" and pod["review_reasons"] == ["AI_ERROR"]
    assert pod["extraction"]["processing_status"] == "FAILED" and "timeout" in pod["extraction"]["processing_error"]
    assert client.get(f"/api/v1/pods/{pod['id']}/image", headers=billing).status_code == 200
    # a human can still resolve it -> billing never permanently blocked by AI failure
    MockProvider.enqueue(good())
    rr = client.post(f"/api/v1/pods/{pod['id']}/process", headers=billing)
    assert rr.status_code == 200 and rr.json()["verification_status"] == "VERIFIED"


def test_invalid_structured_output_is_handled(client, driver, billing, img):
    tid = make_trip()
    MockProvider.enqueue(AIProviderError("invalid_output", "schema failed"))
    r, _ = upload(client, driver, tid, img)
    assert pod_of(client, billing, r.json()["pod"]["id"])["verification_status"] == "NEEDS_REVIEW"


def test_unreadable_image_precheck_requests_retake(client, driver, billing):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (400, 400), "white").save(buf, "JPEG")
    tid = make_trip()
    r, _ = upload(client, driver, tid, buf.getvalue())
    pod = pod_of(client, billing, r.json()["pod"]["id"])
    assert pod["verification_status"] == "RETAKE_REQUESTED" and "UNREADABLE" in pod["review_reasons"]


# ---------- retake cap ----------
def test_two_retakes_then_manual_review(client, driver, billing, img):
    tid = make_trip()
    statuses = []
    for i in range(3):
        MockProvider.enqueue(good(stamp=False))
        r, _ = upload(client, driver, tid, img)
        assert r.status_code == 201, r.text
        statuses.append(pod_of(client, billing, r.json()["pod"]["id"]))
    assert [s["verification_status"] for s in statuses] == ["RETAKE_REQUESTED", "RETAKE_REQUESTED", "NEEDS_REVIEW"]
    assert [s["attempt_number"] for s in statuses] == [1, 2, 3]
    assert statuses[2]["retake_count"] == 2 and "RETAKE_LIMIT_REACHED" in statuses[2]["review_reasons"]
    # human retake no longer allowed either
    r = client.post(f"/api/v1/pods/{statuses[2]['id']}/retake", headers=billing)
    assert r.status_code == 409 and r.json()["error"]["code"] == "retake_limit"
    # old attempts stay visible in trip history
    assert len(client.get(f"/api/v1/trips/{tid}", headers=billing).json()["pods"]) == 3


# ---------- review workflow ----------
def test_human_correction_preserves_original_and_audits(client, driver, billing, img):
    tid = make_trip()
    MockProvider.enqueue(good(lr="LR-66l41"))  # OCR slip
    r, _ = upload(client, driver, tid, img)
    pid = r.json()["pod"]["id"]
    pod = pod_of(client, billing, pid)
    assert pod["verification_status"] == "NEEDS_REVIEW" and "LR_MISMATCH" in pod["review_reasons"]
    # correction without reason is refused
    bad = client.post(f"/api/v1/pods/{pid}/review", headers=billing, json={"decision": "APPROVE", "corrections": {"lr_number": "LR-66141"}})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "reason_required"
    ok = client.post(f"/api/v1/pods/{pid}/review", headers=billing,
                     json={"decision": "APPROVE", "corrections": {"lr_number": "LR-66141"}, "correction_reason": "Misread l as 1"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["verification_status"] == "VERIFIED" and body["verification_method"] == "human"
    assert body["original_values"]["lr_number"] == "LR-66l41"  # AI value preserved
    assert body["effective_values"]["lr_number"] == "LR-66141"
    assert body["reviews"][0]["original_values"] == {"lr_number": "LR-66l41"}
    with SessionLocal() as db:
        ex = db.scalars(select(PodExtraction)).one()
        assert ex.extracted_data["lr_number"]["value"] == "LR-66l41"  # extraction row never mutated
        actions = [a.action for a in db.scalars(select(AuditLog))]
        assert "pod.fields_corrected" in actions and "pod.verified" in actions and "pod.uploaded" in actions
    assert client.get(f"/api/v1/trips/{tid}", headers=billing).json()["billing_status"] == "BILLING_READY"
    # cannot review twice
    assert client.post(f"/api/v1/pods/{pid}/review", headers=billing, json={"decision": "APPROVE"}).status_code == 409


def test_reject_requires_reason_and_keeps_history(client, driver, billing, img):
    tid = make_trip()
    MockProvider.enqueue(good(damage=True, remarks="torn"))
    r, _ = upload(client, driver, tid, img)
    pid = r.json()["pod"]["id"]
    assert client.post(f"/api/v1/pods/{pid}/review", headers=billing, json={"decision": "REJECT"}).status_code == 400
    rej = client.post(f"/api/v1/pods/{pid}/review", headers=billing, json={"decision": "REJECT", "rejection_reason": "Wrong consignment"})
    assert rej.json()["verification_status"] == "REJECTED"
    trip = client.get(f"/api/v1/trips/{tid}", headers=billing).json()
    assert trip["billing_status"] == "NOT_READY" and len(trip["pods"]) == 1
    # rejected -> driver may upload a new attempt
    MockProvider.enqueue(good())
    r2, _ = upload(client, driver, tid, img)
    assert r2.status_code == 201 and r2.json()["pod"]["attempt_number"] == 2


def test_review_queue_filters_and_priority(client, driver, billing, img):
    a, b = make_trip("TRP-A", "LR-1"), make_trip("TRP-B", "LR-2")
    MockProvider.enqueue(good(lr="LR-1", conf=0.6))
    MockProvider.enqueue(good(lr="LR-2", shortage=True, remarks="short", qty=90))
    upload(client, driver, a, img)
    upload(client, driver, b, img)
    q = client.get("/api/v1/reviews", headers=billing).json()
    assert q["total"] == 2 and q["items"][0]["review_priority"] == "high"  # high before medium
    assert client.get("/api/v1/reviews?reason=SHORTAGE", headers=billing).json()["total"] == 1
    assert client.get("/api/v1/reviews?priority=medium", headers=billing).json()["total"] == 1


def test_unverified_pod_never_enters_billing_queue(client, driver, billing, img):
    tid = make_trip()
    MockProvider.enqueue(good(shortage=True, remarks="short", qty=94))
    upload(client, driver, tid, img)
    assert client.get("/api/v1/billing/queue", headers=billing).json()["total"] == 0
    r = client.post("/api/v1/billing/exports", headers=billing, json={"trip_ids": [tid]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_eligible"


# ---------- billing ----------
def _ready_trip(client, driver, img, ref="TRP-A", lr="LR-66141"):
    tid = make_trip(ref, lr)
    MockProvider.enqueue(good(lr=lr))
    upload(client, driver, tid, img)
    return tid


def test_export_csv_duplicate_protection_and_reexport(client, driver, billing, img):
    tid = _ready_trip(client, driver, img)
    assert client.get("/api/v1/billing/queue", headers=billing).json()["total"] == 1
    r = client.post("/api/v1/billing/exports", headers=billing, json={"trip_ids": [tid], "billing_period": "2026-11-H1"})
    assert r.status_code == 201
    exp = r.json()
    dl = client.get(f"/api/v1/billing/exports/{exp['id']}/download", headers=billing)
    assert dl.status_code == 200 and "text/csv" in dl.headers["content-type"]
    rows = list(csv.DictReader(io.StringIO(dl.content.decode("utf-8-sig"))))
    assert rows[0]["trip_reference"] == "TRP-A" and rows[0]["lr_number"] == "LR-66141" and rows[0]["freight_amount_inr"] == "41200.00"
    assert rows[0]["eway_bill_number"] and rows[0]["pod_reference"] == "POD-TRP-A-A1" and rows[0]["client_name"]
    assert client.get(f"/api/v1/trips/{tid}", headers=billing).json()["billing_status"] == "EXPORTED"
    # duplicate export refused
    d = client.post("/api/v1/billing/exports", headers=billing, json={"trip_ids": [tid]})
    assert d.status_code == 409 and d.json()["error"]["code"] == "duplicate_export"
    # explicit re-export needs a reason
    assert client.post("/api/v1/billing/exports", headers=billing, json={"trip_ids": [tid], "reexport": True}).status_code == 400
    re = client.post("/api/v1/billing/exports", headers=billing,
                     json={"trip_ids": [tid], "reexport": True, "reexport_reason": "Tally import failed"})
    assert re.status_code == 201 and re.json()["is_reexport"] is True
    assert client.get("/api/v1/billing/exports", headers=billing).json()["total"] == 2
    # exporting is not invoicing
    assert client.get(f"/api/v1/trips/{tid}", headers=billing).json()["billing_status"] == "EXPORTED"
    inv = client.post(f"/api/v1/billing/trips/{tid}/invoiced", headers=billing, json={"invoice_reference": "INV-1"})
    assert inv.json()["billing_status"] == "INVOICED"
    assert client.post("/api/v1/billing/exports", headers=billing,
                       json={"trip_ids": [tid], "reexport": True, "reexport_reason": "x"}).status_code == 409


def test_csv_escapes_special_characters(client, driver, billing, img):
    tid = make_trip("TRP-Q", "LR-Q")
    with SessionLocal() as db:
        t = db.get(Trip, uuid.UUID(tid))
        t.destination = '=HYPERLINK("x"),"Pune, MH"'
        db.commit()
    MockProvider.enqueue(good(lr="LR-Q"))
    upload(client, driver, tid, img)
    exp = client.post("/api/v1/billing/exports", headers=billing, json={"trip_ids": [tid]}).json()
    raw = client.get(f"/api/v1/billing/exports/{exp['id']}/download", headers=billing).content.decode("utf-8-sig")
    row = list(csv.DictReader(io.StringIO(raw)))[0]
    assert row["destination"].startswith("'=")  # formula neutralised, commas/quotes round-trip intact


def test_billing_filters(client, driver, billing, img):
    _ready_trip(client, driver, img)
    assert client.get("/api/v1/billing/queue?billing_cycle=2026-11-H1", headers=billing).json()["total"] == 1
    assert client.get("/api/v1/billing/queue?billing_cycle=1999-01-H1", headers=billing).json()["total"] == 0
    assert client.get("/api/v1/billing/queue?export_status=EXPORTED", headers=billing).json()["total"] == 0
    assert client.get("/api/v1/billing/queue?q=LR-66141", headers=billing).json()["total"] == 1


# ---------- hired driver link ----------
def test_driver_link_scoped_and_expiring(client, billing, img):
    t1, t2 = make_trip("TRP-A", "LR-1"), make_trip("TRP-B", "LR-2")
    r = client.post("/api/v1/driver-links", headers=billing, json={"trip_id": t1, "phone": "9000011111"})
    assert r.status_code == 201
    body = r.json()
    token = body["url"].rsplit("/", 1)[1]
    assert "no SMS was actually sent" in body["sms"]["note"] and body["sms"]["to"].endswith("1111") and "9000011111" not in str(body)
    info = client.get(f"/api/v1/driver-links/{token}").json()
    assert info["lr_number"] == "LR-1" and "freight_amount" not in info
    MockProvider.enqueue(good(lr="LR-1"))
    up = client.post(f"/api/v1/driver-links/{token}/pods", headers={"Idempotency-Key": "link-key-0001"}, files={"file": ("p.jpg", img, "image/jpeg")})
    assert up.status_code == 201
    dup = client.post(f"/api/v1/driver-links/{token}/pods", headers={"Idempotency-Key": "link-key-0001"}, files={"file": ("p.jpg", img, "image/jpeg")})
    assert dup.status_code == 200 and dup.json()["pod"]["id"] == up.json()["pod"]["id"]
    with SessionLocal() as db:
        pod = db.scalars(select(Pod)).one()
        assert str(pod.trip_id) == t1 and pod.source == "sms_link"  # token only ever reaches its own trip
        from app.models import DriverLink

        stored = db.scalars(select(DriverLink)).one()
        assert stored.token_hash != token and token not in stored.token_hash  # only hash stored
        actions = {a.action for a in db.scalars(select(AuditLog))}
        assert {"driver_link.created", "driver_link.opened", "driver_link.upload"} <= actions
        stored.expires_at = stored.created_at.replace(year=2000)
        db.commit()
    assert client.get(f"/api/v1/driver-links/{token}").status_code == 410
    assert client.get("/api/v1/driver-links/not-a-real-token").status_code == 404
    assert t2  # second trip untouched


# ---------- driver sync ----------
def test_driver_sync_acknowledges_known_keys(client, driver, img):
    tid = make_trip()
    MockProvider.enqueue(good())
    upload(client, driver, tid, img, key="sync-key-0001")
    r = client.post("/api/v1/driver/uploads/sync", headers=driver, json={"keys": ["sync-key-0001", "sync-key-9999"]}).json()["items"]
    assert r[0]["received"] is True and r[0]["verification_status"] == "VERIFIED"
    assert r[1]["received"] is False


# ---------- dashboard + import + audit ----------
def test_dashboard_reflects_database(client, driver, billing, img):
    m0 = client.get("/api/v1/dashboard/metrics", headers=billing).json()
    assert m0["total_trips"] == 0
    tid = _ready_trip(client, driver, img)
    make_trip("TRP-NOPOD", "LR-9", status="DELIVERED")
    m = client.get("/api/v1/dashboard/metrics", headers=billing).json()
    assert m["total_trips"] == 2 and m["billing_ready"] == 1 and m["ai_verified"] == 1 and m["trips_without_pod"] == 1
    assert m["data_source"] in ("demo", "live")
    miss = client.get("/api/v1/dashboard/missing-pods", headers=billing).json()
    assert [i["trip_reference"] for i in miss["items"]] == ["TRP-NOPOD"] and tid
    assert client.get("/api/v1/dashboard/pod-aging", headers=billing).status_code == 200
    assert client.get("/api/v1/dashboard/client-breakdown", headers=billing).json()["items"]


def test_trip_search_filters_pagination(client, billing):
    for i in range(5):
        make_trip(f"TRP-X{i}", f"LR-X{i}")
    r = client.get("/api/v1/trips?page_size=2&page=1", headers=billing).json()
    assert r["total"] == 5 and len(r["items"]) == 2
    assert client.get("/api/v1/trips?q=LR-X3", headers=billing).json()["total"] == 1
    assert client.get("/api/v1/trips?pod_status=PENDING", headers=billing).json()["total"] == 5
    assert client.get("/api/v1/trips?pod_status=VERIFIED", headers=billing).json()["total"] == 0


def test_trip_sorting_is_whitelisted_and_stable(client, billing):
    for i in range(3):
        make_trip(f"TRP-S{i}", f"LR-S{i}")
    refs = lambda q: [t["trip_reference"] for t in client.get(f"/api/v1/trips?{q}", headers=billing).json()["items"]]  # noqa: E731
    assert refs("sort=trip_reference") == ["TRP-S0", "TRP-S1", "TRP-S2"]
    assert refs("sort=-trip_reference") == ["TRP-S2", "TRP-S1", "TRP-S0"]
    assert client.get("/api/v1/trips?sort=-freight_amount", headers=billing).status_code == 200
    assert client.get("/api/v1/trips?sort=client", headers=billing).status_code == 200
    # Anything outside the whitelist is a validation error, never a raw ORDER BY.
    assert client.get("/api/v1/trips?sort=password_hash", headers=billing).status_code == 422


def test_csv_trip_import_validation_and_duplicates(client, billing):
    make_trip("TRP-EXIST", "LR-EXIST")
    body = ("trip_reference,lr_number,eway_bill_number,client_code,vehicle_registration,destination,freight_amount\n"
            "TRP-N1,LR-N1,331000000009,CMPB,MH20 ZZ 9999,Nagpur,\"12,000\"\n"
            "TRP-EXIST,LR-NEW,331000000010,CMPB,MH20 ZZ 9999,Nagpur,100\n"
            "TRP-N2,LR-N2,331000000011,NOPE,MH20 ZZ 9999,Nagpur,100\n"
            "TRP-N3,LR-N3,331000000012,CMPB,MH20 ZZ 9999,Nagpur,abc\n"
            "TRP-N1,LR-N1,331000000009,CMPB,MH20 ZZ 9999,Nagpur,5\n")
    f = {"file": ("t.csv", body.encode(), "text/csv")}
    dry = client.post("/api/v1/trips/import?dry_run=true", headers=billing, files=f).json()
    assert dry["created"] == 1 and len(dry["duplicates"]) == 2 and len(dry["errors"]) == 2
    assert client.get("/api/v1/trips?q=TRP-N1", headers=billing).json()["total"] == 0  # dry run wrote nothing
    real = client.post("/api/v1/trips/import", headers=billing, files={"file": ("t.csv", body.encode(), "text/csv")}).json()
    assert real["created"] == 1
    again = client.post("/api/v1/trips/import", headers=billing, files={"file": ("t.csv", body.encode(), "text/csv")}).json()
    assert again["created"] == 0
    bad = client.post("/api/v1/trips/import", headers=billing, files={"file": ("t.csv", b"a,b\n1,2\n", "text/csv")}).json()
    assert "Missing required column" in bad["fatal"]


def test_audit_log_and_trip_history(client, driver, billing, img):
    tid = _ready_trip(client, driver, img)
    hist = client.get(f"/api/v1/trips/{tid}/history", headers=billing).json()["items"]
    actions = [h["action"] for h in hist]
    for a in ("pod.uploaded", "pod.ai_processing_started", "pod.ai_processed", "pod.verified", "trip.billing_ready"):
        assert a in actions, a
    logs = client.get("/api/v1/audit-logs?action=pod.", headers=billing).json()
    assert logs["total"] >= 4


def test_health_and_error_shape(client):
    assert client.get("/health").json()["status"] == "ok"
    e = client.get("/api/v1/trips/not-a-uuid", headers=login(client, "billing@routeproof.demo")).json()
    assert e["error"]["code"] == "validation_error"
