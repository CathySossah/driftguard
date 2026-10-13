from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import require_admin

router = APIRouter(prefix="/audit-logs", tags=["Audit"])


@router.get("/", response_model=list[schemas.AuditLogOut])
def list_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    """Historique chronologique des actions (page 'Journal d'audit', admin uniquement)."""
    logs = (
        db.query(models.AuditLog)
        .order_by(models.AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        schemas.AuditLogOut(
            id=log.id,
            created_at=log.created_at,
            user_id=log.user_id,
            user_name=log.user.full_name if log.user else ("Système" if log.user_id is None else None),
            action=log.action,
            target=log.target,
            details=log.details,
        )
        for log in logs
    ]
