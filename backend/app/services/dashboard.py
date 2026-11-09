"""Dashboard aggregations computed from database records on every request (no cached or hardcoded values).

Every view takes the same DashFilters, so the KPIs, charts and the missing-POD table always describe the same set of
trips. Turnaround metrics are measured from the *delivery date* (local business day start), never from upload time,
and an export is never presented as an invoice.
"""
import statistics
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuditLog, Trip, aware

METRIC_DEFINITIONS = {
    "delivery_to_pod_received": "Start of the delivery date (business time zone) -> server receipt of the first POD upload",
    "delivery_to_pod_verified": "Start of the delivery date -> first successful verification of a POD (AI checks or human review)",
    "delivery_to_billing_export": "Start of the delivery date -> first time the trip was included in a billing CSV export",
    "delivery_to_invoice_recorded": "Delivery date -> invoice date entered by a billing executive (calendar days). "
                                    "Only trips with a recorded invoice count; an export is never treated as an invoice.",
    "delivery_date": "TMS/CSV import, or the date on a verified POD; never the upload date",
    "sample": "count = trips contributing to the average; period = earliest..latest delivery date among them",
}

BUCKETS = [("0-2 days", 0, 2), ("3-7 days", 3, 7), ("8-14 days", 8, 14), ("15-30 days", 15, 30), ("30+ days", 31, 10_000)]


@dataclass
class DashFilters:
    date_from: date | None = None
    date_to: date | None = None
    client_id: uuid.UUID | None = None
    branch: str | None = None
    billing_cycle: str | None = None

    def echo(self) -> dict:
        return {k: (str(v) if v is not None else None) for k, v in asdict(self).items()}


def _tz():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(get_settings().business_timezone)
    except Exception:  # no tz database on this host: India has no DST, so a fixed offset is exact
        return timezone(timedelta(hours=5, minutes=30))


def _trips(db: Session, f: DashFilters) -> list[Trip]:
    q = select(Trip)
    if f.date_from:
        q = q.where(Trip.delivery_date >= f.date_from)
    if f.date_to:
        q = q.where(Trip.delivery_date <= f.date_to)
    if f.client_id:
        q = q.where(Trip.client_id == f.client_id)
    if f.branch:
        q = q.where(Trip.branch == f.branch)
    if f.billing_cycle:
        q = q.where(Trip.billing_cycle == f.billing_cycle)
    return list(db.scalars(q).unique())


def _last(t: Trip):
    return t.pods[-1] if t.pods else None


def _is_delivered(t: Trip) -> bool:
    return t.trip_status not in ("IN_TRANSIT", "CANCELLED")


def _missing(t: Trip) -> bool:
    """Delivered with no POD uploaded at all, or the last attempt was retake-requested/rejected (nothing usable on file)."""
    if not _is_delivered(t):
        return False
    p = _last(t)
    return p is None or p.verification_status in ("RETAKE_REQUESTED", "REJECTED")


def _avg(xs):
    return round(sum(xs) / len(xs), 1) if xs else None


def _stat(samples: list[tuple[float, date]]) -> dict:
    """Average / median in days plus the sample behind it, so a figure from three seeded trips is visibly that."""
    if not samples:
        return {"avg_days": None, "median_days": None, "count": 0, "period": None}
    vals = [v for v, _ in samples]
    days = [d for _, d in samples]
    return {"avg_days": round(sum(vals) / len(vals), 1), "median_days": round(statistics.median(vals), 1), "count": len(vals),
            "period": {"from": min(days).isoformat(), "to": max(days).isoformat()}}


def turnaround(trips: list[Trip]) -> dict:
    tz = _tz()
    rec, ver, exp, inv = [], [], [], []
    for t in trips:
        if not _is_delivered(t) or not t.delivery_date:
            continue
        start = datetime.combine(t.delivery_date, time.min, tzinfo=tz)

        def days_to(ts, start=start):
            return max((aware(ts) - start).total_seconds() / 86400, 0.0)

        if t.pods:
            rec.append((days_to(t.pods[0].server_received_at), t.delivery_date))
            verified = [p.verified_at for p in t.pods if p.verified_at]
            if verified:
                ver.append((days_to(min(aware(v) for v in verified)), t.delivery_date))
        if t.exported_at:
            exp.append((days_to(t.exported_at), t.delivery_date))
        if t.invoice_date:
            inv.append((float(max((t.invoice_date - t.delivery_date).days, 0)), t.delivery_date))
    return {"delivery_to_pod_received": _stat(rec), "delivery_to_pod_verified": _stat(ver),
            "delivery_to_billing_export": _stat(exp), "delivery_to_invoice_recorded": _stat(inv)}


def metrics(db: Session, f: DashFilters | None = None) -> dict:
    f = f or DashFilters()
    trips = _trips(db, f)
    last = {t.id: _last(t) for t in trips}
    delivered = [t for t in trips if _is_delivered(t)]
    # Legacy hour-based figures (kept for API compatibility), on the same server-side clocks as `turnaround`.
    to_upload_h, to_ready_h, ready_to_export_h, within24 = [], [], [], 0
    tz = _tz()
    for t in delivered:
        if not t.pods or not t.delivery_date:
            continue
        first = aware(t.pods[0].server_received_at)
        due = datetime.combine(t.delivery_date, time.min, tzinfo=tz)
        h = (first - due).total_seconds() / 3600
        to_upload_h.append(max(h, 0))
        if h <= 48:  # delivery day plus 24h grace, measured from start of the delivery date
            within24 += 1
        ready = aware(t.billing_ready_at)
        if ready is None:  # rows created before billing_ready_at existed: fall back to the verification time
            v = next((p for p in reversed(t.pods) if p.verified_at), None)
            ready = aware(v.verified_at) if v and t.billing_status != "NOT_READY" else None
        if ready:
            to_ready_h.append(max((ready - first).total_seconds() / 3600, 0))
            if t.exported_at:
                ready_to_export_h.append(max((aware(t.exported_at) - ready).total_seconds() / 3600, 0))
    with_pod = sum(1 for t in delivered if t.pods)
    ai_v = sum(1 for p in last.values() if p and p.verification_status == "VERIFIED" and p.verification_method == "ai")
    hu_v = sum(1 for p in last.values() if p and p.verification_status == "VERIFIED" and p.verification_method == "human")
    return {
        "data_source": get_settings().data_mode,
        "filters": f.echo(),
        "total_trips": len(trips),
        "in_transit": sum(1 for t in trips if t.trip_status == "IN_TRANSIT"),
        "delivered": len(delivered),
        "pods_pending": sum(1 for t in delivered if _last(t) is None),
        "pods_uploaded": with_pod,
        "ai_verified": ai_v,
        "human_verified": hu_v,
        "needs_review": sum(1 for p in last.values() if p and p.verification_status == "NEEDS_REVIEW"),
        "retake_requests": sum(1 for p in last.values() if p and p.verification_status == "RETAKE_REQUESTED"),
        "billing_ready": sum(1 for t in trips if t.billing_status == "BILLING_READY"),
        "exported": sum(1 for t in trips if t.billing_status == "EXPORTED"),
        "invoiced": sum(1 for t in trips if t.billing_status == "INVOICED"),
        "trips_without_pod": sum(1 for t in delivered if _missing(t)),
        "turnaround": turnaround(trips),
        "avg_delivery_to_upload_hours": _avg(to_upload_h),
        "avg_upload_to_billing_ready_hours": _avg(to_ready_h),
        "avg_billing_ready_to_export_hours": _avg(ready_to_export_h),
        "pods_within_24h_pct": round(100 * within24 / with_pod, 1) if with_pod else None,
        "approved_with_exception": sum(1 for p in last.values() if p and p.verification_status == "VERIFIED" and p.approved_exceptions),
        "metric_definitions": METRIC_DEFINITIONS,
        "clients": _group(trips, lambda t: t.client_id, lambda t: t.client.company_name, "client"),
        "branches": _group(trips, lambda t: t.branch or "Unassigned", lambda t: t.branch or "Unassigned", "branch"),
        "aging": _aging(trips),
    }


def _aging(trips: list[Trip]) -> list[dict]:
    today = date.today()
    out = [{"bucket": b, "count": 0, "freight": 0.0} for b, _, _ in BUCKETS]
    for t in trips:
        if _missing(t) and t.delivery_date:
            age = (today - t.delivery_date).days
            for i, (_, lo, hi) in enumerate(BUCKETS):
                if lo <= age <= hi:
                    out[i]["count"] += 1
                    out[i]["freight"] += float(t.freight_amount)
                    break
    return out


def _group(trips: list[Trip], key_fn, label_fn, label_key: str) -> list[dict]:
    g: dict = defaultdict(lambda: {"trips": 0, "pending_pod": 0, "needs_review": 0, "billing_ready": 0, "exported": 0, "freight_awaiting_pod": 0.0})
    for t in trips:
        row = g[key_fn(t)]
        row[label_key] = label_fn(t)
        row["trips"] += 1
        p = _last(t)
        if _missing(t):
            row["pending_pod"] += 1
            row["freight_awaiting_pod"] += float(t.freight_amount)
        if p and p.verification_status == "NEEDS_REVIEW":
            row["needs_review"] += 1
        row["billing_ready"] += t.billing_status == "BILLING_READY"
        row["exported"] += t.billing_status == "EXPORTED"
    return sorted(g.values(), key=lambda r: -r["pending_pod"])


def pod_aging(db: Session, f: DashFilters | None = None) -> list[dict]:
    return _aging(_trips(db, f or DashFilters()))


def client_breakdown(db: Session, f: DashFilters | None = None) -> list[dict]:
    return _group(_trips(db, f or DashFilters()), lambda t: t.client_id, lambda t: t.client.company_name, "client")


def branch_breakdown(db: Session, f: DashFilters | None = None) -> list[dict]:
    return _group(_trips(db, f or DashFilters()), lambda t: t.branch or "Unassigned", lambda t: t.branch or "Unassigned", "branch")


def missing_pods(db: Session, f: DashFilters | None = None, min_days: int | None = None) -> dict:
    """Trips whose freight is blocked for lack of a usable POD. Totals are computed from exactly the rows returned."""
    f = f or DashFilters()
    s = get_settings()
    today = date.today()
    trips = _trips(db, f)
    items = []
    for t in trips:
        if not (_missing(t) and t.delivery_date):
            continue
        days = (today - t.delivery_date).days
        if min_days is not None and days < min_days:
            continue
        p = _last(t)
        items.append({
            "trip_id": str(t.id), "trip_reference": t.trip_reference, "lr_number": t.lr_number,
            "client": t.client.company_name, "client_id": str(t.client_id), "billing_cycle": t.billing_cycle,
            # Phone only where calling the driver is the suggested action (company drivers); hired trips get a link.
            "driver": t.driver.name if t.driver else None,
            "driver_phone": t.driver.phone if t.driver and t.vehicle.ownership_type != "hired" else None,
            "vehicle": t.vehicle.registration_number, "ownership": t.vehicle.ownership_type, "destination": t.destination,
            "branch": t.branch, "delivery_date": t.delivery_date.isoformat(), "days_since_delivery": days,
            "overdue": days > s.delivery_overdue_days, "freight_amount": float(t.freight_amount),
            "pod_state": p.verification_status if p else "PENDING",
            "suggested_action": "send_upload_link" if t.vehicle.ownership_type == "hired" else "call_driver",
        })
    items.sort(key=lambda i: -i["days_since_delivery"])
    return {
        "filters": {**f.echo(), "min_days": min_days},
        "overdue_after_days": s.delivery_overdue_days,
        "items": items,
        "overdue_count": sum(1 for i in items if i["overdue"]),
        "freight_blocked": sum(i["freight_amount"] for i in items),
        "pending_reviews": sum(1 for t in trips if _last(t) and _last(t).verification_status == "NEEDS_REVIEW"),
    }


def recent_activity(db: Session, limit: int = 10) -> list[dict]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)).unique()
    return [{"id": str(r.id), "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id,
             "user": r.user.name if r.user else "System / link", "timestamp": aware(r.timestamp).isoformat()} for r in rows]
