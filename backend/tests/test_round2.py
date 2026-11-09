"""Second review round: client POD view, invoice evidence in CSV, 300 KB policy, hired-driver links, delivery-date
regressions, business turnaround metrics and consistent missing-POD filters."""
import csv
import io
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import AuditLog, ClientViewLink, DriverLink, Trip
from app.services.ai.base import AIProviderError
from app.services.ai.mock import MockProvider, result
from tests.conftest import make_image
from tests.helpers import make_trip, upload

TODAY = date.today()


def good(lr="LR-66141", day=None, **kw):
    base = dict(lr=lr, consignee="Indore Warehouse", qty=100, unit="cartons", date=(day or TODAY - timedelta(days=1)).isoformat())
    base.update(kw)
    return result(**base)


def verified_trip(client, driver, img, ref, lr, **kw):
    tid = make_trip(ref, lr, **kw)
    MockProvider.enqueue(good(lr=lr))
    r, _ = upload(client, driver, tid, img)
    return tid, r.json()["pod"]["id"]


def actions():
    with SessionLocal() as db:
        return [a.action for a in db.scalars(select(AuditLog))]


# ---------- 1. client POD-view links ----------
def _client_id(trip_id):
    with SessionLocal() as db:
        return str(db.get(Trip, uuid.UUID(trip_id)).client_id)


def test_client_link_shows_only_its_trips_and_verified_images(client, driver, billing, img):
    a, _ = verified_trip(client, driver, img, "TRP-A", "LR-A")
    b = make_trip("TRP-B", "LR-B")  # same client, no POD yet
    other = make_trip("TRP-X", "LR-X", client_code="CMPB")  # another client
    cid = _client_id(a)
    r = client.post("/api/v1/client-links", headers=billing, json={"client_id": cid, "trip_ids": [a, b], "expires_in_days": 7, "label": "Nov H1"})
    assert r.status_code == 201
    token = r.json()["url"].rsplit("/view/", 1)[1]
    assert len(token) >= 43  # 32 random bytes, url-safe
    view = client.get(f"/api/v1/client-view/{token}")
    assert view.status_code == 200 and view.headers["Cache-Control"] == "private, no-store"
    body = view.json()
    rows = {t["trip_reference"]: t for t in body["trips"]}
    assert set(rows) == {"TRP-A", "TRP-B"}
    assert rows["TRP-A"]["pod_status"] == "VERIFIED" and rows["TRP-A"]["has_image"] and rows["TRP-A"]["delivery_date"]
    assert rows["TRP-B"]["pod_status"] == "PENDING" and not rows["TRP-B"]["has_image"]
    raw = view.text
    for leak in ("driver", "phone", "freight", "latitude", "Ramesh", "9000000001", "storage"):
        assert leak not in raw, leak
    assert client.get(f"/api/v1/client-view/{token}/trips/{a}/pod-image").headers["content-type"].startswith("image/")
    assert client.get(f"/api/v1/client-view/{token}/trips/{b}/pod-image").status_code == 404  # no verified POD
    assert client.get(f"/api/v1/client-view/{token}/trips/{other}/pod-image").status_code == 404  # out of scope
    with SessionLocal() as db:
        link = db.scalars(select(ClientViewLink)).one()
        assert link.token_hash != token and token not in link.token_hash and link.access_count == 2
    assert {"client_link.created", "client_link.opened", "client_link.image_viewed"} <= set(actions())


def test_client_link_cannot_include_another_clients_trip(client, billing):
    a, x = make_trip("TRP-A", "LR-A"), make_trip("TRP-X", "LR-X", client_code="CMPB")
    r = client.post("/api/v1/client-links", headers=billing, json={"client_id": _client_id(a), "trip_ids": [a, x]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "trip_not_for_client"
    both = client.post("/api/v1/client-links", headers=billing, json={"client_id": _client_id(a), "trip_ids": [a], "billing_cycle": "2026-11-H1"})
    assert both.status_code == 400


def test_client_link_by_billing_cycle_expiry_and_revocation(client, driver, billing, img):
    a, _ = verified_trip(client, driver, img, "TRP-A", "LR-A")
    late = make_trip("TRP-C", "LR-C")
    with SessionLocal() as db:
        db.get(Trip, uuid.UUID(late)).billing_cycle = "2026-12-H1"
        db.commit()
    r = client.post("/api/v1/client-links", headers=billing, json={"client_id": _client_id(a), "billing_cycle": "2026-11-H1"}).json()
    token = r["url"].rsplit("/", 1)[1]
    assert [t["trip_reference"] for t in client.get(f"/api/v1/client-view/{token}").json()["trips"]] == ["TRP-A"]
    assert client.post(f"/api/v1/client-links/{r['id']}/revoke", headers=billing).json()["state"] == "revoked"
    assert client.get(f"/api/v1/client-view/{token}").status_code == 410
    assert client.get(f"/api/v1/client-view/{token}/trips/{a}/pod-image").status_code == 410
    assert "client_link.revoked" in actions()
    r2 = client.post("/api/v1/client-links", headers=billing, json={"client_id": _client_id(a), "trip_ids": [a]}).json()
    with SessionLocal() as db:
        lk = db.get(ClientViewLink, uuid.UUID(r2["id"]))
        lk.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert client.get(f"/api/v1/client-view/{r2['url'].rsplit('/', 1)[1]}").status_code == 410
    assert client.post("/api/v1/client-links", headers=billing, json={"client_id": _client_id(a), "trip_ids": [a], "expires_in_days": 60}).status_code == 400


def test_driver_and_client_tokens_are_not_interchangeable(client, billing, driver):
    tid = make_trip()
    dl = client.post("/api/v1/driver-links", headers=billing, json={"trip_id": tid}).json()["url"].rsplit("/", 1)[1]
    cl = client.post("/api/v1/client-links", headers=billing, json={"client_id": _client_id(tid), "trip_ids": [tid]}).json()["url"].rsplit("/", 1)[1]
    assert client.get(f"/api/v1/client-view/{dl}").status_code == 404
    assert client.get(f"/api/v1/driver-links/{cl}").status_code == 404
    assert client.post(f"/api/v1/driver-links/{cl}/pods", headers={"Idempotency-Key": "k" * 12},
                       files={"file": ("p.jpg", make_image(), "image/jpeg")}).status_code == 404
    assert client.post("/api/v1/client-links", headers=driver, json={"client_id": _client_id(tid), "trip_ids": [tid]}).status_code == 403


# ---------- 2. invoice-to-POD evidence in the CSV ----------
def test_csv_carries_pod_evidence_without_storage_paths(client, driver, billing, img):
    tid, pid = verified_trip(client, driver, img, "TRP-A", "LR-A")
    exp = client.post("/api/v1/billing/exports", headers=billing, json={"trip_ids": [tid]}).json()
    assert exp["trip_ids"] == [tid]
    raw = client.get(f"/api/v1/billing/exports/{exp['id']}/download", headers=billing).content.decode("utf-8-sig")
    row = list(csv.DictReader(io.StringIO(raw)))[0]
    for col in ("trip_reference", "lr_number", "eway_bill_number", "pod_reference", "pod_image_reference", "delivery_date",
                "client_name", "billing_cycle", "freight_amount_inr", "pod_evidence_url"):
        assert row[col], col
    assert row["pod_image_reference"] == f"PODIMG-{pid}" and row["pod_evidence_url"].endswith(f"/pods/{pid}")
    assert f"pods/{tid}/" not in raw and "storage" not in raw and "/image" not in raw  # no private paths / direct image URLs


# ---------- 3. compressed upload size policy (strictly under 300 KB) ----------
def _sized(n: int) -> bytes:
    base = make_image()
    assert len(base) < n
    return base + b"\0" * (n - len(base))  # JPEG decoders ignore bytes after the end-of-image marker


@pytest.mark.parametrize("kb,policy", [(100, "OK"), (299, "OK"), (300, "OVERSIZE"), (301, "OVERSIZE")])
def test_compressed_size_policy(client, driver, billing, kb, policy):
    MockProvider.enqueue(good())
    r, _ = upload(client, driver, make_trip(), _sized(kb * 1024))
    assert r.status_code == 201  # evidence is never dropped for size; it is flagged
    pod = client.get(f"/api/v1/pods/{r.json()['pod']['id']}", headers=billing).json()
    assert pod["upload_bytes"] == kb * 1024 and pod["upload_size_policy"] == policy and pod["upload_limit_bytes"] == 300 * 1024
    assert ("pod.upload_oversize" in actions()) == (policy == "OVERSIZE")


def test_one_byte_under_the_limit_is_ok(client, driver, billing):
    MockProvider.enqueue(good())
    r, _ = upload(client, driver, make_trip(), _sized(300 * 1024 - 1))
    assert client.get(f"/api/v1/pods/{r.json()['pod']['id']}", headers=billing).json()["upload_size_policy"] == "OK"


def test_original_is_attached_after_the_compressed_copy(client, driver, driver2, billing, img):
    MockProvider.enqueue(good())
    r, _ = upload(client, driver, make_trip(), img)
    pid = r.json()["pod"]["id"]
    big = _sized(2 * 1024 * 1024)
    assert client.post(f"/api/v1/pods/{pid}/original", headers=driver2, files={"file": ("o.jpg", big, "image/jpeg")}).status_code == 404
    first = client.post(f"/api/v1/pods/{pid}/original", headers=driver, files={"file": ("o.jpg", big, "image/jpeg")})
    assert first.status_code == 201 and first.json()["original_bytes"] == len(big)
    again = client.post(f"/api/v1/pods/{pid}/original", headers=driver, files={"file": ("o.jpg", img, "image/jpeg")})
    assert again.status_code == 200 and again.json()["attached"] is False  # the first original is kept
    pod = client.get(f"/api/v1/pods/{pid}", headers=billing).json()
    assert pod["has_separate_original"] and pod["original_bytes"] == len(big)
    assert client.get(f"/api/v1/pods/{pid}/image?variant=original", headers=billing).content == big
    assert "pod.original_attached" in actions()


# ---------- 4. hired-driver link, start to finish ----------
def test_hired_driver_link_journey(client, billing, img):
    tid, other = make_trip("TRP-H", "LR-H"), make_trip("TRP-O", "LR-O")
    MockProvider.enqueue(good(lr="LR-O"))
    other_pod = upload(client, login_driver(client), other, img)[0].json()["pod"]["id"]
    made = client.post("/api/v1/driver-links", headers=billing, json={"trip_id": tid, "phone": "9000012345"}).json()
    token = made["url"].rsplit("/", 1)[1]
    assert len(token) >= 43
    links = client.get(f"/api/v1/driver-links?trip_id={tid}", headers=billing).json()["items"]
    assert links[0]["state"] == "active" and links[0]["sms_log"][0]["status"] == "LOGGED_NOT_SENT"
    assert links[0]["sms_log"][0]["to"].endswith("2345") and "9000012345" not in str(links)
    # no sign-in: the token alone uploads, AI processes, the office sees the result
    MockProvider.enqueue(good(lr="LR-H", shortage=True, remarks="short 6", qty=94))
    up = client.post(f"/api/v1/driver-links/{token}/pods", headers={"Idempotency-Key": "hired-0001"},
                     files={"file": ("p.jpg", img, "image/jpeg")}, data={"location_status": "permission_denied"})
    assert up.status_code == 201
    q = client.get("/api/v1/reviews?q=TRP-H", headers=billing).json()["items"]
    assert q and q[0]["source"] == "sms_link" and "SHORTAGE" in q[0]["review_reasons"] and q[0]["location_status"] == "permission_denied"
    pid = up.json()["pod"]["id"]
    # the link can attach the original for its own POD only, and can read nothing about other trips
    assert client.post(f"/api/v1/driver-links/{token}/pods/{pid}/original", files={"file": ("o.jpg", img, "image/jpeg")}).status_code == 201
    assert client.post(f"/api/v1/driver-links/{token}/pods/{other_pod}/original", files={"file": ("o.jpg", img, "image/jpeg")}).status_code == 404
    assert client.get(f"/api/v1/pods/{pid}/image").status_code == 401
    view = client.get(f"/api/v1/driver-links/{token}").json()
    assert set(view) == {"lr_number", "trip_reference", "destination", "pod_status", "retakes_remaining"}
    # revocation ends it
    assert client.post(f"/api/v1/driver-links/{made['id']}/revoke", headers=billing).json()["state"] == "revoked"
    assert client.get(f"/api/v1/driver-links/{token}").status_code == 410
    assert client.post(f"/api/v1/driver-links/{token}/pods", headers={"Idempotency-Key": "hired-0002"},
                       files={"file": ("p.jpg", img, "image/jpeg")}).status_code == 410
    with SessionLocal() as db:
        assert db.scalars(select(DriverLink)).one().token_hash != token


def login_driver(client):
    from tests.conftest import login

    return login(client, "driver1@routeproof.demo")


def test_link_endpoints_are_rate_limited(client, billing, monkeypatch):
    from app.core import ratelimit

    tid = make_trip()
    token = client.post("/api/v1/driver-links", headers=billing, json={"trip_id": tid}).json()["url"].rsplit("/", 1)[1]
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    ratelimit.reset()
    codes = [client.get(f"/api/v1/driver-links/{token}").status_code for _ in range(61)]
    assert codes[:60] == [200] * 60 and codes[60] == 429
    codes = [client.get("/api/v1/client-view/not-a-token").status_code for _ in range(61)]
    assert codes[-1] == 429


# ---------- 7. delivery date vs upload time ----------
def _trip(tid):
    with SessionLocal() as db:
        return db.get(Trip, uuid.UUID(tid))


def test_ai_failure_never_sets_or_changes_delivery_date(client, driver, img):
    none_trip = make_trip("TRP-N", "LR-N", status="IN_TRANSIT")
    with SessionLocal() as db:
        db.get(Trip, uuid.UUID(none_trip)).delivery_date = None
        db.commit()
    imported = make_trip("TRP-I", "LR-I", delivery_date=TODAY - timedelta(days=4))
    for tid in (none_trip, imported):
        MockProvider.enqueue(AIProviderError("timeout", "x"))
        upload(client, driver, tid, img)
    assert _trip(none_trip).delivery_date is None
    t = _trip(imported)
    assert t.delivery_date == TODAY - timedelta(days=4) and t.delivery_date_source is None  # helper rows have no source


def test_pod_uploaded_three_days_after_delivery_keeps_the_document_date(client, driver, billing, img):
    d = TODAY - timedelta(days=3)
    tid = make_trip(delivery_date=d)
    MockProvider.enqueue(good(day=d))
    upload(client, driver, tid, img, captured_at=(datetime.now(timezone.utc) - timedelta(days=3)).isoformat())
    t = _trip(tid)
    assert t.delivery_date == d and t.delivery_date_source == "pod_ai"
    m = client.get("/api/v1/dashboard/metrics", headers=billing).json()["turnaround"]["delivery_to_pod_received"]
    assert m["count"] == 1 and m["avg_days"] >= 2.5


def test_offline_capture_synced_next_day(client, driver, billing, img):
    tid = make_trip(status="IN_TRANSIT")
    with SessionLocal() as db:
        db.get(Trip, uuid.UUID(tid)).delivery_date = None
        db.commit()
    yesterday = TODAY - timedelta(days=1)
    captured = (datetime.now(timezone.utc) - timedelta(hours=26)).replace(microsecond=0)
    MockProvider.enqueue(good(day=yesterday))
    r, _ = upload(client, driver, tid, img, captured_at=captured.isoformat())
    pod = client.get(f"/api/v1/pods/{r.json()['pod']['id']}", headers=billing).json()
    assert datetime.fromisoformat(pod["captured_at"]) == captured  # device time preserved as reported
    assert datetime.fromisoformat(pod["server_received_at"]) > captured + timedelta(hours=25)
    assert _trip(tid).delivery_date == yesterday  # from the document, not either timestamp


def test_human_correction_of_a_misread_delivery_date(client, driver, billing, img):
    tid = make_trip(status="IN_TRANSIT")
    with SessionLocal() as db:
        db.get(Trip, uuid.UUID(tid)).delivery_date = None
        db.commit()
    MockProvider.enqueue(good(day=TODAY - timedelta(days=2), conf=0.6))  # low confidence -> review
    pid = upload(client, driver, tid, img)[0].json()["pod"]["id"]
    right = (TODAY - timedelta(days=1)).isoformat()
    ok = client.post(f"/api/v1/pods/{pid}/review", headers=billing, json={
        "decision": "APPROVE", "corrections": {"delivery_date": right}, "correction_reason": "Stamp shows the 7th"})
    assert ok.status_code == 200
    t = _trip(tid)
    assert t.delivery_date.isoformat() == right and t.delivery_date_source == "pod_human"


def test_imported_date_differing_from_pod_needs_a_person(client, driver, billing, img):
    imported = TODAY - timedelta(days=1)
    tid = make_trip(delivery_date=imported)
    pod_day = imported - timedelta(days=1)
    MockProvider.enqueue(good(day=pod_day))
    pid = upload(client, driver, tid, img)[0].json()["pod"]["id"]
    pod = client.get(f"/api/v1/pods/{pid}", headers=billing).json()
    assert pod["verification_status"] == "NEEDS_REVIEW" and "DATE_DIFFERS_FROM_TRIP" in pod["review_reasons"]
    assert _trip(tid).delivery_date == imported  # unchanged until a person decides
    client.post(f"/api/v1/pods/{pid}/review", headers=billing, json={"decision": "APPROVE"})
    t = _trip(tid)
    assert t.delivery_date == pod_day and t.delivery_date_source == "pod_human"
    with SessionLocal() as db:
        a = db.scalar(select(AuditLog).where(AuditLog.action == "trip.delivery_date_confirmed"))
        assert a.previous_values["delivery_date"] == imported.isoformat() and a.meta["changed"] is True


# ---------- 8. business turnaround metrics ----------
def test_turnaround_never_treats_export_as_invoice(client, driver, billing, img):
    a, _ = verified_trip(client, driver, img, "TRP-A", "LR-A")
    b, _ = verified_trip(client, driver, img, "TRP-B", "LR-B")
    client.post("/api/v1/billing/exports", headers=billing, json={"trip_ids": [a, b]})
    t = client.get("/api/v1/dashboard/metrics", headers=billing).json()["turnaround"]
    assert t["delivery_to_pod_received"]["count"] == 2 and t["delivery_to_pod_verified"]["count"] == 2
    assert t["delivery_to_billing_export"]["count"] == 2
    assert t["delivery_to_invoice_recorded"] == {"avg_days": None, "median_days": None, "count": 0, "period": None}
    inv_day = TODAY
    bad = client.post(f"/api/v1/billing/trips/{a}/invoiced", headers=billing, json={"invoice_reference": "INV-1", "invoice_date": (TODAY + timedelta(days=1)).isoformat()})
    assert bad.status_code == 400
    client.post(f"/api/v1/billing/trips/{a}/invoiced", headers=billing, json={"invoice_reference": "INV-1", "invoice_date": inv_day.isoformat()})
    inv = client.get("/api/v1/dashboard/metrics", headers=billing).json()["turnaround"]["delivery_to_invoice_recorded"]
    assert inv["count"] == 1 and inv["avg_days"] == 1.0
    assert inv["period"] == {"from": (TODAY - timedelta(days=1)).isoformat(), "to": (TODAY - timedelta(days=1)).isoformat()}


# ---------- 10. missing-POD filters ----------
def test_missing_pod_filters_share_scope_with_dashboard(client, billing):
    make_trip("TRP-M1", "LR-M1", status="DELIVERED", delivery_date=TODAY - timedelta(days=10))
    make_trip("TRP-M2", "LR-M2", status="DELIVERED", delivery_date=TODAY - timedelta(days=1))
    m3 = make_trip("TRP-M3", "LR-M3", status="DELIVERED", delivery_date=TODAY - timedelta(days=6), client_code="CMPB")
    with SessionLocal() as db:
        db.get(Trip, uuid.UUID(m3)).billing_cycle = "2026-10-H2"
        db.commit()
    allm = client.get("/api/v1/dashboard/missing-pods", headers=billing).json()
    assert [i["trip_reference"] for i in allm["items"]] == ["TRP-M1", "TRP-M3", "TRP-M2"]
    item = allm["items"][0]
    for k in ("branch", "client", "billing_cycle", "days_since_delivery", "freight_amount", "pod_state", "driver", "driver_phone",
              "vehicle", "suggested_action"):
        assert k in item, k
    old = client.get("/api/v1/dashboard/missing-pods?min_days=5", headers=billing).json()
    assert [i["trip_reference"] for i in old["items"]] == ["TRP-M1", "TRP-M3"]
    assert old["freight_blocked"] == sum(i["freight_amount"] for i in old["items"])
    cyc = client.get("/api/v1/dashboard/missing-pods?billing_cycle=2026-10-H2", headers=billing).json()
    met = client.get("/api/v1/dashboard/metrics?billing_cycle=2026-10-H2", headers=billing).json()
    assert [i["trip_reference"] for i in cyc["items"]] == ["TRP-M3"] and met["trips_without_pod"] == 1
    assert cyc["filters"]["billing_cycle"] == met["filters"]["billing_cycle"] == "2026-10-H2"
    assert client.get(f"/api/v1/dashboard/missing-pods?client_id={_client_id(m3)}&branch=Pune", headers=billing).json()["items"][0]["trip_reference"] == "TRP-M3"
