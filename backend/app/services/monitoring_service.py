"""
Logique métier partagée entre l'endpoint manuel (/monitoring/run-now) et le
job planifié (scheduler.py) : enregistre un résultat de calcul de dérive et
crée automatiquement une alerte si le seuil est dépassé — mais ne déclenche
JAMAIS le ré-entraînement directement (cf. app/routers/alerts.py : seule la
validation humaine explicite d'un administrateur peut le faire).
"""
from typing import Any

from sqlalchemy.orm import Session

from app import models
from app.services.drift_service import compute_drift
from app.services.data_simulator import get_reference_dataset, get_current_batch
from app.services.real_data_service import load_dataframe, split_reference_current, looks_like_id, DatasetLoadError
from app.services import scenario_state

# Seuil de dérive par défaut. En production, ce seuil doit être configurable
# par variable/dataset (cf. page "Paramètres" de la maquette) — actuellement
# une valeur globale unique, à raffiner en un seuil par ModelVersion/Dataset.
DEFAULT_DRIFT_THRESHOLD = 0.20


def compute_drift_for_version(db: Session, version: models.ModelVersion) -> dict[str, Any]:
    """
    Calcule un cycle de dérive pour une version de modèle : utilise le VRAI
    dataset importé (découpage référence/courant du fichier CSV) s'il est
    disponible, sinon retombe sur le simulateur avec dérive progressive
    contrôlée (cf. scenario_state.py) pour permettre la démonstration.
    """
    dataset = db.query(models.Dataset).filter(models.Dataset.id == version.dataset_id).first()

    if dataset is not None and dataset.source_path:
        try:
            df = load_dataframe(dataset.source_path)
            reference, current = split_reference_current(df, time_column=dataset.time_column)

            # Colonnes à exclure du calcul de dérive : la cible (pas une
            # "feature"), la colonne temporelle (comparer le temps à
            # lui-même après un split chronologique est trivialement
            # toujours "en dérive" — non informatif), et les colonnes de
            # type identifiant (une valeur quasi unique par ligne, ex.
            # TransactionID — leur "dérive" ne reflète rien d'utile).
            exclude = set()
            if dataset.target_column and dataset.target_column in reference.columns:
                exclude.add(dataset.target_column)
            if dataset.time_column and dataset.time_column in reference.columns:
                exclude.add(dataset.time_column)
            id_like = [c for c in reference.columns if c not in exclude and looks_like_id(reference[c])]
            exclude.update(id_like)

            feature_cols = [c for c in reference.columns if c not in exclude]
            reference = reference[feature_cols]
            current = current[feature_cols]

            result = compute_drift(reference, current)
            return {
                "drift_score": result["drift_score"],
                "drift_detected": result["drift_detected"],
                "report_json": {"columns": result["columns"], "source": "dataset_reel", "dataset_id": dataset.id},
            }
        except DatasetLoadError:
            pass  # retombe sur le simulateur si le fichier n'est plus lisible

    drift_level = scenario_state.advance_drift_level(version.id)
    reference = get_reference_dataset()
    current = get_current_batch(drift_level=drift_level)
    result = compute_drift(reference, current)
    return {
        "drift_score": result["drift_score"],
        "drift_detected": result["drift_detected"],
        "report_json": {"columns": result["columns"], "source": "simule", "simulated_drift_level": drift_level},
    }


def _severity_from_score(score: float) -> models.SeverityEnum:
    if score >= 0.60:
        return models.SeverityEnum.critique
    if score >= 0.35:
        return models.SeverityEnum.moyenne
    return models.SeverityEnum.faible


def process_monitoring_result(
    db: Session,
    model_version_id: str,
    drift_score: float,
    drift_detected: bool,
    report_json: dict[str, Any] | None,
    threshold: float = DEFAULT_DRIFT_THRESHOLD,
) -> models.MonitoringRun:
    """Enregistre le run et crée une alerte 'en_attente' si le seuil est dépassé."""
    run = models.MonitoringRun(
        model_version_id=model_version_id,
        drift_score=drift_score,
        drift_detected=drift_detected,
        report_json=report_json,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    if drift_score >= threshold:
        existing_pending = (
            db.query(models.Alert)
            .join(models.MonitoringRun)
            .filter(
                models.MonitoringRun.model_version_id == model_version_id,
                models.Alert.status == models.AlertStatusEnum.en_attente,
            )
            .first()
        )
        if existing_pending is None:
            alert = models.Alert(
                monitoring_run_id=run.id,
                severity=_severity_from_score(drift_score),
                status=models.AlertStatusEnum.en_attente,
            )
            db.add(alert)
            db.commit()
            # TODO : brancher ici l'envoi d'e-mail réel (SMTP) aux administrateurs.
        # Sinon : une alerte est déjà en attente de validation pour ce modèle,
        # on évite de multiplier les notifications pour la même dérive en cours.

    return run
