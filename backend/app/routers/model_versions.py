from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import get_current_user, require_admin
from app.services.retraining_service import execute_initial_training_job
from app.services.audit_service import log_action

router = APIRouter(prefix="/models", tags=["Modèles"])


@router.post("/train-initial/{dataset_id}", response_model=schemas.RetrainingJobOut, status_code=202)
def train_initial_model(
    dataset_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """
    Entraîne le tout premier modèle sur un dataset importé (aucune version
    n'existe encore pour ce dataset). Utilise le VRAI fichier CSV importé.
    La colonne cible est facultative : si elle n'est pas configurée
    (PATCH /datasets/{id}/configure), elle est choisie automatiquement.
    Exécuté en tâche de fond, comme le ré-entraînement classique.
    """
    dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset introuvable")
    if not dataset.source_path:
        raise HTTPException(status_code=400, detail="Ce dataset n'a pas de fichier importé.")

    existing = db.query(models.ModelVersion).filter(models.ModelVersion.dataset_id == dataset_id).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Un modèle existe déjà pour ce dataset — utilise le ré-entraînement (via une alerte) plutôt que l'entraînement initial.",
        )

    job = models.RetrainingJob(
        alert_id=None,
        dataset_id=dataset_id,
        triggered_by=admin.id,
        status=models.JobStatusEnum.en_cours,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    log_action(db, action="model.initial_training", user_id=admin.id, target=f"Dataset {dataset.name}")
    background_tasks.add_task(execute_initial_training_job, job.id, dataset_id)
    return job


@router.get("/", response_model=list[schemas.ModelVersionOut])
def list_model_versions(
    dataset_id: str | None = None,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    """Page 'Gestion des modèles' : liste des versions, filtrable par dataset/domaine."""
    query = db.query(models.ModelVersion)
    if dataset_id:
        query = query.filter(models.ModelVersion.dataset_id == dataset_id)
    return query.order_by(models.ModelVersion.version_number.desc()).all()


@router.get("/compare", response_model=list[schemas.ModelVersionOut])
def compare_versions(
    version_a_id: str,
    version_b_id: str,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    """Page 'Comparer les modèles' : renvoie les deux versions choisies côte à côte."""
    versions = (
        db.query(models.ModelVersion)
        .filter(models.ModelVersion.id.in_([version_a_id, version_b_id]))
        .all()
    )
    if len(versions) != 2:
        raise HTTPException(status_code=404, detail="Une ou plusieurs versions introuvables")
    return versions


@router.patch("/{version_id}/deploy", response_model=schemas.ModelVersionOut)
def deploy_version(
    version_id: str,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    """Déployer manuellement une version : passe son statut à 'en_production'
    et archive l'ancienne version en production du même dataset."""
    version = db.query(models.ModelVersion).filter(models.ModelVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version introuvable")

    # Archive l'ancienne version en production pour le même dataset
    db.query(models.ModelVersion).filter(
        models.ModelVersion.dataset_id == version.dataset_id,
        models.ModelVersion.status == models.ModelStatusEnum.en_production,
    ).update({"status": models.ModelStatusEnum.archive})

    version.status = models.ModelStatusEnum.en_production
    db.commit()
    db.refresh(version)
    log_action(db, action="model.deployed", user_id=_admin.id, target=f"Version v{version.version_number}")
    return version
