from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import Client, Pod, Trip, Vehicle


@dataclass
class TripFilters:
    q: str | None = None
    client_id: object = None
    branch: str | None = None
    destination: str | None = None
    vehicle: str | None = None
    trip_status: str | None = None
    pod_status: str | None = None
    billing_status: str | None = None
    billing_cycle: str | None = None
    driver_id: object = None
    date_from: date | None = None
    date_to: date | None = None


def latest_pod_status_expr():
    return (
        select(Pod.verification_status).where(Pod.trip_id == Trip.id).order_by(Pod.attempt_number.desc()).limit(1)
        .correlate(Trip).scalar_subquery()
    )


def apply_filters(stmt: Select, f: TripFilters) -> Select:
    stmt = stmt.join(Client, Client.id == Trip.client_id).join(Vehicle, Vehicle.id == Trip.vehicle_id)
    if f.q:
        like = f"%{f.q.strip()}%"
        stmt = stmt.where(or_(Trip.trip_reference.ilike(like), Trip.lr_number.ilike(like), Trip.eway_bill_number.ilike(like),
                              Client.company_name.ilike(like), Vehicle.registration_number.ilike(like),
                              Trip.destination.ilike(like)))
    if f.client_id:
        stmt = stmt.where(Trip.client_id == f.client_id)
    if f.branch:
        stmt = stmt.where(Trip.branch == f.branch)
    if f.destination:
        stmt = stmt.where(Trip.destination.ilike(f"%{f.destination}%"))
    if f.vehicle:
        stmt = stmt.where(Vehicle.registration_number.ilike(f"%{f.vehicle}%"))
    if f.trip_status:
        stmt = stmt.where(Trip.trip_status == f.trip_status)
    if f.billing_status:
        stmt = stmt.where(Trip.billing_status == f.billing_status)
    if f.billing_cycle:
        stmt = stmt.where(Trip.billing_cycle == f.billing_cycle)
    if f.driver_id:
        stmt = stmt.where(Trip.driver_id == f.driver_id)
    if f.date_from:
        stmt = stmt.where(Trip.delivery_date >= f.date_from)
    if f.date_to:
        stmt = stmt.where(Trip.delivery_date <= f.date_to)
    if f.pod_status:
        expr = latest_pod_status_expr()
        stmt = stmt.where(expr.is_(None)) if f.pod_status == "PENDING" else stmt.where(expr == f.pod_status)
    return stmt


def query_trips(db: Session, f: TripFilters, page: int, page_size: int, order=None):
    base = apply_filters(select(Trip.id), f)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    stmt = apply_filters(select(Trip), f).order_by(*(order or (Trip.delivery_date.desc().nullslast(), Trip.trip_reference)))
    items = list(db.scalars(stmt.limit(page_size).offset((page - 1) * page_size)).unique())
    return items, total
