import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import get_current_user
from app.services.ml_features import (
    InputError, predict_and_explain, label_prediction, describe_fields,
)
from app.services.prediction_service import load_bundle, ModelUnavailable

logger = logging.getLogger("driftguard.predictions")

router = APIRouter(prefix="/predictions", tags=["Prédictions"])


def _get_version_or_404(db: Session, version_id: str) -> models.ModelVersion:
    version = db.query(models.ModelVersion).filter(models.ModelVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version de modèle introuvable")
    return version


def _load_or_409(version: models.ModelVersion):
    try:
        return load_bundle(version.mlflow_run_id)
    except ModelUnavailable as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/models", response_model=list[schemas.PredictableModelOut])
def predictable_models(
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    """Modèles en production utilisables pour une prédiction (avec le nom de leur dataset)."""
    versions = (
        db.query(models.ModelVersion)
        .filter(
            models.ModelVersion.status == models.ModelStatusEnum.en_production,
            models.ModelVersion.mlflow_run_id.isnot(None),
        )
        .order_by(models.ModelVersion.deployed_at.desc())
        .all()
    )
    return [
        schemas.PredictableModelOut(
            id=v.id,
            version_number=v.version_number,
            dataset_name=v.dataset.name,
            domain=v.dataset.domain.value,
            metrics=v.metrics,
        )
        for v in versions
    ]


@router.get("/schema/{model_version_id}", response_model=schemas.PredictionSchemaOut)
def prediction_schema(
    model_version_id: str,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    """Variables à saisir pour interroger ce modèle (celles qui comptent le plus pour lui)."""
    version = _get_version_or_404(db, model_version_id)
    _model, meta = _load_or_409(version)
    return schemas.PredictionSchemaOut(
        model_version_id=version.id,
        version_number=version.version_number,
        dataset_name=version.dataset.name,
        domain=version.dataset.domain.value,
        target_column=meta.get("target_column"),
        fields=describe_fields(meta),
    )


@router.post("/", response_model=schemas.PredictionOut, status_code=201)
def make_prediction(
    payload: schemas.PredictionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Page 'Faire une prédiction' : charge le modèle entraîné (MLflow), calcule la
    prédiction réelle et une explication locale par perturbation des variables
    (voir ml_features.py).
    """
    version = _get_version_or_404(db, payload.model_version_id)
    model, meta = _load_or_409(version)

    try:
        result = predict_and_explain(model, meta, payload.input_payload)
    except InputError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        logger.exception("Échec du calcul de prédiction")
        raise HTTPException(status_code=500, detail="Erreur lors du calcul de la prédiction.")

    prediction, probability_label = label_prediction(meta, result)

    log = models.PredictionLog(
        user_id=current_user.id,
        model_version_id=version.id,
        input_payload=result["inputs"],
        prediction=prediction,
        shap_explanation=result["contributions"],
        probability=result["probability"],
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return schemas.PredictionOut(
        id=log.id,
        prediction=log.prediction,
        shap_explanation=log.shap_explanation,
        created_at=log.created_at,
        probability=log.probability,
        probability_label=probability_label,
        model_version_id=log.model_version_id,
    )


@router.get("/history", response_model=list[schemas.PredictionOut])
def my_prediction_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Page 'Historique' de l'espace utilisateur (avec état vide si aucune prédiction)."""
    return (
        db.query(models.PredictionLog)
        .filter(models.PredictionLog.user_id == current_user.id)
        .order_by(models.PredictionLog.created_at.desc())
        .all()
    )
