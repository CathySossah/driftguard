"""Utilitaire pour enregistrer une entrée dans le journal d'audit."""
from typing import Optional, Any

from sqlalchemy.orm import Session

from app import models


def log_action(
    db: Session,
    action: str,
    user_id: Optional[str] = None,
    target: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    """
    Enregistre une action dans le journal d'audit. Ne lève jamais d'exception
    vers l'appelant : une erreur de journalisation ne doit jamais faire
    échouer l'action métier elle-même (principe de robustesse — le journal
    est un observateur, pas un acteur critique du flux).
    """
    try:
        entry = models.AuditLog(user_id=user_id, action=action, target=target, details=details)
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()
