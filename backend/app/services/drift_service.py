"""
Service de détection de dérive — implémentation réelle avec Evidently AI.

Ce module remplace le placeholder précédent : il calcule un score de dérive
authentique (et non simulé) en comparant un jeu de données de référence
(distribution d'entraînement) à un lot de données courantes (production),
grâce à des tests statistiques (Kolmogorov-Smirnov pour les variables
continues, Z-test pour les variables catégorielles) — cf. chapitre 1 du
mémoire (revue de littérature sur les méthodes de détection).
"""
from typing import Any

import pandas as pd
from evidently import Report
from evidently.presets import DataDriftPreset


def compute_drift(reference_df: pd.DataFrame, current_df: pd.DataFrame) -> dict[str, Any]:
    """
    Compare deux jeux de données et retourne :
      - drift_score : part des variables en dérive (0.0 à 1.0), utilisée comme
        métrique globale comparée au seuil configuré (section Paramètres).
      - drift_detected : booléen, True si au moins une variable est en dérive.
      - columns : détail par variable (p-value du test statistique, dérive ou non),
        alimente la page "Monitoring détaillé" (tableau "Dérive par variable").
    """
    report = Report(metrics=[DataDriftPreset()])
    snapshot = report.run(reference_data=reference_df, current_data=current_df)
    result = snapshot.dict()

    columns: dict[str, dict[str, Any]] = {}
    drifted_count = 0
    drift_share = 0.0

    for metric in result["metrics"]:
        name = metric["metric_name"]

        if name.startswith("DriftedColumnsCount"):
            drift_share = metric["value"]["share"]
            drifted_count = metric["value"]["count"]

        elif name.startswith("ValueDrift"):
            # Format : "ValueDrift(column=purchase_hour,method=K-S p_value,threshold=0.05)"
            column_name = name.split("column=")[1].split(",")[0]
            p_value = float(metric["value"])
            threshold = float(name.split("threshold=")[1].rstrip(")"))
            columns[column_name] = {
                "p_value": p_value,
                "threshold": threshold,
                "drifted": bool(p_value < threshold),
                "method": name.split("method=")[1].split(",")[0],
            }

    return {
        "drift_score": round(float(drift_share), 4),
        "drift_detected": bool(drifted_count > 0),
        "columns": columns,
    }
