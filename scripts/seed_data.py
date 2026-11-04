"""Seed demo data (idempotent). Usage (from repo root): python scripts/seed_data.py [--users-only]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.db import SessionLocal  # noqa: E402
from app.services.seed import seed  # noqa: E402

if __name__ == "__main__":
    with SessionLocal() as db:
        print(seed(db, with_demo_trips="--users-only" not in sys.argv))
