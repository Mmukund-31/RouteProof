"""Write synthetic POD test documents to demo_pods/ (all fictional).

Default: one document per client sample trip (TRP-66120 clear, TRP-66134 missing stamp, TRP-66141 short by 6 cartons),
printed with EXACTLY the values of the seeded trip record - LR, consignee, client, vehicle, quantity, unit and delivery
date. The delivery date is read from the database when it is reachable (the seed stores dates relative to the day it
ran); otherwise it is computed the same way the seed does. A mismatched photo would look like an AI error in the demo.

    python scripts/generate_demo_pods.py                      # the three sample trips
    python scripts/generate_demo_pods.py --lr LR-66162 --consignee "Nashik Retail Depot" --qty 600 --unit bags \\
        --date 31/10/2026 --client "Company B (Cement)" --vehicle "MH20 AB 1101"   # all six scenarios for another trip
"""
import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.demo_docs import SCENARIOS, render_pod  # noqa: E402
from app.services.sample_trips import SAMPLE_TRIPS  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "demo_pods"


def seeded_delivery_dates() -> dict[str, date]:
    """Delivery dates as actually stored by the seed, if the database is reachable."""
    try:
        from sqlalchemy import select

        from app.core.db import SessionLocal
        from app.models import Trip

        with SessionLocal() as db:
            rows = db.execute(select(Trip.trip_reference, Trip.delivery_date).where(Trip.trip_reference.in_([t.ref for t in SAMPLE_TRIPS])))
            return {r: d for r, d in rows if d}
    except Exception:
        return {}


def sample_documents() -> None:
    stored = seeded_delivery_dates()
    for t in SAMPLE_TRIPS:
        d = stored.get(t.ref) or t.delivery_date()
        data = render_pod(t.scenario, lr=t.lr, consignee=t.consignee, qty=t.printed_qty, unit=t.unit, date_str=d.strftime("%d/%m/%Y"),
                          client=t.client_name, vehicle=t.vehicle, seed=int(t.ref[-5:]))
        name = f"{t.ref}_{t.scenario}.jpg"
        (OUT / name).write_bytes(data)
        src = "database" if t.ref in stored else "computed (no database)"
        print(f"wrote {OUT / name} - {t.ref} {t.lr} {t.printed_qty} {t.unit} delivered {d:%d/%m/%Y} [{src}] -> expect {t.expected_status}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lr", help="generate all six scenarios for this LR instead of the three sample trips")
    ap.add_argument("--consignee", default="Indore Warehouse")
    ap.add_argument("--qty", type=int, default=100, help="expected delivered quantity (shortage scenario prints qty-6)")
    ap.add_argument("--unit", default="cartons")
    ap.add_argument("--date", default=date.today().strftime("%d/%m/%Y"), help="DD/MM/YYYY printed on the document (use the trip's delivery date)")
    ap.add_argument("--client", default="Company D (Packaged Foods)")
    ap.add_argument("--vehicle", default="MH17 BY 3092")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    if not a.lr:
        sample_documents()
        sys.exit(0)
    for i, name in enumerate(SCENARIOS, start=1):
        qty = a.qty - 6 if name == "shortage_remark" else a.qty
        data = render_pod(name, lr=a.lr, consignee=a.consignee, qty=qty, unit=a.unit, date_str=a.date, client=a.client, vehicle=a.vehicle, seed=i)
        (OUT / f"{i}_{name}.jpg").write_bytes(data)
        print("wrote", OUT / f"{i}_{name}.jpg", "-", SCENARIOS[name])
