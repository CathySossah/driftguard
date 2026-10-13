"""
Chargement d'un modèle entraîné depuis MLflow et calcul d'une vraie
prédiction (avec explication). Les modèles sont gardés en mémoire (cache) :
un run MLflow est immuable, il n'y a donc rien à invalider.
"""
import threading
from typing import Any

import joblib

from app.services.training_service import MLFLOW_TRACKING_URI, BUNDLE_ARTIFACT_NAME

_CACHE: dict[str, tuple[Any, dict]] = {}
_CACHE_MAX = 6
_lock = threading.Lock()


class ModelUnavailable(Exception):
    """Le modèle (ou ses métadonnées) est introuvable dans MLflow."""


def load_bundle(run_id: str | None) -> tuple[Any, dict]:
    if not run_id:
        raise ModelUnavailable("Cette version de modèle n'est liée à aucun run MLflow : elle ne peut pas servir de prédiction.")

    with _lock:
        if run_id in _CACHE:
            return _CACHE[run_id]

    try:
        import mlflow
        import mlflow.artifacts

        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        local_path = mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path=BUNDLE_ARTIFACT_NAME)
        bundle = joblib.load(local_path)
        model, meta = bundle["model"], bundle["meta"]
    except Exception as e:
        raise ModelUnavailable(
            "Le modèle est introuvable dans MLflow (fichiers perdus après un redémarrage, ou modèle entraîné "
            "avant l'ajout des prédictions réelles). Ré-entraînez ce modèle pour le rendre utilisable. "
            f"Détail : {e}"
        )

    with _lock:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[run_id] = (model, meta)
    return model, meta
