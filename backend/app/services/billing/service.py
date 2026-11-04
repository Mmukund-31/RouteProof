import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import BadRequest, Conflict, NotFound
from app.models import BillingExport, BillingExportItem, Trip
from app.services.audit import audit
from app.services.billing.csv_export import build_csv
from app.services.billing.eligibility import blockers
from app.services.pods.state import billing_transition
from app.services.uploads.storage import get_storage


def create_export(db: Session, user_id, trip_ids: list[uuid.UUID], *, reexport: bool, reexport_reason: str | None,
                  billing_period: str | None, filters: dict | None) -> BillingExport:
    if not trip_ids:
        raise BadRequest("empty_selection", "Select at least one trip")
    trip_ids = list(dict.fromkeys(trip_ids))
    trips = list(db.scalars(select(Trip).where(Trip.id.in_(trip_ids))).unique())
    if len(trips) != len(trip_ids):
        raise NotFound("One or more trips")

    ineligible = {t.trip_reference: blockers(t) for t in trips if blockers(t)}
    ineligible.update({t.trip_reference: ["Already marked INVOICED"] for t in trips if t.billing_status == "INVOICED"})
    if ineligible:
        raise Conflict("not_eligible", "Some trips are not eligible for export", {"trips": ineligible})
    dupes = [t.trip_reference for t in trips if t.billing_status == "EXPORTED"]
    if dupes and not reexport:
        raise Conflict("duplicate_export", "Some trips were already exported. Re-export explicitly with a reason.", {"trips": dupes})
    if dupes and not (reexport_reason or "").strip():
        raise BadRequest("reason_required", "A reason is required to re-export trips")
    not_ready = [t.trip_reference for t in trips if t.billing_status not in ("BILLING_READY", "EXPORTED")]
    if not_ready:
        raise Conflict("not_eligible", "Trips are not billing-ready", {"trips": {r: ["Not billing-ready"] for r in not_ready}})

    trips.sort(key=lambda t: t.trip_reference)
    ref = f"RPX-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:5].upper()}"
    data = build_csv(ref, trips)
    path = f"exports/{ref}.csv"
    get_storage().put(path, data, "text/csv")

    client_ids = {t.client_id for t in trips}
    exp = BillingExport(
        export_reference=ref, client_id=next(iter(client_ids)) if len(client_ids) == 1 else None,
        billing_period=billing_period, filters=filters, trip_count=len(trips),
        total_freight=sum((t.freight_amount for t in trips), Decimal("0")), is_reexport=bool(dupes),
        reexport_reason=reexport_reason if dupes else None, file_path=path, created_by=user_id,
    )
    db.add(exp)
    db.flush()
    for t in trips:
        db.add(BillingExportItem(export_id=exp.id, trip_id=t.id, trip_reference=t.trip_reference))
        prev = billing_transition(t, "EXPORTED")
        audit(db, user_id, "trip", t.id, "trip.exported", {"billing_status": prev}, {"billing_status": "EXPORTED"},
              {"export": ref, "reexport": prev == "EXPORTED"})
    audit(db, user_id, "billing_export", exp.id, "billing.export_created", None,
          {"reference": ref, "trips": len(trips), "reexport": bool(dupes)}, {"reason": reexport_reason})
    db.commit()
    return exp


def mark_invoiced(db: Session, user_id, trip: Trip, invoice_reference: str) -> Trip:
    """Manual record of an EXTERNAL business event; RouteProof never issues invoices."""
    if not invoice_reference.strip():
        raise BadRequest("reason_required", "Invoice reference is required")
    prev = billing_transition(trip, "INVOICED")
    trip.invoice_reference = invoice_reference.strip()
    audit(db, user_id, "trip", trip.id, "trip.invoiced_recorded", {"billing_status": prev},
          {"billing_status": "INVOICED", "invoice_reference": trip.invoice_reference}, {"note": "recorded manually; issued outside RouteProof"})
    db.commit()
    return trip
