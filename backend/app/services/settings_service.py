"""
Paramètres de surveillance du drift, modifiables depuis la page « Paramètres » :
  - alert_threshold      : part de variables en dérive (0 à 1) à partir de laquelle une alerte est créée ;
  - pvalue_threshold     : seuil global des tests à p-value (une variable dérive si p < seuil) ;
  - variable_thresholds  : seuils propres à certaines variables (nom de variable -> seuil).
Stockés en base (table app_settings) ; les valeurs par défaut s'appliquent tant que rien n'est modifié.
"""
from typing import Any, Optional

from sqlalchemy.orm import Session

from app import models

SETTINGS_KEY = "drift"
DEFAULTS: dict[str, Any] = {
    "alert_threshold": 0.20,
    "pvalue_threshold": 0.05,
    "variable_thresholds": {},
    "email_alerts_enabled": True,
}


class SettingsError(ValueError):
    """Valeur de paramètre invalide (message lisible affiché à l'administrateur)."""


def get_settings(db: Session) -> dict[str, Any]:
    row = db.query(models.AppSetting).filter(models.AppSetting.key == SETTINGS_KEY).first()
    stored = row.value if row and isinstance(row.value, dict) else {}
    return {
        "alert_threshold": float(stored.get("alert_threshold", DEFAULTS["alert_threshold"])),
        "pvalue_threshold": float(stored.get("pvalue_threshold", DEFAULTS["pvalue_threshold"])),
        "variable_thresholds": dict(stored.get("variable_thresholds") or {}),
        "email_alerts_enabled": bool(stored.get("email_alerts_enabled", DEFAULTS["email_alerts_enabled"])),
    }


def update_settings(
    db: Session,
    alert_threshold: Optional[float] = None,
    pvalue_threshold: Optional[float] = None,
    variable_thresholds: Optional[dict[str, Optional[float]]] = None,
    email_alerts_enabled: Optional[bool] = None,
) -> dict[str, Any]:
    """Met à jour les paramètres fournis (les autres restent inchangés). Une valeur None retire le seuil d'une variable."""
    current = get_settings(db)

    if alert_threshold is not None:
        if not 0.0 < float(alert_threshold) <= 1.0:
            raise SettingsError("Le seuil d'alerte doit être compris entre 1 % et 100 % des variables.")
        current["alert_threshold"] = float(alert_threshold)

    if pvalue_threshold is not None:
        if not 0.0 < float(pvalue_threshold) <= 0.5:
            raise SettingsError("Le seuil de p-value doit être compris entre 0 (exclu) et 0,5.")
        current["pvalue_threshold"] = float(pvalue_threshold)

    if email_alerts_enabled is not None:
        current["email_alerts_enabled"] = bool(email_alerts_enabled)

    for name, value in (variable_thresholds or {}).items():
        if value is None:
            current["variable_thresholds"].pop(name, None)
            continue
        if not 0.0 < float(value) <= 1.0:
            raise SettingsError(f"Le seuil de la variable « {name} » doit être compris entre 0 (exclu) et 1.")
        current["variable_thresholds"][name] = float(value)

    row = db.query(models.AppSetting).filter(models.AppSetting.key == SETTINGS_KEY).first()
    if row is None:
        db.add(models.AppSetting(key=SETTINGS_KEY, value=current))
    else:
        row.value = current  # nouvel objet : SQLAlchemy détecte le changement
    db.commit()
    return current
