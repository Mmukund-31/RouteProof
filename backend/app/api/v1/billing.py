import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_billing
from app.core.db import get_db
from app.core.errors import NotFound
from app.models import BillingExport, Trip, User, aware
from app.repositories.trips import TripFilters, apply_filters
from app.schemas.requests import ExportIn, InvoicedIn
from app.schemas.serializers import page
from app.services.audit import audit
from app.services.billing.eligibility import blockers, pod_reference
from app.services.billing.service import create_export, mark_invoiced
from app.services.uploads.storage import get_storage

router = APIRouter(prefix="/billing", tags=["billing"])


def _queue_row(t: Trip) -> dict:
    p = t.pods[-1]
    return {
        "id": str(t.id), "trip_reference": t.trip_reference, "lr_number": t.lr_number, "eway_bill_number": t.eway_bill_number,
        "client": {"id": str(t.client.id), "name": t.client.company_name}, "destination": t.destination,
        "vehicle": t.vehicle.registration_number, "freight_amount": f"{t.freight_amount:.2f}",
        "delivery_date": t.delivery_date.isoformat() if t.delivery_date else None, "billing_cycle": t.billing_cycle,
        "pod_reference": pod_reference(t, p), "pod_verified_at": aware(p.verified_at).isoformat() if p.verified_at else None,
        "verification_method": p.verification_method, "export_status": "EXPORTED" if t.billing_status == "EXPORTED" else "NOT_EXPORTED",
        "billing_status": t.billing_status,
    }


@router.get("/queue")
def queue(q: str | None = None, client_id: uuid.UUID | None = None, billing_cycle: str | None = None,
          date_from: date | None = None, date_to: date | None = None,
          export_status: str | None = Query(None, pattern="^(EXPORTED|NOT_EXPORTED)$"),
          page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(20, ge=1, le=100),
          user: User = Depends(require_billing), db: Session = Depends(get_db)):
    f = TripFilters(q=q, client_id=client_id, billing_cycle=billing_cycle, date_from=date_from, date_to=date_to)
    statuses = {"EXPORTED": ["EXPORTED"], "NOT_EXPORTED": ["BILLING_READY"]}.get(export_status or "", ["BILLING_READY", "EXPORTED"])
    base = apply_filters(select(Trip.id), f).where(Trip.billing_status.in_(statuses))
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    stmt = (apply_filters(select(Trip), f).where(Trip.billing_status.in_(statuses))
            .order_by(Trip.delivery_date.desc().nullslast(), Trip.trip_reference).limit(page_size).offset((page_no - 1) * page_size))
    trips = [t for t in db.scalars(stmt).unique() if not blockers(t)]
    sums = db.execute(apply_filters(select(func.coalesce(func.sum(Trip.freight_amount), 0)), f).where(Trip.billing_status.in_(statuses))).scalar()
    out = page([_queue_row(t) for t in trips], total, page_no, page_size)
    out["total_freight"] = f"{sums:.2f}"
    return out


def _exp_out(e: BillingExport) -> dict:
    return {"id": str(e.id), "export_reference": e.export_reference, "client": e.client.company_name if e.client else "Multiple clients",
            "billing_period": e.billing_period, "trip_count": e.trip_count, "total_freight": f"{e.total_freight:.2f}",
            "is_reexport": e.is_reexport, "reexport_reason": e.reexport_reason, "filters": e.filters,
            "created_at": aware(e.created_at).isoformat(), "trip_references": [i.trip_reference for i in e.items]}


@router.post("/exports", status_code=201)
def make_export(body: ExportIn, user: User = Depends(require_billing), db: Session = Depends(get_db)):
    e = create_export(db, user.id, body.trip_ids, reexport=body.reexport, reexport_reason=body.reexport_reason,
                      billing_period=body.billing_period, filters=body.filters)
    return _exp_out(e)


@router.get("/exports")
def list_exports(page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(20, ge=1, le=100),
                 user: User = Depends(require_billing), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(BillingExport))
    rows = db.scalars(select(BillingExport).order_by(BillingExport.created_at.desc()).limit(page_size).offset((page_no - 1) * page_size)).unique()
    return page([_exp_out(e) for e in rows], total, page_no, page_size)


@router.get("/exports/{export_id}/download")
def download(export_id: uuid.UUID, user: User = Depends(require_billing), db: Session = Depends(get_db)):
    e = db.get(BillingExport, export_id)
    if not e:
        raise NotFound("Export")
    audit(db, user.id, "billing_export", e.id, "billing.export_downloaded")
    db.commit()
    return Response(get_storage().get(e.file_path), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{e.export_reference}.csv"', "Cache-Control": "private, no-store"})


@router.post("/trips/{trip_id}/invoiced")
def invoiced(trip_id: uuid.UUID, body: InvoicedIn, user: User = Depends(require_billing), db: Session = Depends(get_db)):
    t = db.get(Trip, trip_id)
    if not t:
        raise NotFound("Trip")
    mark_invoiced(db, user.id, t, body.invoice_reference)
    return {"id": str(t.id), "billing_status": t.billing_status, "invoice_reference": t.invoice_reference}
