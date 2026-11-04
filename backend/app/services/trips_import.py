import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Client, Trip, User, Vehicle
from app.services.audit import audit

REQUIRED = ["trip_reference", "lr_number", "eway_bill_number", "client_code", "vehicle_registration", "destination", "freight_amount"]
OPTIONAL = ["origin", "branch", "commodity", "consignee_name", "expected_quantity", "quantity_unit", "driver_email",
            "delivery_date", "billing_cycle", "vehicle_type", "ownership_type"]
MAX_ROWS = 2000


def import_trips(db: Session, user_id, raw: bytes, dry_run: bool) -> dict:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return {"fatal": "File must be UTF-8 encoded CSV", "created": 0, "duplicates": [], "errors": [], "dry_run": dry_run}
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED if c not in headers]
    unknown = [h for h in headers if h not in REQUIRED + OPTIONAL]
    if missing:
        return {"fatal": f"Missing required column(s): {', '.join(missing)}", "created": 0, "duplicates": [], "errors": [],
                "unknown_columns": unknown, "dry_run": dry_run}

    clients = {c.client_code.lower(): c for c in db.scalars(select(Client))}
    existing_refs = set(db.scalars(select(Trip.trip_reference)))
    existing_lrs = set(db.scalars(select(Trip.lr_number)))
    seen_refs, seen_lrs = set(), set()
    created, dupes, errors = [], [], []

    for i, raw_row in enumerate(reader, start=2):
        if i - 1 > MAX_ROWS:
            errors.append({"row": i, "message": f"Row limit of {MAX_ROWS} exceeded; remaining rows ignored"})
            break
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}
        blank = [c for c in REQUIRED if not row.get(c)]
        if blank:
            errors.append({"row": i, "message": f"Missing value(s): {', '.join(blank)}"})
            continue
        ref, lr = row["trip_reference"], row["lr_number"]
        if ref in existing_refs or lr in existing_lrs or ref in seen_refs or lr in seen_lrs:
            dupes.append({"row": i, "trip_reference": ref, "lr_number": lr})
            continue
        client = clients.get(row["client_code"].lower())
        if not client:
            errors.append({"row": i, "message": f"Unknown client_code {row['client_code']}"})
            continue
        try:
            freight = Decimal(row["freight_amount"].replace(",", ""))
            if freight < 0:
                raise InvalidOperation
        except InvalidOperation:
            errors.append({"row": i, "message": "freight_amount must be a non-negative number"})
            continue
        try:
            dd = date.fromisoformat(row["delivery_date"]) if row.get("delivery_date") else None
        except ValueError:
            errors.append({"row": i, "message": "delivery_date must be YYYY-MM-DD"})
            continue
        try:
            eq = Decimal(row["expected_quantity"]) if row.get("expected_quantity") else None
        except InvalidOperation:
            errors.append({"row": i, "message": "expected_quantity must be a number"})
            continue
        driver = None
        if row.get("driver_email"):
            driver = db.scalar(select(User).where(User.email == row["driver_email"].lower(), User.role == "driver"))
            if not driver:
                errors.append({"row": i, "message": f"Unknown driver_email {row['driver_email']}"})
                continue
        own = (row.get("ownership_type") or "hired").lower()
        if own not in ("owned", "hired"):
            errors.append({"row": i, "message": "ownership_type must be owned or hired"})
            continue

        seen_refs.add(ref)
        seen_lrs.add(lr)
        created.append(ref)
        if dry_run:
            continue
        reg = row["vehicle_registration"].upper()
        veh = db.scalar(select(Vehicle).where(Vehicle.registration_number == reg))
        if not veh:
            veh = Vehicle(registration_number=reg, vehicle_type=row.get("vehicle_type") or "Truck", ownership_type=own)
            db.add(veh)
            db.flush()
        t = Trip(trip_reference=ref, lr_number=lr, eway_bill_number=row["eway_bill_number"], client_id=client.id, vehicle_id=veh.id,
                 driver_id=driver.id if driver else None, origin=row.get("origin") or "Chhatrapati Sambhajinagar",
                 destination=row["destination"], branch=row.get("branch") or None, commodity=row.get("commodity") or None,
                 consignee_name=row.get("consignee_name") or None, expected_quantity=eq, quantity_unit=row.get("quantity_unit") or None,
                 freight_amount=freight, delivery_date=dd, billing_cycle=row.get("billing_cycle") or None,
                 trip_status="DELIVERED" if dd else "IN_TRANSIT")
        db.add(t)
        db.flush()
        audit(db, user_id, "trip", t.id, "trip.imported", None, {"trip_reference": ref, "lr_number": lr})
    if not dry_run:
        db.commit()
    return {"fatal": None, "dry_run": dry_run, "created": len(created), "created_references": created[:200],
            "duplicates": dupes, "errors": errors, "unknown_columns": unknown}
