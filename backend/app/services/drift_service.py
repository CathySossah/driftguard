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


def interpret_drift_metrics(
    metrics: list[dict],
    pvalue_threshold: float | None = None,
    variable_thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Transforme la sortie brute d'Evidently en résultat DriftGuard, en appliquant les seuils
    configurés (page Paramètres) :
      - pvalue_threshold : seuil global des tests à p-value (une variable dérive si p < seuil) ;
      - variable_thresholds : seuil propre à une variable (remplace le seuil global ; pour un
        test à distance — Wasserstein, Jensen-Shannon — c'est un seuil de distance : la variable
        dérive si la distance >= seuil).
    Le drift_score est la part des variables en dérive (0 à 1).
    """
    variable_thresholds = variable_thresholds or {}
    columns: dict[str, dict[str, Any]] = {}
    evidently_share = 0.0
    evidently_count = 0

    for metric in metrics:
        name = metric["metric_name"]

        if name.startswith("DriftedColumnsCount"):
            evidently_share = metric["value"]["share"]
            evidently_count = metric["value"]["count"]

        elif name.startswith("ValueDrift"):
            # Format : "ValueDrift(column=purchase_hour,method=K-S p_value,threshold=0.05)"
            column_name = name.split("column=")[1].split(",")[0]
            value = float(metric["value"])
            method = name.split("method=")[1].split(",")[0]
            default_threshold = float(name.split("threshold=")[1].rstrip(")"))
            is_pvalue = "p_value" in method  # sinon : test à distance (dérive quand la valeur est GRANDE)

            custom = variable_thresholds.get(column_name)
            if custom is not None:
                threshold = float(custom)
            elif is_pvalue and pvalue_threshold is not None:
                threshold = float(pvalue_threshold)
            else:
                threshold = default_threshold

            drifted = bool(value < threshold) if is_pvalue else bool(value >= threshold)
            columns[column_name] = {
                "p_value": value,  # nom conservé pour l'interface : p-value ou distance selon "kind"
                "threshold": threshold,
                "default_threshold": default_threshold,
                "custom": custom is not None,
                "kind": "p_value" if is_pvalue else "distance",
                "drifted": drifted,
                "method": method,
            }

    if columns:
        drifted_count = sum(1 for c in columns.values() if c["drifted"])
        drift_share = drifted_count / len(columns)
    else:
        drifted_count, drift_share = evidently_count, evidently_share

    return {
        "drift_score": round(float(drift_share), 4),
        "drift_detected": bool(drifted_count > 0),
        "columns": columns,
    }


def compute_drift(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    pvalue_threshold: float | None = None,
    variable_thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Compare deux jeux de données et retourne :
      - drift_score : part des variables en dérive (0.0 à 1.0), comparée au seuil d'alerte
        configuré (page Paramètres) ;
      - drift_detected : booléen, True si au moins une variable est en dérive ;
      - columns : détail par variable (valeur du test statistique, seuil appliqué, dérive ou non).
    Les seuils (globaux et par variable) sont appliqués par interpret_drift_metrics.
    """
    # Import tardif : Evidently est lourd en mémoire, on ne le charge qu'au premier calcul.
    from evidently import Report
    from evidently.presets import DataDriftPreset

    report = Report(metrics=[DataDriftPreset()])
    snapshot = report.run(reference_data=reference_df, current_data=current_df)
    result = snapshot.dict()
    return interpret_drift_metrics(result["metrics"], pvalue_threshold, variable_thresholds)
