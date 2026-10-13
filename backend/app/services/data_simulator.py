"""
Simulateur de données — génère un jeu de référence (distribution d'entraînement)
et des lots "courants" (production) avec un niveau de dérive contrôlable.

⚠️ Ceci est un simulateur pour démonstration et protocole expérimental (cf.
chapitre 2.4 "Protocole expérimental" du mémoire — scénarios de dérive
progressive, brutale, saisonnière). En production, `get_current_batch()` doit
être remplacé par la lecture des transactions réelles les plus récentes
(base de données, data warehouse, flux Kafka, etc.).

Features simulées, inspirées du dataset réel IEEE-CIS Fraud Detection :
  - TransactionAmt   (continue)
  - purchase_hour    (continue, 0-23)
  - device_type      (catégorielle : mobile / desktop)
  - card_type        (catégorielle : visa / mastercard / amex)
"""
import numpy as np
import pandas as pd

_RNG_SEED = 42


def get_reference_dataset(n: int = 500) -> pd.DataFrame:
    """Jeu de référence fixe, représentant la distribution d'entraînement (v12)."""
    rng = np.random.default_rng(_RNG_SEED)
    return pd.DataFrame({
        "TransactionAmt": rng.gamma(2, 50, n),
        "purchase_hour": np.clip(rng.normal(14, 4, n), 0, 23),
        "device_type": rng.choice(["mobile", "desktop"], n, p=[0.6, 0.4]),
        "card_type": rng.choice(["visa", "mastercard", "amex"], n, p=[0.5, 0.35, 0.15]),
    })


def get_current_batch(n: int = 200, drift_level: float = 0.0, seed: int | None = None) -> pd.DataFrame:
    """
    Génère un lot "de production" avec un niveau de dérive contrôlé.

    drift_level = 0.0  -> même distribution que la référence (pas de dérive)
    drift_level = 1.0  -> dérive maximale (simule un changement brutal de comportement)
    Valeurs intermédiaires -> dérive progressive (cf. scénario "dérive progressive").
    """
    rng = np.random.default_rng(seed)
    drift_level = max(0.0, min(1.0, drift_level))

    # purchase_hour : la moyenne glisse progressivement de 14h vers 23h
    hour_mean = 14 + drift_level * 9
    hour_std = 4 - drift_level * 2  # distribution qui se resserre aussi (achats de nuit groupés)

    # device_type : la part de mobile augmente avec la dérive
    p_mobile = 0.6 + drift_level * 0.35
    p_mobile = min(p_mobile, 0.97)

    return pd.DataFrame({
        "TransactionAmt": rng.gamma(2, 50, n),  # stable, ne dérive pas dans ce scénario
        "purchase_hour": np.clip(rng.normal(hour_mean, max(hour_std, 0.5), n), 0, 23),
        "device_type": rng.choice(["mobile", "desktop"], n, p=[p_mobile, 1 - p_mobile]),
        "card_type": rng.choice(["visa", "mastercard", "amex"], n, p=[0.5, 0.35, 0.15]),
    })
