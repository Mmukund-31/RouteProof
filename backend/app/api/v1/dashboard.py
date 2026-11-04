import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_billing
from app.core.db import get_db
from app.models import AuditLog, User, aware
from app.schemas.serializers import page
from app.services import dashboard as svc

router = APIRouter(tags=["dashboard"])


class _F:
    def __init__(self, date_from: date | None = None, date_to: date | None = None, client_id: uuid.UUID | None = None,
                 branch: str | None = None):
        self.args = (date_from, date_to, client_id, branch)


@router.get("/dashboard/metrics")
def metrics(f: _F = Depends(), user: User = Depends(require_billing), db: Session = Depends(get_db)):
    return svc.metrics(db, *f.args)


@router.get("/dashboard/pod-aging")
def aging(f: _F = Depends(), user: User = Depends(require_billing), db: Session = Depends(get_db)):
    return {"items": svc.pod_aging(db, *f.args)}


@router.get("/dashboard/client-breakdown")
def clients(f: _F = Depends(), user: User = Depends(require_billing), db: Session = Depends(get_db)):
    return {"items": svc.client_breakdown(db, *f.args)}


@router.get("/dashboard/missing-pods")
def missing(f: _F = Depends(), user: User = Depends(require_billing), db: Session = Depends(get_db)):
    return svc.missing_pods(db, *f.args)


@router.get("/dashboard/recent-activity")
def recent(user: User = Depends(require_billing), db: Session = Depends(get_db)):
    return {"items": svc.recent_activity(db)}


@router.get("/audit-logs")
def audit_logs(entity_type: str | None = None, entity_id: str | None = None, action: str | None = None,
               page_no: int = Query(1, alias="page", ge=1), page_size: int = Query(50, ge=1, le=200),
               user: User = Depends(require_billing), db: Session = Depends(get_db)):
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"%{action}%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditLog.timestamp.desc()).limit(page_size).offset((page_no - 1) * page_size)).unique()
    return page([{"id": str(r.id), "user": r.user.name if r.user else None, "entity_type": r.entity_type, "entity_id": r.entity_id,
                  "action": r.action, "previous_values": r.previous_values, "new_values": r.new_values, "metadata": r.meta,
                  "timestamp": aware(r.timestamp).isoformat()} for r in rows], total, page_no, page_size)
