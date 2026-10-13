from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import get_current_user, require_admin
from app.services.monitoring_service import process_monitoring_result, compute_drift_for_version
from app.services import scenario_state

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


@router.get("/", response_model=list[schemas.MonitoringRunOut])
def list_monitoring_runs(
    model_version_id: str | None = None,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    """Page 'Monitoring détaillé' : historique des exécutions."""
    query = db.query(models.MonitoringRun)
    if model_version_id:
        query = query.filter(models.MonitoringRun.model_version_id == model_version_id)
    return query.order_by(models.MonitoringRun.executed_at.desc()).all()


@router.post("/", response_model=schemas.MonitoringRunOut, status_code=201)
def submit_monitoring_run(
    payload: schemas.MonitoringRunCreate,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    """
    Enregistre manuellement un résultat de calcul de dérive déjà produit en
    externe (ex. par un pipeline data science indépendant). Pour un calcul
    réel via Evidently AI directement depuis l'API, voir POST /monitoring/run-now.
    """
    return process_monitoring_result(
        db, payload.model_version_id, payload.drift_score,
        payload.drift_detected, payload.report_json,
    )


@router.post("/run-now/{model_version_id}", response_model=schemas.MonitoringRunOut, status_code=201)
def run_monitoring_now(
    model_version_id: str,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    """
    Déclenche IMMÉDIATEMENT un cycle de monitoring réel avec Evidently AI
    (au lieu d'attendre le prochain passage du job planifié) — utile pour
    la démonstration et les tests du protocole expérimental (chapitre 2.4).

    Utilise le VRAI dataset importé (comparaison référence/courant du fichier
    CSV) si un fichier a été chargé pour ce modèle ; sinon retombe sur le
    simulateur à dérive progressive contrôlée pour la démonstration.
    """
    version = db.query(models.ModelVersion).filter(models.ModelVersion.id == model_version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version de modèle introuvable")

    result = compute_drift_for_version(db, version)

    return process_monitoring_result(
        db,
        model_version_id=model_version_id,
        drift_score=result["drift_score"],
        drift_detected=result["drift_detected"],
        report_json=result["report_json"],
    )


@router.post("/reset-scenario/{model_version_id}")
def reset_scenario(
    model_version_id: str,
    _admin: models.User = Depends(require_admin),
):
    """Réinitialise le niveau de dérive simulé pour rejouer un scénario depuis le début."""
    scenario_state.reset_drift_level(model_version_id)
    return {"message": "Scénario réinitialisé", "model_version_id": model_version_id}
