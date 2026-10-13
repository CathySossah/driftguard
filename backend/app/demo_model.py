"""
Modèle de démonstration pré-entraîné.

Entraîner un modèle au démarrage de l'API (via MLflow) est coûteux en mémoire :
sur un hébergeur gratuit à 512 Mo, cela provoque des redémarrages en boucle.
On construit donc le modèle de démonstration UNE FOIS, au moment de construire
l'image Docker (voir Dockerfile), avec pandas et scikit-learn seulement — sans
MLflow. Au démarrage, l'API se contente d'enregistrer ce modèle en base
(bootstrap.py) et de le charger depuis le disque pour les prédictions.

    python -m app.demo_model     # (re)construit app/demo_assets/demo_model.joblib
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from app.services.ml_features import build_real_training_frame, fit_and_evaluate, build_meta

ASSETS_DIR = Path(__file__).resolve().parent / "demo_assets"
BUNDLE_PATH = ASSETS_DIR / "demo_model.joblib"
METRICS_PATH = ASSETS_DIR / "demo_model.json"
LOCAL_RUN_ID = "local:demo_model"
DATASET_NAME = "Démo — Transactions mobile money (données simulées)"


def _demo_transactions(n: int = 3000) -> pd.DataFrame:
    """
    Transactions synthétiques avec des motifs de fraude lisibles (pour que la démonstration
    soit parlante) : la fraude est plus fréquente la nuit, pour les montants élevés et sur mobile.
    Mêmes colonnes que le simulateur utilisé pour le monitoring (data_simulator.py).
    """
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "TransactionAmt": np.round(rng.gamma(2.0, 60.0, n), 2),
        "purchase_hour": rng.integers(0, 24, n),
        "device_type": rng.choice(["mobile", "desktop", "tablet"], n, p=[0.6, 0.3, 0.1]),
        "card_type": rng.choice(["visa", "mastercard", "amex"], n, p=[0.5, 0.4, 0.1]),
    })
    night = (df["purchase_hour"] >= 22) | (df["purchase_hour"] <= 4)
    p = 0.02 + 0.45 * night + 0.25 * (df["TransactionAmt"] > 300) + 0.10 * (df["device_type"] == "mobile")
    df["isFraud"] = rng.binomial(1, np.clip(p, 0, 0.9))
    return df


def build(path: Path = BUNDLE_PATH) -> dict:
    X, y, parts = build_real_training_frame(_demo_transactions(), "isFraud")
    model, metrics, notes = fit_and_evaluate(X, y, n_estimators=100, max_depth=6, min_samples_leaf=5)
    meta = build_meta(
        parts, X, importances=model.feature_importances_, domain="finance", dataset_name=DATASET_NAME
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "meta": meta}, path, compress=3)
    path.with_suffix(".json").write_text(json.dumps({"metrics": metrics, "notes": notes}), encoding="utf-8")
    return metrics


if __name__ == "__main__":
    print("Modèle de démonstration construit :", build())
