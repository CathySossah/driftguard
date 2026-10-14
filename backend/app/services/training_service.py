"""
Service de ré-entraînement — entraîne un modèle réel et le journalise dans
MLflow. Utilise le VRAI dataset importé par l'utilisateur (via
/datasets/upload) quand un fichier est disponible ; sinon, retombe sur le
simulateur (data_simulator.py) pour permettre les démonstrations sans
dataset réel encore importé.

Avec le modèle, on journalise aussi un "bundle" (modèle + métadonnées de
préparation des variables) : c'est ce qui permet à l'API de prédiction
(prediction_service.py) de rejouer exactement le même encodage et de calculer
une vraie prédiction avec explication.
"""
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

import joblib

from app import models
from app.services.real_data_service import load_dataframe, DatasetLoadError
from app.services.ml_features import (  # noqa: F401  (constantes ré-exportées)
    TrainingError, MAX_TRAINING_ROWS, MAX_CATEGORY_CARDINALITY,
    build_simulated_training_frame, build_real_training_frame, build_meta, fit_and_evaluate,
    train_and_compare, feature_importances, normalize_training_options, ALGORITHMS, BALANCING_METHODS,
)

logger = logging.getLogger("driftguard.training")

from app.services.prediction_service import MLFLOW_TRACKING_URI, BUNDLE_ARTIFACT_NAME  # noqa: F401

MLFLOW_EXPERIMENT_NAME = "driftguard-fraud-detection"


def _ensure_experiment() -> None:
    """Configure MLflow ; MLFLOW_ARTIFACT_ROOT (optionnel) fixe le dossier des artefacts."""
    import mlflow  # import tardif : MLflow est lourd en mémoire, on ne le charge qu'au premier entraînement

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    root = os.getenv("MLFLOW_ARTIFACT_ROOT")
    if root and mlflow.get_experiment_by_name(MLFLOW_EXPERIMENT_NAME) is None:
        try:
            os.makedirs(root, exist_ok=True)
            mlflow.create_experiment(MLFLOW_EXPERIMENT_NAME, artifact_location=Path(root).resolve().as_uri())
        except Exception:
            pass  # créée entre-temps par un autre entraînement : on continue
    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)


def train_and_log_model(
    dataset: Optional[models.Dataset],
    drift_level: float = 0.0,
    algorithms: Optional[list[str]] = None,
    balancing: Optional[str] = None,
    progress=None,
) -> dict[str, Any]:
    """
    Entraîne un nouveau modèle et le journalise dans MLflow.
    `dataset` : l'objet Dataset (avec source_path) à utiliser. Si son
    `source_path` est vide (aucun fichier importé), retombe sur les données
    simulées — pratique pour les démonstrations sans dataset réel.
    `algorithms` / `balancing` : choix de l'administrateur (voir ml_features.ALGORITHMS
    et BALANCING_METHODS). Tous les algorithmes choisis sont entraînés et comparés ;
    le meilleur (F1) devient le modèle publié.
    `progress(pourcentage, libellé)` : appelé au fil de l'entraînement.
    Retourne un dict {success, mlflow_run_id, metrics, error_message, training_results...}.
    """
    algorithms, balancing = normalize_training_options(algorithms, balancing)

    def report(pct: int, label: str) -> None:
        if progress:
            try:
                progress(pct, label)
            except Exception:  # le suivi ne doit jamais faire échouer l'entraînement
                logger.debug("Mise à jour de la progression impossible", exc_info=True)

    try:
        import mlflow  # import tardif (voir _ensure_experiment)
        import mlflow.sklearn

        report(3, "Préparation de l'entraînement")
        if dataset is not None and dataset.source_path:
            try:
                report(8, "Chargement du fichier")
                df = load_dataframe(dataset.source_path)
                report(18, "Préparation des variables")
                X, y, parts = build_real_training_frame(df, dataset.target_column)
            except DatasetLoadError as e:
                raise TrainingError(str(e))
            data_source_label = f"dataset réel ({dataset.name})"
        else:
            X, y, parts = build_simulated_training_frame(drift_level)
            data_source_label = "données simulées (aucun dataset importé)"

        _ensure_experiment()

        with mlflow.start_run() as run:
            # L'entraînement s'adapte à la taille et à l'équilibre des données au lieu
            # d'échouer ; les adaptations faites sont consignées dans `notes`.
            comparison = train_and_compare(
                X, y, algorithms, balancing, progress=report, class_labels=parts.get("class_labels"),
            )
            model = comparison["model"]
            metrics = comparison["metrics"]
            notes = list(parts.get("notes", [])) + comparison["notes"]
            for note in notes:
                logger.info("Entraînement : %s", note)

            report(92, "Enregistrement dans MLflow")
            meta = build_meta(
                parts, X,
                importances=feature_importances(model),
                domain=dataset.domain.value if dataset is not None else "finance",
                dataset_name=dataset.name if dataset is not None else None,
            )

            mlflow.log_param("algorithms", ",".join(comparison["algorithms"]))
            mlflow.log_param("balancing", comparison["balancing"])
            mlflow.log_param("best_algorithm", comparison["best"])
            mlflow.log_param("evaluation", comparison["evaluation"])
            mlflow.log_param("training_samples", len(X))
            mlflow.log_param("feature_count", X.shape[1])
            mlflow.log_param("data_source", data_source_label)
            mlflow.log_param("target_column", parts.get("target_column"))
            if notes:
                mlflow.log_param("notes", " | ".join(notes)[:450])
            if dataset is None or not dataset.source_path:
                mlflow.log_param("simulated_drift_level", drift_level)
            mlflow.log_metrics(metrics)
            for r in comparison["results"]:
                if "metrics" in r:
                    for key in ("accuracy", "f1", "recall", "precision"):
                        mlflow.log_metric(f"{key}_{r['algorithm']}", r["metrics"][key])
            # Les versions récentes de MLflow sérialisent avec skops, qui refuse par défaut
            # certains types internes de scikit-learn : on autorise celui des arbres. Cet
            # enregistrement n'est qu'un « plus » (registre MLflow) : les prédictions utilisent
            # le bundle ci-dessous, donc un échec ici ne doit jamais faire échouer l'entraînement.
            try:
                mlflow.sklearn.log_model(model, name="model", skops_trusted_types=["sklearn.tree._tree.Tree"])
            except Exception as exc:
                logger.warning("Enregistrement du modèle au format MLflow impossible : %s", exc)
            mlflow.log_dict(meta, "model_meta.json")

            # Bundle (modèle + métadonnées) relu par l'API de prédiction.
            with tempfile.TemporaryDirectory() as tmp:
                bundle_path = os.path.join(tmp, BUNDLE_ARTIFACT_NAME)
                joblib.dump({"model": model, "meta": meta}, bundle_path, compress=3)
                mlflow.log_artifact(bundle_path)

            report(98, "Finalisation")
            return {
                "success": True,
                "mlflow_run_id": run.info.run_id,
                "metrics": metrics,
                "error_message": None,
                "target_column": parts.get("target_column"),
                "notes": notes,
                "training_results": {
                    "algorithms": comparison["algorithms"],
                    "balancing": comparison["balancing"],
                    "best": comparison["best"],
                    "evaluation": comparison["evaluation"],
                    "results": comparison["results"],
                    "notes": notes,
                },
            }

    except TrainingError as e:
        return {"success": False, "mlflow_run_id": None, "metrics": None, "error_message": str(e)}
    except Exception as e:  # garde-fou : toute autre erreur inattendue est capturée proprement
        return {"success": False, "mlflow_run_id": None, "metrics": None, "error_message": f"Erreur inattendue : {e}"}
