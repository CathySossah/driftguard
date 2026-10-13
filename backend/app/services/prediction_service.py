"""
Chargement d'un modèle entraîné depuis MLflow et calcul d'une vraie
prédiction (avec explication). Les modèles sont gardés en mémoire (cache) :
un run MLflow est immuable, il n'y a donc rien à invalider.
"""
import os
import re
import threading
from pathlib import Path
from typing import Any

import joblib

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "sqlite:///./mlflow.db")
BUNDLE_ARTIFACT_NAME = "model_bundle.joblib"

# Un "run" de la forme « local:<nom> » désigne un modèle pré-entraîné livré avec l'application
# (dossier demo_assets) : il se charge depuis le disque, sans MLflow (voir demo_model.py).
LOCAL_PREFIX = "local:"
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "demo_assets"

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

    if run_id.startswith(LOCAL_PREFIX):
        name = run_id[len(LOCAL_PREFIX):]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ModelUnavailable("Identifiant de modèle local invalide.")
        try:
            bundle = joblib.load(_ASSETS_DIR / f"{name}.joblib")
            model, meta = bundle["model"], bundle["meta"]
        except Exception as e:
            raise ModelUnavailable(f"Le modèle de démonstration est introuvable sur le disque. Détail : {e}")
        with _lock:
            _CACHE[run_id] = (model, meta)
        return model, meta

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
