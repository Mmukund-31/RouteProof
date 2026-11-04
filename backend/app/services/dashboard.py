"""Dashboard aggregations computed from database records on every request (no cached or hardcoded values)."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuditLog, Client, Trip, aware

BUCKETS = [("0-2 days", 0, 2), ("3-7 days", 3, 7), ("8-14 days", 8, 14), ("15-30 days", 15, 30), ("30+ days", 31, 10_000)]


def _trips(db: Session, date_from, date_to, client_id, branch) -> list[Trip]:
    q = select(Trip)
    if date_from:
        q = q.where(Trip.delivery_date >= date_from)
    if date_to:
        q = q.where(Trip.delivery_date <= date_to)
    if client_id:
        q = q.where(Trip.client_id == client_id)
    if branch:
        q = q.where(Trip.branch == branch)
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


def metrics(db: Session, date_from=None, date_to=None, client_id=None, branch=None) -> dict:
    trips = _trips(db, date_from, date_to, client_id, branch)
    last = {t.id: _last(t) for t in trips}
    delivered = [t for t in trips if _is_delivered(t)]
    to_upload_h, to_ready_h, within24 = [], [], 0
    for t in delivered:
        if not t.pods or not t.delivery_date:
            continue
        first = aware(t.pods[0].server_received_at)
        due = datetime.combine(t.delivery_date, time.min, tzinfo=timezone.utc)
        h = (first - due).total_seconds() / 3600
        to_upload_h.append(max(h, 0))
        if h <= 48:  # delivery day plus 24h grace, measured from start of the delivery date
            within24 += 1
        v = next((p for p in reversed(t.pods) if p.verified_at), None)
        if v:
            to_ready_h.append(max((aware(v.verified_at) - aware(v.server_received_at)).total_seconds() / 3600, 0))
    with_pod = sum(1 for t in delivered if t.pods)
    ai_v = sum(1 for p in last.values() if p and p.verification_status == "VERIFIED" and p.verification_method == "ai")
    hu_v = sum(1 for p in last.values() if p and p.verification_status == "VERIFIED" and p.verification_method == "human")
    return {
        "data_source": get_settings().data_mode,
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
        "avg_delivery_to_upload_hours": _avg(to_upload_h),
        "avg_upload_to_billing_ready_hours": _avg(to_ready_h),
        "pods_within_24h_pct": round(100 * within24 / with_pod, 1) if with_pod else None,
        "clients": client_breakdown(db, date_from, date_to, client_id, branch),
        "branches": branch_breakdown(db, date_from, date_to, client_id, branch),
        "aging": pod_aging(db, date_from, date_to, client_id, branch),
    }


def pod_aging(db: Session, date_from=None, date_to=None, client_id=None, branch=None) -> list[dict]:
    today = date.today()
    out = [{"bucket": b, "count": 0, "freight": 0.0} for b, _, _ in BUCKETS]
    for t in _trips(db, date_from, date_to, client_id, branch):
        if _missing(t) and t.delivery_date:
            age = (today - t.delivery_date).days
            for i, (_, lo, hi) in enumerate(BUCKETS):
                if lo <= age <= hi:
                    out[i]["count"] += 1
                    out[i]["freight"] += float(t.freight_amount)
                    break
    return out


def _group(db, key_fn, label_fn, date_from, date_to, client_id, branch) -> list[dict]:
    g: dict = defaultdict(lambda: {"trips": 0, "pending_pod": 0, "needs_review": 0, "billing_ready": 0, "exported": 0, "freight_awaiting_pod": 0.0})
    for t in _trips(db, date_from, date_to, client_id, branch):
        row = g[key_fn(t)]
        row["label"] = label_fn(t)
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


def client_breakdown(db: Session, date_from=None, date_to=None, client_id=None, branch=None) -> list[dict]:
    rows = _group(db, lambda t: t.client_id, lambda t: t.client.company_name, date_from, date_to, client_id, branch)
    for r in rows:
        r["client"] = r.pop("label")
    return rows


def branch_breakdown(db: Session, date_from=None, date_to=None, client_id=None, branch=None) -> list[dict]:
    rows = _group(db, lambda t: t.branch or "Unassigned", lambda t: t.branch or "Unassigned", date_from, date_to, client_id, branch)
    for r in rows:
        r["branch"] = r.pop("label")
    return rows


def missing_pods(db: Session, date_from=None, date_to=None, client_id=None, branch=None) -> dict:
    s = get_settings()
    today = date.today()
    items = []
    for t in _trips(db, date_from, date_to, client_id, branch):
        if _missing(t) and t.delivery_date:
            days = (today - t.delivery_date).days
            p = _last(t)
            items.append({
                "trip_id": str(t.id), "trip_reference": t.trip_reference, "lr_number": t.lr_number, "client": t.client.company_name,
                "driver": t.driver.name if t.driver else None, "vehicle": t.vehicle.registration_number,
                "ownership": t.vehicle.ownership_type, "destination": t.destination, "branch": t.branch,
                "delivery_date": t.delivery_date.isoformat(), "days_since_delivery": days,
                "overdue": days > s.delivery_overdue_days, "freight_amount": float(t.freight_amount),
                "pod_state": p.verification_status if p else "PENDING",
            })
    items.sort(key=lambda i: -i["days_since_delivery"])
    reviews = [t for t in _trips(db, date_from, date_to, client_id, branch) if _last(t) and _last(t).verification_status == "NEEDS_REVIEW"]
    return {
        "overdue_after_days": s.delivery_overdue_days,
        "items": items,
        "overdue_count": sum(1 for i in items if i["overdue"]),
        "freight_blocked": sum(i["freight_amount"] for i in items),
        "pending_reviews": len(reviews),
    }


def recent_activity(db: Session, limit: int = 10) -> list[dict]:
    rows = db.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)).unique()
    return [{"id": str(r.id), "action": r.action, "entity_type": r.entity_type, "entity_id": r.entity_id,
             "user": r.user.name if r.user else "System / link", "timestamp": aware(r.timestamp).isoformat()} for r in rows]
