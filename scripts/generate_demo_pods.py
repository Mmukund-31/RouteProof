"""Write the six synthetic POD test documents to demo_pods/ (all fictional).

Generate documents that MATCH the trip you will upload against, e.g. for a trip with LR-66162 delivered to Nashik Retail Depot:

    python scripts/generate_demo_pods.py --lr LR-66162 --consignee "Nashik Retail Depot" --qty 600 --unit bags --date 31/10/2026
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.demo_docs import SCENARIOS, render_pod  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "demo_pods"

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lr", default="LR-66141")
    ap.add_argument("--consignee", default="Indore Warehouse")
    ap.add_argument("--qty", type=int, default=100, help="expected delivered quantity (shortage scenario prints qty-6)")
    ap.add_argument("--unit", default="cartons")
    ap.add_argument("--date", default=(date.today() - timedelta(days=1)).strftime("%d/%m/%Y"), help="DD/MM/YYYY printed on the document")
    ap.add_argument("--client", default="Company D (Packaged Foods)")
    ap.add_argument("--vehicle", default="MH17 BY 3092")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    for i, name in enumerate(SCENARIOS, start=1):
        qty = a.qty - 6 if name == "shortage_remark" else a.qty
        data = render_pod(name, lr=a.lr, consignee=a.consignee, qty=qty, unit=a.unit, date_str=a.date, client=a.client, vehicle=a.vehicle, seed=i)
        (OUT / f"{i}_{name}.jpg").write_bytes(data)
        print("wrote", OUT / f"{i}_{name}.jpg", "-", SCENARIOS[name])
