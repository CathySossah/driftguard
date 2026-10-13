"""
Suivi en mémoire du niveau de dérive simulé par version de modèle, pour
rejouer un scénario de 'dérive progressive' sur des appels successifs
(cf. chapitre 2.4 "Protocole expérimental").

⚠️ Stockage en mémoire (perdu au redémarrage du serveur) — suffisant pour la
démonstration et l'expérimentation en local. Pour une persistance entre
redémarrages, déplacer cet état dans une table dédiée en base de données.
"""
DRIFT_STEP = 0.08  # incrément de dérive à chaque cycle de monitoring
MAX_DRIFT_LEVEL = 1.0

_state: dict[str, float] = {}


def advance_drift_level(model_version_id: str) -> float:
    """Augmente le niveau de dérive simulé d'un cran et retourne la nouvelle valeur."""
    current = _state.get(model_version_id, 0.0)
    new_level = min(current + DRIFT_STEP, MAX_DRIFT_LEVEL)
    _state[model_version_id] = new_level
    return new_level


def get_drift_level(model_version_id: str) -> float:
    return _state.get(model_version_id, 0.0)


def reset_drift_level(model_version_id: str) -> None:
    _state[model_version_id] = 0.0


def set_drift_level(model_version_id: str, level: float) -> None:
    """Permet de sauter directement à un niveau (utile pour simuler une dérive brutale)."""
    _state[model_version_id] = max(0.0, min(level, MAX_DRIFT_LEVEL))
