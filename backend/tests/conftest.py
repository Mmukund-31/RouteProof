import io
import os
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="routeproof_test_")
os.environ.update({
    "APP_ENV": "test", "DATABASE_URL": os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmp}/test.db"), "AI_PROVIDER": "mock",
    "STORAGE_LOCAL_DIR": f"{_tmp}/storage", "RATE_LIMIT_ENABLED": "false", "JWT_SECRET_KEY": "t" * 40,
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from app.core import ratelimit  # noqa: E402
from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.ai.mock import MockProvider  # noqa: E402
from app.services.uploads import storage  # noqa: E402
from app.models import *  # noqa: E402,F401
from app.services.seed import seed  # noqa: E402


def make_image(text="LR-66141") -> bytes:
    im = Image.new("RGB", (640, 480), "white")
    d = ImageDraw.Draw(im)
    for i in range(0, 480, 16):
        d.line([(0, i), (640, (i * 7) % 640)], fill="black", width=2)
    d.text((40, 40), text, fill="black")
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=70)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    storage.set_storage(None)
    MockProvider.reset()
    ratelimit.reset()
    with SessionLocal() as db:
        seed(db, with_demo_trips=False)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def login(client, email, password="Demo@12345"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def billing(client):
    return login(client, "billing@routeproof.demo")


@pytest.fixture
def driver(client):
    return login(client, "driver1@routeproof.demo")


@pytest.fixture
def driver2(client):
    return login(client, "driver2@routeproof.demo")


@pytest.fixture
def img():
    return make_image()
