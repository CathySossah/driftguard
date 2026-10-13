from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import get_current_user, require_admin
from app.services.retraining_service import execute_retraining_job
from app.services.audit_service import log_action

router = APIRouter(prefix="/alerts", tags=["Alertes"])


@router.get("/", response_model=list[schemas.AlertOut])
def list_alerts(
    status_filter: models.AlertStatusEnum | None = None,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    """Page 'Gestion des alertes'."""
    query = db.query(models.Alert)
    if status_filter:
        query = query.filter(models.Alert.status == status_filter)
    return query.order_by(models.Alert.triggered_at.desc()).all()


@router.patch("/{alert_id}/review", response_model=schemas.AlertOut)
def review_alert(
    alert_id: str,
    payload: schemas.AlertReview,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """
    Validation humaine d'une alerte (boutons 'Valider' / 'Rejeter' de la maquette).
    C'est ICI, et uniquement ici, que peut être déclenché un ré-entraînement :
    la validation d'une alerte crée un RetrainingJob, exécuté en tâche de fond
    (entraînement réel + journalisation MLflow, cf. training_service.py) afin
    que l'API réponde immédiatement sans bloquer sur la durée de l'entraînement.
    """
    alert = db.query(models.Alert).filter(models.Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte introuvable")
    if alert.status != models.AlertStatusEnum.en_attente:
        raise HTTPException(status_code=400, detail="Cette alerte a déjà été traitée")

    alert.reviewed_by = admin.id
    alert.reviewed_at = datetime.utcnow()
    alert.comment = payload.comment

    if payload.approve:
        alert.status = models.AlertStatusEnum.validee
        job = models.RetrainingJob(
            alert_id=alert.id,
            triggered_by=admin.id,
            status=models.JobStatusEnum.en_cours,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        log_action(db, action="alert.validated", user_id=admin.id, target=f"Alerte {alert.id[:8]} — sévérité {alert.severity.value}")
        background_tasks.add_task(execute_retraining_job, job.id)
    else:
        alert.status = models.AlertStatusEnum.rejetee
        db.commit()
        log_action(db, action="alert.rejected", user_id=admin.id, target=f"Alerte {alert.id[:8]} — sévérité {alert.severity.value}")

    db.refresh(alert)
    return alert
