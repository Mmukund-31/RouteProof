import uuid

from sqlalchemy.orm import Session

from app.models import AuditLog


def audit(db: Session, user_id, entity_type: str, entity_id, action: str, previous=None, new=None, meta=None) -> AuditLog:
    """Append an audit row in the caller's transaction so state change and audit commit atomically."""
    row = AuditLog(
        user_id=user_id if isinstance(user_id, (uuid.UUID, type(None))) else uuid.UUID(str(user_id)),
        entity_type=entity_type, entity_id=str(entity_id), action=action,
        previous_values=previous, new_values=new, meta=meta,
    )
    db.add(row)
    return row
