"""Security and data handling, verified: route-wide authorization, image access, data minimisation, log hygiene,
retention/erasure, link auditing and production configuration."""
import json
import logging
import re
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.core.db import SessionLocal
from app.core.observability import RedactFilter, redact
from app.main import app
from app.models import AuditLog, ClientViewLink, DriverLink, Pod, Trip
from app.services import retention
from app.services.ai.mock import MockProvider, result
from app.services.uploads import storage
from tests.conftest import make_image
from tests.helpers import make_trip, upload

PUBLIC = ("/api/v1/auth/login", "/api/v1/driver-links/{token}", "/api/v1/client-view/{token}", "/health")


def good(lr="LR-66141"):
    from datetime import date

    return result(lr=lr, consignee="Indore Warehouse", qty=100, unit="cartons", date=(date.today() - timedelta(days=1)).isoformat())


def _routes():
    """Every documented endpoint with its full path (FastAPI >= 0.16x includes routers lazily, so app.routes is not flat)."""
    for path, ops in app.openapi()["paths"].items():
        for m in ops:
            if m.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                yield m.upper(), path


def _fill(path, **ids):
    out = path
    for k, v in ids.items():
        out = out.replace("{" + k + "}", str(v))
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), out)


# ---------- authorization across every endpoint ----------
def test_every_non_public_endpoint_requires_authentication(client):
    checked = 0
    for method, path in _routes():
        if path.startswith(PUBLIC):
            continue
        r = client.request(method, _fill(path))
        assert r.status_code in (401, 403), (method, path, r.status_code)
        checked += 1
    assert checked > 30


def test_no_endpoint_lets_a_driver_read_or_change_another_drivers_trip_or_pod(client, driver, driver2, img):
    tid = make_trip()  # assigned to driver1
    MockProvider.enqueue(good())
    pid = upload(client, driver, tid, img)[0].json()["pod"]["id"]
    with SessionLocal() as db:
        trip = db.get(Trip, uuid.UUID(tid))
        trip.delivery_date = trip.delivery_date  # no-op, keeps the row loaded
    leaks = []
    for method, path in _routes():
        if "{trip_id}" not in path and "{pod_id}" not in path:
            continue
        files = {"file": ("x.jpg", make_image(), "image/jpeg")} if method == "POST" else None
        r = client.request(method, _fill(path, trip_id=tid, pod_id=pid), headers={**driver2, "Idempotency-Key": uuid.uuid4().hex},
                           files=files, json=None if files else ({"decision": "APPROVE"} if path.endswith("/review") else None))
        if r.status_code < 400:
            leaks.append((method, path, r.status_code))
    assert leaks == []
    # and the owner still can, so the sweep above is meaningful
    assert client.get(f"/api/v1/pods/{pid}", headers=driver).status_code == 200


def test_driver_lists_only_contain_their_own_pods(client, driver, driver2, img):
    tid = make_trip()
    MockProvider.enqueue(good())
    key = upload(client, driver, tid, img)[1]
    assert client.get("/api/v1/driver/uploads", headers=driver2).json()["items"] == []
    assert client.get("/api/v1/driver/trips", headers=driver2).json()["items"] == []
    sync = client.post("/api/v1/driver/uploads/sync", headers=driver2, json={"keys": [key]}).json()["items"][0]
    assert sync["received"] is False and sync["pod_id"] is None  # cannot even learn the upload exists


@pytest.mark.parametrize("variant", ["upload", "original"])
def test_images_require_authorization(client, driver, driver2, billing, img, variant):
    MockProvider.enqueue(good())
    pid = upload(client, driver, make_trip(), img)[0].json()["pod"]["id"]
    client.post(f"/api/v1/pods/{pid}/original", headers=driver, files={"file": ("o.jpg", img, "image/jpeg")})
    url = f"/api/v1/pods/{pid}/image?variant={variant}"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=driver2).status_code == 404
    assert client.get(url, headers=driver).status_code == 200
    r = client.get(url, headers=billing)
    assert r.status_code == 200 and r.headers["Cache-Control"] == "private, no-store"


# ---------- data minimisation ----------
def test_phone_numbers_are_not_exposed_or_stored_in_full(client, billing, driver, img):
    tid = make_trip()
    client.post("/api/v1/driver-links", headers=billing, json={"trip_id": tid, "phone": "9876543210"})
    with SessionLocal() as db:
        blob = json.dumps([[a.previous_values, a.new_values, a.meta] for a in db.scalars(select(AuditLog))], default=str)
        assert "9876543210" not in blob
        assert db.scalars(select(DriverLink)).one().phone_masked.endswith("3210")
    for path in ("/api/v1/driver/trips", f"/api/v1/trips/{tid}", "/api/v1/auth/me"):
        body = client.get(path, headers=driver).text
        assert "9000000001" not in body and "freight" not in body, path


def test_missing_pod_list_shows_driver_phone_only_where_calling_is_the_action(client, billing):
    make_trip("TRP-O", "LR-O", status="DELIVERED")
    with SessionLocal() as db:  # make a second trip use a hired vehicle
        from app.models import Vehicle

        hired = db.scalar(select(Vehicle).where(Vehicle.ownership_type == "hired"))
        tid = make_trip("TRP-H", "LR-H", status="DELIVERED")
        db.get(Trip, uuid.UUID(tid)).vehicle_id = hired.id
        db.commit()
    rows = {i["trip_reference"]: i for i in client.get("/api/v1/dashboard/missing-pods", headers=billing).json()["items"]}
    assert rows["TRP-O"]["driver_phone"] and rows["TRP-O"]["suggested_action"] == "call_driver"
    assert rows["TRP-H"]["driver_phone"] is None and rows["TRP-H"]["suggested_action"] == "send_upload_link"


# ---------- log hygiene ----------
def test_redaction_of_tokens_phones_and_bearer_values():
    line = 'GET /api/v1/driver-links/AbCdEfGhIjKlMnOpQrStUvWxYz0123456789/pods "+91 9876543210" Bearer eyJhbGciOi.payload.sig'
    out = redact(line)
    assert "AbCdEfGh" not in out and "9876543210" not in out and "eyJhbGciOi" not in out
    assert "/driver-links/[redacted]" in out and out.count("3210") == 1
    assert redact("pod 2ba188df-c0e9-468e-9ad0-ef135d18e032 trip TRP-66141") == "pod 2ba188df-c0e9-468e-9ad0-ef135d18e032 trip TRP-66141"


def test_uvicorn_style_access_lines_are_scrubbed():
    rec = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/1.1" %d', ("1.2.3.4", "GET",
                            "/api/v1/client-view/AbCdEfGhIjKlMnOpQrStUvWxYz0123/trips/x/pod-image", 200), None)
    RedactFilter().filter(rec)
    assert "AbCdEfGh" not in rec.getMessage() and "/client-view/[redacted]/" in rec.getMessage()


def test_app_access_log_uses_route_templates_not_raw_paths(client, billing, caplog):
    token = client.post("/api/v1/driver-links", headers=billing, json={"trip_id": make_trip()}).json()["url"].rsplit("/", 1)[1]
    with caplog.at_level(logging.INFO, logger="routeproof.http"):
        client.get(f"/api/v1/driver-links/{token}")
    routes = [str(getattr(r, "route", "")) for r in caplog.records if r.name == "routeproof.http"]
    assert any(r.endswith("/driver-links/{token}") for r in routes), routes
    assert all(token not in (r.getMessage() + str(getattr(r, "route", ""))) for r in caplog.records)


# ---------- retention and controlled deletion ----------
def _invoiced_pod(client, driver, billing, img, ref="TRP-R", lr="LR-R", days_ago=4000):
    tid = make_trip(ref, lr)
    MockProvider.enqueue(good(lr))
    pid = upload(client, driver, tid, img)[0].json()["pod"]["id"]
    client.post("/api/v1/billing/exports", headers=billing, json={"trip_ids": [tid]})
    client.post(f"/api/v1/billing/trips/{tid}/invoiced", headers=billing, json={"invoice_reference": "INV-R"})
    with SessionLocal() as db:
        t = db.get(Trip, uuid.UUID(tid))
        t.invoiced_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
        db.commit()
    return tid, pid


def test_retention_schedule_is_a_dry_run_until_applied_and_respects_holds(client, driver, billing, img):
    old_tid, old_pid = _invoiced_pod(client, driver, billing, img)
    _recent_tid, recent_pid = _invoiced_pod(client, driver, billing, img, "TRP-N", "LR-N", days_ago=10)
    open_tid = make_trip("TRP-OPEN", "LR-OPEN")
    MockProvider.enqueue(result(lr="LR-OPEN", consignee="Indore Warehouse", qty=94, unit="cartons", shortage=True, remarks="short"))
    open_pid = upload(client, driver, open_tid, img)[0].json()["pod"]["id"]
    with SessionLocal() as db:
        db.get(Pod, uuid.UUID(open_pid)).server_received_at = datetime.now(timezone.utc) - timedelta(days=5000)
        db.commit()
        dry = retention.run(db)
        assert [p["pod_id"] for p in dry["pods_due"]] == [old_pid] and dry["dry_run"] and dry["pods_purged"] == []
        assert db.get(Pod, uuid.UUID(old_pid)).images_purged_at is None  # nothing deleted in a dry run
        done = retention.run(db, apply=True)
        assert done["pods_purged"] == [old_pid]
        pod = db.get(Pod, uuid.UUID(old_pid))
        assert pod.images_purged_at and pod.images_purge_reason.startswith("retention schedule")
        assert not Path(storage.get_storage().root / pod.uploaded_image_path).exists()
        assert db.get(Trip, uuid.UUID(old_tid)).lr_number == "LR-R"  # the record stays
        assert db.get(Pod, uuid.UUID(recent_pid)).images_purged_at is None
        assert db.get(Pod, uuid.UUID(open_pid)).images_purged_at is None  # open review: on hold
        assert db.scalar(select(AuditLog).where(AuditLog.action == "pod.images_purged"))
    r = client.get(f"/api/v1/pods/{old_pid}/image", headers=billing)
    assert r.status_code == 410 and r.json()["error"]["code"] == "image_purged"
    assert client.get(f"/api/v1/pods/{old_pid}", headers=billing).json()["images_purged_at"]


def test_targeted_erasure_needs_a_reason_and_honours_holds(client, driver, billing, img):
    tid = make_trip()
    MockProvider.enqueue(good())
    pid = upload(client, driver, tid, img)[0].json()["pod"]["id"]  # verified, not yet invoiced
    with SessionLocal() as db:
        pod = db.get(Pod, uuid.UUID(pid))
        with pytest.raises(Exception, match="reason"):
            retention.purge_pod_images(db, pod, reason=" ")
        with pytest.raises(Exception, match="hold"):
            retention.purge_pod_images(db, pod, reason="DPR-1")
        retention.purge_pod_images(db, pod, reason="DPR-1 approved", override_hold=True)
        a = db.scalar(select(AuditLog).where(AuditLog.action == "pod.images_purged"))
        assert a.meta == {"reason": "DPR-1 approved", "override_hold": True}


def test_client_view_hides_purged_images(client, driver, billing, img):
    tid, pid = _invoiced_pod(client, driver, billing, img)
    with SessionLocal() as db:
        cid = str(db.get(Trip, uuid.UUID(tid)).client_id)
    token = client.post("/api/v1/client-links", headers=billing, json={"client_id": cid, "trip_ids": [tid]}).json()["url"].rsplit("/", 1)[1]
    with SessionLocal() as db:
        retention.run(db, apply=True)
    row = client.get(f"/api/v1/client-view/{token}").json()["trips"][0]
    assert row["has_image"] is False
    assert client.get(f"/api/v1/client-view/{token}/trips/{tid}/pod-image").status_code == 404


def test_access_logs_are_purged_after_retention_and_the_purge_is_recorded(client, billing):
    token = client.post("/api/v1/driver-links", headers=billing, json={"trip_id": make_trip()}).json()["url"].rsplit("/", 1)[1]
    client.get(f"/api/v1/driver-links/{token}")
    with SessionLocal() as db:
        for a in db.scalars(select(AuditLog).where(AuditLog.action == "driver_link.opened")):
            a.timestamp = datetime.now(timezone.utc) - timedelta(days=400)
        db.commit()
        assert retention.purge_access_logs(db) == 1  # dry run counts
        assert retention.purge_access_logs(db, apply=True) == 1
        assert db.scalar(select(AuditLog).where(AuditLog.action == "driver_link.opened")) is None
        assert db.scalar(select(AuditLog).where(AuditLog.action == "driver_link.created"))  # state changes kept
        assert db.scalar(select(AuditLog).where(AuditLog.action == "retention.access_logs_purged")).new_values == {"rows": 1}


def test_client_link_lifecycle_is_fully_audited(client, billing, driver, img):
    tid = make_trip()
    with SessionLocal() as db:
        cid = str(db.get(Trip, uuid.UUID(tid)).client_id)
    a = client.post("/api/v1/client-links", headers=billing, json={"client_id": cid, "trip_ids": [tid]}).json()
    b = client.post("/api/v1/client-links", headers=billing, json={"client_id": cid, "trip_ids": [tid]}).json()
    client.get(f"/api/v1/client-view/{a['url'].rsplit('/', 1)[1]}")
    client.post(f"/api/v1/client-links/{a['id']}/revoke", headers=billing)
    client.get(f"/api/v1/client-view/{a['url'].rsplit('/', 1)[1]}")  # after revocation
    with SessionLocal() as db:
        db.get(ClientViewLink, uuid.UUID(b["id"])).expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
        assert retention.record_link_expiries(db) == 1
        assert retention.record_link_expiries(db) == 0  # recorded once
        acts = [(x.entity_id, x.action) for x in db.scalars(select(AuditLog).where(AuditLog.entity_type == "client_link"))]
    assert {(a["id"], "client_link.created"), (a["id"], "client_link.opened"), (a["id"], "client_link.revoked"),
            (a["id"], "client_link.access_denied"), (b["id"], "client_link.expired")} <= set(acts)
    assert (a["id"], "client_link.expired") not in acts  # revoked links end by revocation, not expiry


# ---------- production configuration ----------
PROD = dict(app_env="production", jwt_secret_key="x" * 40, ai_provider="manual", database_url="postgresql://u:p@db/x",
            public_app_url="https://routeproof.example", cors_allowed_origins="https://routeproof.example")


def test_production_configuration_accepts_a_secure_setup():
    s = Settings(_env_file=None, **PROD)
    assert s.cookie_secure is True


@pytest.mark.parametrize("override,msg", [
    (dict(cookie_secure=False), "COOKIE_SECURE"),
    (dict(public_app_url="http://routeproof.example"), "PUBLIC_APP_URL"),
    (dict(cors_allowed_origins="*"), "CORS_ALLOWED_ORIGINS"),
    (dict(cors_allowed_origins="http://routeproof.example"), "CORS_ALLOWED_ORIGINS"),
    (dict(jwt_secret_key="short"), "JWT_SECRET_KEY"),
    (dict(database_url="sqlite:///x.db"), "PostgreSQL"),
])
def test_production_configuration_refuses_insecure_settings(override, msg):
    with pytest.raises(ValueError, match=msg):
        Settings(_env_file=None, **{**PROD, **override})


def test_seed_refuses_demo_accounts_in_production(monkeypatch):
    from app.core import config
    from app.services.seed import seed

    monkeypatch.setattr(config.get_settings(), "app_env", "production")
    with SessionLocal() as db, pytest.raises(RuntimeError, match="ALLOW_DEMO_ACCOUNTS"):
        seed(db, with_demo_trips=False)
    monkeypatch.setattr(config.get_settings(), "allow_demo_accounts", True)
    with SessionLocal() as db:
        seed(db, with_demo_trips=False)  # explicit opt-in for a public demo works


# ---------- repository hygiene ----------
def _tracked() -> list[str] | None:
    root = Path(__file__).resolve().parents[2]
    try:
        out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.splitlines() if out.returncode == 0 else None


SECRET = re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
                    r"(?i:(?:jwt_secret_key|ai_api_key|storage_secret_key|password)[ \t]*=[ \t]*(?!CHANGE_ME|routeproof_local_only)[^\s#'\"]{12,})")


def test_no_secrets_or_generated_artifacts_are_committed():
    files = _tracked()
    if files is None:
        pytest.skip("not a git checkout (e.g. running inside the backend container)")
    root = Path(__file__).resolve().parents[2]
    forbidden = [f for f in files if re.search(r"(^|/)\.env$|\.db$|^backend/storage/|^demo_pods/|^graphify-out/|\.pem$", f)]
    assert forbidden == []
    hits = []
    for f in files:
        p = root / f
        if p.suffix in {".png", ".jpg", ".ico", ".lock"} or p.name == "package-lock.json" or not p.is_file():
            continue
        if SECRET.search(p.read_text(encoding="utf-8", errors="ignore")):
            hits.append(f)
    assert hits == []
