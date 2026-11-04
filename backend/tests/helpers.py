import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Client, Trip, User, Vehicle


def make_trip(ref="TRP-T1", lr="LR-66141", driver="driver1@routeproof.demo", qty=100, unit="cartons", consignee="Indore Warehouse",
              freight=41200, status="IN_TRANSIT", delivery_date=None, client_code="CMPD") -> str:
    with SessionLocal() as db:
        drv = db.scalar(select(User).where(User.email == driver))
        client = db.scalar(select(Client).where(Client.client_code == client_code))
        veh = db.scalar(select(Vehicle))
        t = Trip(trip_reference=ref, lr_number=lr, eway_bill_number="331000000001", client_id=client.id, vehicle_id=veh.id,
                 driver_id=drv.id, origin="Chhatrapati Sambhajinagar", destination="Indore", branch="Pune",
                 consignee_name=consignee, expected_quantity=Decimal(qty) if qty else None, quantity_unit=unit,
                 freight_amount=Decimal(freight), trip_status=status, delivery_date=delivery_date or date.today() - timedelta(days=1),
                 billing_cycle="2026-11-H1")
        db.add(t)
        db.commit()
        return str(t.id)


def upload(client, headers, trip_id, img, key=None, **extra):
    key = key or uuid.uuid4().hex
    return client.post(f"/api/v1/trips/{trip_id}/pods", headers={**headers, "Idempotency-Key": key},
                       files={"file": ("pod.jpg", img, "image/jpeg")}, data={"captured_at": "2026-11-03T09:30:00Z", "latitude": "19.87",
                                                                              "longitude": "75.34", **extra}), key
