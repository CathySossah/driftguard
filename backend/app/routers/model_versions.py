from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import get_current_user, require_admin
from app.services.retraining_service import execute_initial_training_job
from app.services.ml_features import ALGORITHMS, BALANCING_METHODS, normalize_training_options
from app.services.audit_service import log_action

router = APIRouter(prefix="/models", tags=["Modèles"])


@router.post("/train-initial/{dataset_id}", response_model=schemas.RetrainingJobOut, status_code=202)
def train_initial_model(
    dataset_id: str,
    background_tasks: BackgroundTasks,
    payload: Optional[schemas.TrainRequest] = None,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """
    Entraîne un modèle sur un dataset importé, avec les algorithmes et la méthode
    d'équilibrage choisis (par défaut : Random Forest + pondération des classes).
    Tous les algorithmes choisis sont comparés ; le meilleur (F1) est publié.
    Un nouvel entraînement sur un dataset qui a déjà un modèle crée une nouvelle
    version (la précédente est archivée). Utilise le VRAI fichier CSV importé.
    La colonne cible est facultative : si elle n'est pas configurée
    (PATCH /datasets/{id}/configure), elle est choisie automatiquement.
    Exécuté en tâche de fond, comme le ré-entraînement classique.
    """
    dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset introuvable")
    if not dataset.source_path:
        raise HTTPException(status_code=400, detail="Ce dataset n'a pas de fichier importé.")

    requested = payload or schemas.TrainRequest()
    unknown = [a for a in requested.algorithms if a not in ALGORITHMS]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Algorithme(s) inconnu(s) : {', '.join(unknown)}")
    if requested.balancing not in BALANCING_METHODS:
        raise HTTPException(status_code=422, detail=f"Méthode d'équilibrage inconnue : {requested.balancing}")
    algorithms, balancing = normalize_training_options(requested.algorithms, requested.balancing)
    if requested.target_status not in (None, "staging", "en_production"):
        raise HTTPException(status_code=422, detail="Le statut cible doit être « staging » ou « en_production ».")

    job = models.RetrainingJob(
        alert_id=None,
        dataset_id=dataset_id,
        triggered_by=admin.id,
        status=models.JobStatusEnum.en_cours,
        progress=0,
        progress_label="En attente de démarrage",
        training_results={"config": {
            "algorithms": algorithms, "balancing": balancing, "target_status": requested.target_status,
        }},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    log_action(db, action="model.initial_training", user_id=admin.id, target=f"Dataset {dataset.name}")
    background_tasks.add_task(execute_initial_training_job, job.id, dataset_id)
    return job


@router.get("/training-options")
def training_options(_current_user: models.User = Depends(get_current_user)):
    """Algorithmes et méthodes d'équilibrage proposés dans l'onglet Datasets."""
    return {
        "algorithms": [{"key": k, "label": v} for k, v in ALGORITHMS.items()],
        "balancing": [{"key": k, "label": v} for k, v in BALANCING_METHODS.items()],
    }


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


@router.patch("/{version_id}/status", response_model=schemas.ModelVersionOut)
def change_version_status(
    version_id: str,
    payload: schemas.ModelStatusUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """
    Fait évoluer une version dans son cycle de vie (en_test, staging, en_production, archive).
    Mettre une version en production archive automatiquement celle qui l'était pour le même dataset :
    il n'y a jamais deux modèles en production pour un même dataset.
    """
    version = db.query(models.ModelVersion).filter(models.ModelVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version introuvable")
    new_status = payload.status
    old_status = version.status
    if old_status == new_status:
        raise HTTPException(status_code=400, detail="Cette version a déjà ce statut.")

    if new_status == models.ModelStatusEnum.en_production:
        db.query(models.ModelVersion).filter(
            models.ModelVersion.dataset_id == version.dataset_id,
            models.ModelVersion.status == models.ModelStatusEnum.en_production,
            models.ModelVersion.id != version.id,
        ).update({"status": models.ModelStatusEnum.archive})
        version.deployed_at = datetime.utcnow()

    version.status = new_status
    db.commit()
    db.refresh(version)
    log_action(
        db, action="model.status_changed", user_id=admin.id,
        target=f"Version v{version.version_number} : {old_status.value} → {new_status.value}",
    )
    return version


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
