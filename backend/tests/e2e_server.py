"""Deterministic backend for Playwright e2e: fresh SQLite DB, demo seed, mock AI keyed on the trip's LR number.

    python tests/e2e_server.py   ->  http://localhost:8100
"""
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
tmp = tempfile.mkdtemp(prefix="rp_e2e_")
os.environ.update({
    "APP_ENV": "test", "DATABASE_URL": f"sqlite:///{tmp}/e2e.db", "STORAGE_LOCAL_DIR": f"{tmp}/storage", "AI_PROVIDER": "mock",
    "CORS_ALLOWED_ORIGINS": "http://localhost:3100", "RATE_LIMIT_ENABLED": "false", "PUBLIC_APP_URL": "http://localhost:3100",
    "JWT_SECRET_KEY": "e" * 40,
})

import uvicorn  # noqa: E402

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Client, Trip, User, Vehicle  # noqa: E402
from app.services.ai.mock import MockProvider, result  # noqa: E402
from app.services.seed import seed  # noqa: E402
from sqlalchemy import select  # noqa: E402


def fixture(ctx):
    """Reads the *trip's* LR (as a stand-in for what the document says). E2E-A* trips: clean; E2E-S: shortage; E2E-T: timeout."""
    d = (date.today() - timedelta(days=1)).isoformat()
    if ctx.lr_number == "LR-E2E-S":
        return result(lr=ctx.lr_number, consignee=ctx.consignee_name, qty=94, unit="cartons", date=d, shortage=True, remarks="Short by 6 cartons")
    if ctx.lr_number == "LR-E2E-X":
        from app.services.ai.base import AIProviderError
        raise AIProviderError("timeout", "AI provider timed out")
    if ctx.lr_number == "LR-E2E-R":
        return result(lr=ctx.lr_number, consignee=ctx.consignee_name, qty=100, unit="cartons", date=d, stamp=False)
    return result(lr=ctx.lr_number, consignee=ctx.consignee_name, qty=100, unit="cartons", date=d)


MockProvider.default = staticmethod(fixture)

Base.metadata.create_all(engine)
with SessionLocal() as db:
    seed(db)
    client = db.scalar(select(Client).where(Client.client_code == "CMPD"))
    veh = db.scalar(select(Vehicle))
    drv = db.scalar(select(User).where(User.email == "driver4@routeproof.demo"))
    from decimal import Decimal
    hired = db.scalar(select(Vehicle).where(Vehicle.ownership_type == "hired"))
    # H: hired vehicle, no account (upload link). OFF2/DUP/TMO: offline durability. CL: client view.
    for suffix in ("A", "A2", "S", "X", "R", "OFF", "OFF2", "DUP", "TMO", "CL", "OUT", "H"):
        db.add(Trip(trip_reference=f"TRP-E2E-{suffix}", lr_number=f"LR-E2E-{suffix}", eway_bill_number="331099990000", client_id=client.id,
                    vehicle_id=hired.id if suffix == "H" else veh.id,
                    driver_id=None if suffix == "H" else drv.id, origin="Chhatrapati Sambhajinagar", destination="Indore", branch="Pune", consignee_name="Indore Warehouse",
                    expected_quantity=Decimal(100), quantity_unit="cartons", freight_amount=Decimal(40000), trip_status="IN_TRANSIT",
                    billing_cycle="2026-11-H1", delivery_date=date.today() - timedelta(days=1)))
    db.commit()

if __name__ == "__main__":
    # E2E_HOST=0.0.0.0 when the server runs inside a container (port published to the host's 127.0.0.1:8100).
    uvicorn.run(app, host=os.environ.get("E2E_HOST", "127.0.0.1"), port=8100, log_level="warning")
