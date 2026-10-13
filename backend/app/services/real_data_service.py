"""
Charge un dataset réel (importé via /datasets/upload) et le découpe en un lot
de référence et un lot "courant", pour le monitoring de dérive et
l'entraînement — en remplacement du simulateur (data_simulator.py) quand un
vrai fichier a été importé.

Hypothèse simplificatrice, documentée : à défaut de colonne de date/heure
explicite, les lignes sont supposées ordonnées chronologiquement dans le
fichier (cas courant pour un export de transactions). Si une colonne
ressemblant à une date/heure est détectée, le dataset est trié dessus avant
découpage, pour un résultat plus fiable.
"""
import re
from typing import Optional

import pandas as pd

# Noms de colonnes usuels pour une cible de classification binaire
# (fraude, churn, défaut de paiement...) — utilisés seulement si l'utilisateur
# n'a pas explicitement renseigné target_column à l'import.
_COMMON_TARGET_NAMES = [
    "isfraud", "is_fraud", "fraud", "target", "label", "class",
    "churn", "readmitted", "default", "outcome",
]

_DATE_LIKE_PATTERN = re.compile(r"(date|time|dt|timestamp)", re.IGNORECASE)


class DatasetLoadError(Exception):
    """Levée quand le dataset ne peut pas être chargé ou découpé correctement."""


def load_dataframe(source_path: str) -> pd.DataFrame:
    try:
        return pd.read_csv(source_path)
    except Exception as e:
        raise DatasetLoadError(f"Impossible de lire le fichier CSV : {e}")


def looks_like_id(series: pd.Series) -> bool:
    """
    Vrai si la colonne ressemble à un identifiant (une valeur quasi unique par
    ligne : numéro de transaction, e-mail...). Une variable continue à
    décimales (un montant, une mesure) a elle aussi beaucoup de valeurs
    uniques mais N'EST PAS un identifiant : on ne l'écarte donc pas.
    """
    n = len(series)
    if n == 0 or series.nunique(dropna=True) < n * 0.98:
        return False
    if pd.api.types.is_float_dtype(series):
        values = series.dropna()
        return bool((values == values.round()).all())  # entiers stockés en float
    return True


def guess_target_column(df: pd.DataFrame) -> Optional[str]:
    """Essaie de deviner la colonne cible si elle n'a pas été précisée à l'import."""
    lower_cols = {c.lower(): c for c in df.columns}
    for candidate in _COMMON_TARGET_NAMES:
        if candidate in lower_cols:
            return lower_cols[candidate]
    return None


def _find_date_column(df: pd.DataFrame) -> Optional[str]:
    for col in df.columns:
        if _DATE_LIKE_PATTERN.search(col):
            return col
    return None


def split_reference_current(
    df: pd.DataFrame, current_fraction: float = 0.2, time_column: Optional[str] = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Découpe le dataset en (référence, courant) : la référence sert de socle
    "entraînement", le lot courant simule les données de production les plus
    récentes pour le calcul de dérive.

    `time_column`, si fourni explicitement (configuré par l'admin via
    /datasets/{id}/configure), est prioritaire sur la détection automatique
    par nom de colonne.
    """
    if len(df) < 20:
        raise DatasetLoadError(
            f"Le dataset ne contient que {len(df)} lignes — au moins 20 sont nécessaires "
            "pour un découpage référence/courant exploitable."
        )

    date_col = time_column if time_column and time_column in df.columns else _find_date_column(df)
    ordered = df.sort_values(date_col) if date_col else df

    split_index = int(len(ordered) * (1 - current_fraction))
    reference = ordered.iloc[:split_index].reset_index(drop=True)
    current = ordered.iloc[split_index:].reset_index(drop=True)
    return reference, current
