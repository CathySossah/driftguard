from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import get_current_user, require_admin
from app.services.retraining_service import execute_retraining_job, execute_initial_training_job
from app.services.audit_service import log_action

router = APIRouter(prefix="/retraining-jobs", tags=["Ré-entraînement"])


@router.get("/", response_model=list[schemas.RetrainingJobOut])
def list_retraining_jobs(
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    """Page Modèles > 'Historique des ré-entraînements'."""
    return db.query(models.RetrainingJob).order_by(models.RetrainingJob.started_at.desc()).all()


@router.patch("/{job_id}/complete", response_model=schemas.RetrainingJobOut)
def complete_job(
    job_id: str,
    success: bool,
    new_model_version_id: str | None = None,
    error_message: str | None = None,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    """
    Appelé par le pipeline de ré-entraînement à la fin de son exécution
    (succès -> nouvelle ModelVersion, échec -> message d'erreur affiché
    dans la maquette avec option 'Relancer manuellement').
    """
    job = db.query(models.RetrainingJob).filter(models.RetrainingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job de ré-entraînement introuvable")

    job.finished_at = datetime.utcnow()
    if success:
        job.status = models.JobStatusEnum.reussi
        job.new_model_version_id = new_model_version_id
    else:
        job.status = models.JobStatusEnum.echoue
        job.error_message = error_message

    db.commit()
    db.refresh(job)
    return job


@router.post("/{job_id}/retry", response_model=schemas.RetrainingJobOut, status_code=201)
def retry_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """
    Bouton 'Relancer manuellement' après un échec de ré-entraînement.

    Un job échoué peut avoir deux origines différentes, qui doivent être
    relancées via des chemins différents :
    - né d'une alerte validée (alert_id renseigné) -> execute_retraining_job,
      qui retrouve le modèle concerné via l'alerte ;
    - né d'un entraînement initial sur un dataset fraîchement importé
      (dataset_id renseigné, pas d'alerte) -> execute_initial_training_job.
    Avant cette distinction, relancer un entraînement initial échoué tombait
    par erreur sur execute_retraining_job, qui ne trouvait aucune alerte et
    échouait avec un message trompeur ('alerte associée introuvable').
    """
    original = db.query(models.RetrainingJob).filter(models.RetrainingJob.id == job_id).first()
    if not original:
        raise HTTPException(status_code=404, detail="Job introuvable")
    if original.status != models.JobStatusEnum.echoue:
        raise HTTPException(status_code=400, detail="Seul un job en échec peut être relancé")
    if not original.alert_id and not original.dataset_id:
        raise HTTPException(
            status_code=400,
            detail="Ce job n'a ni alerte ni dataset associé — impossible de déterminer quoi relancer.",
        )

    new_job = models.RetrainingJob(
        alert_id=original.alert_id,
        dataset_id=original.dataset_id,
        triggered_by=admin.id,
        status=models.JobStatusEnum.en_cours,
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    log_action(db, action="retraining.retried", user_id=admin.id, target=f"Job {job_id[:8]} relancé sous {new_job.id[:8]}")

    if original.alert_id:
        background_tasks.add_task(execute_retraining_job, new_job.id)
    else:
        background_tasks.add_task(execute_initial_training_job, new_job.id, original.dataset_id)

    return new_job
