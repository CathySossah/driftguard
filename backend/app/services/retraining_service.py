"""
Orchestration d'un job de ré-entraînement : appelle le service d'entraînement,
puis met à jour le RetrainingJob et publie une nouvelle ModelVersion en cas de
succès. Conçu pour être exécuté en tâche de fond (FastAPI BackgroundTasks) afin
que l'API réponde immédiatement à l'administrateur sans attendre la fin de
l'entraînement — une alternative légère à une file de tâches (Celery/RQ) pour
un déploiement de cette taille ; à migrer vers Celery si la charge augmente.
"""
import logging
from datetime import datetime

from app.database import SessionLocal
from app import models
from app.services.training_service import train_and_log_model
from app.services import scenario_state

logger = logging.getLogger("driftguard.retraining")


def execute_initial_training_job(job_id: str, dataset_id: str) -> None:
    """
    Comme execute_retraining_job, mais pour le tout premier modèle d'un
    dataset fraîchement importé (pas d'alerte à l'origine, donc pas de
    version précédente à archiver). Déclenché par
    POST /models/train-initial/{dataset_id}.
    """
    db = SessionLocal()
    try:
        job = db.query(models.RetrainingJob).filter(models.RetrainingJob.id == job_id).first()
        dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
        if job is None or dataset is None:
            logger.error("Job %s ou dataset %s introuvable", job_id, dataset_id)
            return

        result = train_and_log_model(dataset=dataset, drift_level=0.0)
        job.finished_at = datetime.utcnow()

        if result["success"]:
            if not dataset.target_column and result.get("target_column"):
                dataset.target_column = result["target_column"]  # colonne choisie automatiquement
            new_version = models.ModelVersion(
                dataset_id=dataset.id,
                mlflow_run_id=result["mlflow_run_id"],
                version_number=1,
                status=models.ModelStatusEnum.en_production,
                metrics=result["metrics"],
                deployed_at=datetime.utcnow(),
            )
            db.add(new_version)
            db.commit()
            db.refresh(new_version)

            job.status = models.JobStatusEnum.reussi
            job.new_model_version_id = new_version.id
            db.commit()
            logger.info("Premier modèle entraîné pour le dataset %s (run MLflow %s)", dataset.id, result["mlflow_run_id"])
        else:
            job.status = models.JobStatusEnum.echoue
            job.error_message = result["error_message"]
            db.commit()
            logger.warning("Échec de l'entraînement initial pour le dataset %s : %s", dataset.id, result["error_message"])
    finally:
        db.close()


def execute_retraining_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(models.RetrainingJob).filter(models.RetrainingJob.id == job_id).first()
        if job is None:
            logger.error("RetrainingJob %s introuvable", job_id)
            return

        # Retrouve le modèle et le dataset concernés via l'alerte d'origine
        # (s'il s'agit d'un job relancé manuellement sans alerte, on ne peut
        # pas déduire le modèle : à adapter selon vos règles de gestion).
        model_version_id = None
        if job.alert_id:
            alert = db.query(models.Alert).filter(models.Alert.id == job.alert_id).first()
            if alert:
                run = db.query(models.MonitoringRun).filter(
                    models.MonitoringRun.id == alert.monitoring_run_id
                ).first()
                if run:
                    model_version_id = run.model_version_id

        if model_version_id is None:
            job.status = models.JobStatusEnum.echoue
            job.error_message = "Impossible de déterminer le modèle à ré-entraîner (alerte associée introuvable)."
            job.finished_at = datetime.utcnow()
            db.commit()
            return

        old_version = db.query(models.ModelVersion).filter(models.ModelVersion.id == model_version_id).first()
        if old_version is None:
            job.status = models.JobStatusEnum.echoue
            job.error_message = "La version de modèle à ré-entraîner n'existe plus."
            job.finished_at = datetime.utcnow()
            db.commit()
            return
        dataset = db.query(models.Dataset).filter(models.Dataset.id == old_version.dataset_id).first()
        drift_level = scenario_state.get_drift_level(model_version_id)

        result = train_and_log_model(dataset=dataset, drift_level=drift_level)

        job.finished_at = datetime.utcnow()

        if result["success"]:
            new_version = models.ModelVersion(
                dataset_id=old_version.dataset_id,
                mlflow_run_id=result["mlflow_run_id"],
                version_number=old_version.version_number + 1,
                status=models.ModelStatusEnum.en_production,
                metrics=result["metrics"],
                deployed_at=datetime.utcnow(),
            )
            db.add(new_version)
            old_version.status = models.ModelStatusEnum.archive
            db.commit()
            db.refresh(new_version)

            job.status = models.JobStatusEnum.reussi
            job.new_model_version_id = new_version.id
            db.commit()

            # Le modèle vient de changer : on repart d'un niveau de dérive à
            # zéro pour la nouvelle version (elle vient d'être ré-entraînée
            # sur les données les plus récentes).
            scenario_state.reset_drift_level(new_version.id)

            logger.info(
                "Ré-entraînement réussi : v%s -> v%s (run MLflow %s)",
                old_version.version_number, new_version.version_number, result["mlflow_run_id"],
            )
        else:
            job.status = models.JobStatusEnum.echoue
            job.error_message = result["error_message"]
            db.commit()
            logger.warning("Échec du ré-entraînement pour le modèle %s : %s", model_version_id, result["error_message"])

    finally:
        db.close()
