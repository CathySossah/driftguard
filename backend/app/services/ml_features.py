"""
Préparation des variables, encodage d'une saisie utilisateur et explication
locale d'une prédiction.

Ce module est volontairement indépendant de la base de données et de MLflow
(il n'utilise que pandas / numpy) : la MÊME logique de préparation sert à
l'entraînement (training_service.py) et à l'inférence (prediction_service.py),
ce qui garantit que le modèle reçoit à la prédiction exactement les mêmes
colonnes que pendant son entraînement.

Explication d'une prédiction : pour chaque variable, on remplace sa valeur par
une valeur "typique" du jeu d'entraînement (médiane pour une variable
numérique, modalité la plus fréquente pour une variable catégorielle) et on
mesure de combien la probabilité change. C'est une explication locale par
perturbation (model-agnostic), pas un calcul de valeurs SHAP exactes.
"""
from __future__ import annotations

import math
import time
import warnings
from typing import Any, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, recall_score, precision_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight

from app.services.data_simulator import get_reference_dataset, get_current_batch
from app.services.real_data_service import guess_target_column, looks_like_id

META_VERSION = 1

# Pour garder un temps d'entraînement raisonnable en démonstration, on limite
# le nombre de lignes utilisées même si le CSV importé en contient beaucoup
# plus (ex. IEEE-CIS Fraud Detection : ~590 000 lignes).
MAX_TRAINING_ROWS = 8000

# Une colonne catégorielle avec plus de valeurs uniques que ce seuil est
# considérée comme un identifiant ou du texte libre, et donc écartée plutôt
# qu'encodée en dummies (éviterait une explosion du nombre de colonnes).
MAX_CATEGORY_CARDINALITY = 40

# Au-delà de ce nombre de valeurs distinctes, la colonne cible est considérée
# comme continue (ou trop riche) : elle est alors regroupée en classes.
MAX_TARGET_CLASSES = 20

# Le filtre "identifiants" n'a de sens que sur un échantillon assez grand
# (sur 30 lignes, un âge ou un code a naturellement presque une valeur par ligne).
MIN_ROWS_FOR_ID_FILTER = 100

# En dessous de ce nombre de lignes, on ne réserve pas de jeu de test.
MIN_ROWS_FOR_TEST_SPLIT = 8

# Nombre maximal de variables proposées dans le formulaire de prédiction
# (les plus importantes pour le modèle) ; les autres prennent une valeur
# typique du jeu d'entraînement.
MAX_FORM_FEATURES = 12

# Libellés de classe considérés comme "positifs" (fraude) pour un jeu de
# données du domaine finance.
_POSITIVE_TOKENS = {"1", "true", "yes", "oui", "y", "fraud", "fraude", "fraudulent", "suspecte"}


class TrainingError(Exception):
    """Levée quand l'entraînement ne peut pas aboutir (données insuffisantes, etc.)."""


class InputError(ValueError):
    """Levée quand la saisie d'une prédiction est invalide (valeur non numérique, modalité inconnue...)."""


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------
def _f(x: Any, default: float = 0.0) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return default
    return x if math.isfinite(x) else default


def class_key(value: Any) -> str:
    """Clé texte stable d'une classe : 1, 1.0 et True donnent tous "1"."""
    try:
        f = float(value)
        if f.is_integer():
            return str(int(f))
    except (TypeError, ValueError):
        pass
    return str(value)


# ---------------------------------------------------------------------------
# Construction des jeux d'entraînement
# ---------------------------------------------------------------------------
def build_simulated_training_frame(drift_level: float, n: int = 600, fraud_rate: float = 0.06):
    """Jeu d'entraînement simulé (aucun dataset importé) — pour les démonstrations."""
    reference = get_reference_dataset(n=n // 2)
    current = get_current_batch(n=n // 2, drift_level=drift_level)
    df = pd.concat([reference, current], ignore_index=True)

    rng = np.random.default_rng(123)
    base_fraud_prob = fraud_rate + 0.15 * (df["purchase_hour"] > 21).astype(float)
    base_fraud_prob += 0.1 * (df["device_type"] == "mobile").astype(float)
    y = pd.Series(rng.binomial(1, np.clip(base_fraud_prob, 0, 0.9)), name="target")

    X = pd.get_dummies(df, columns=["device_type", "card_type"], drop_first=True).astype(float)
    parts = {
        "numeric": df[["TransactionAmt", "purchase_hour"]],
        "categorical": df[["device_type", "card_type"]].astype(str),
        "class_labels": {"0": "0", "1": "1"},
        "target_column": "target",
    }
    return X, y, parts


def resolve_target(df: pd.DataFrame, target_column: Optional[str]) -> tuple[str, Optional[str]]:
    """
    Détermine la colonne cible. Si elle n'est pas précisée (ou n'existe plus),
    on la devine par son nom, sinon on prend la dernière colonne qui ressemble
    à une classe (2 à 20 valeurs distinctes), sinon la dernière colonne.
    Retourne (colonne, note éventuelle).
    """
    if target_column and target_column in df.columns:
        return target_column, None
    guessed = guess_target_column(df)
    if guessed:
        return guessed, f"Colonne cible non précisée : « {guessed} » choisie automatiquement."
    if df.shape[1] < 2:
        raise TrainingError(
            "Le fichier ne contient qu'une seule colonne : il faut au moins une variable et une colonne à prédire."
        )
    for c in reversed(df.columns):
        if 2 <= df[c].nunique(dropna=True) <= MAX_TARGET_CLASSES:
            return c, f"Colonne cible non précisée : « {c} » choisie automatiquement (dernière colonne à peu de valeurs)."
    last = df.columns[-1]
    return last, f"Colonne cible non précisée : la dernière colonne « {last} » a été choisie automatiquement."


def _bin_continuous_target(y_raw: pd.Series, name: str):
    """Cible continue -> 2 classes (au-dessus / en dessous de la médiane, à défaut de la moyenne)."""
    values = y_raw.astype(float)
    threshold = values.median()
    high = values > threshold
    if not 0 < high.sum() < len(values):
        threshold = values.mean()
        high = values > threshold
    labels = {"0": f"≤ {threshold:.4g}", "1": f"> {threshold:.4g}"}
    note = (
        f"La colonne cible « {name} » est continue : elle a été transformée en 2 classes "
        f"(au-dessus / en dessous de {threshold:.4g})."
    )
    return high.astype(int).to_numpy(), labels, note


def _encode_features(X: pd.DataFrame, strict: bool):
    """
    Encode les variables explicatives.
    strict=True  : écarte les identifiants et les textes libres (cas normal) ;
    strict=False : mode de secours, garde toutes les colonnes et regroupe les
                   modalités rares en « autre » (utilisé si le mode strict ne
                   laisse aucune variable).
    """
    if strict and len(X) >= MIN_ROWS_FOR_ID_FILTER:
        X = X.drop(columns=[c for c in X.columns if looks_like_id(X[c])])

    numeric_cols = X.select_dtypes(include=["number", "bool"]).columns.tolist()
    categorical_cols = [c for c in X.columns if c not in numeric_cols]
    if strict:
        usable_categorical = [c for c in categorical_cols if X[c].nunique(dropna=True) <= MAX_CATEGORY_CARDINALITY]
    else:
        usable_categorical = categorical_cols

    X_numeric = X[numeric_cols].apply(pd.to_numeric, errors="coerce").astype(float)
    X_numeric = X_numeric.replace([np.inf, -np.inf], np.nan)
    X_numeric = X_numeric.fillna(X_numeric.median()).fillna(0.0)

    if usable_categorical:
        # Les valeurs manquantes deviennent une modalité "nan" (comportement identique
        # quelle que soit la version de pandas, qui diffère sur astype(str) et les NaN).
        cat_df = X[usable_categorical].astype(object).fillna("nan").astype(str)
        if not strict:
            for c in cat_df.columns:
                if cat_df[c].nunique() > MAX_CATEGORY_CARDINALITY:
                    top = cat_df[c].value_counts().index[:MAX_CATEGORY_CARDINALITY]
                    cat_df[c] = cat_df[c].where(cat_df[c].isin(top), "autre")
        X_categorical = pd.get_dummies(cat_df, columns=usable_categorical, drop_first=True).astype(float)
    else:
        cat_df = pd.DataFrame(index=X.index)
        X_categorical = pd.DataFrame(index=X.index)

    X_final = pd.concat([X_numeric, X_categorical], axis=1).reset_index(drop=True)
    return X_numeric, cat_df, X_final


def _encode_target(y_raw: pd.Series, target_col: str):
    """Encode la cible en classes entières. Retourne (valeurs, libellés, notes)."""
    notes: list[str] = []

    if pd.api.types.is_bool_dtype(y_raw):
        return y_raw.astype(int).to_numpy(), {"0": "False", "1": "True"}, notes

    if pd.api.types.is_numeric_dtype(y_raw):
        if y_raw.nunique() <= MAX_TARGET_CLASSES:
            return y_raw.to_numpy(), {class_key(c): class_key(c) for c in sorted(y_raw.unique())}, notes
        # Cible continue : découpée en classes par quantiles (faible / moyen / élevé).
        codes = pd.qcut(y_raw, q=3, labels=False, duplicates="drop").astype(int)
        k = int(codes.max()) + 1
        names = {1: ["unique"], 2: ["bas", "haut"], 3: ["faible", "moyen", "élevé"]}[k]
        notes.append(
            f"La cible '{target_col}' est continue ({y_raw.nunique()} valeurs distinctes) : "
            f"elle a été découpée automatiquement en {k} classe(s) par quantiles."
        )
        return codes.to_numpy(), {str(i): n for i, n in enumerate(names)}, notes

    y_str = y_raw.astype(str)
    if y_str.nunique() > MAX_TARGET_CLASSES:
        keep = y_str.value_counts().index[: MAX_TARGET_CLASSES - 1]
        y_str = y_str.where(y_str.isin(keep), "autres")
        notes.append(
            f"La cible '{target_col}' a beaucoup de valeurs : les {MAX_TARGET_CLASSES - 1} plus "
            "fréquentes sont gardées, les autres regroupées en « autres »."
        )
    codes, uniques = pd.factorize(y_str, sort=True)
    return codes, {str(i): str(u) for i, u in enumerate(uniques)}, notes


def build_real_training_frame(df: pd.DataFrame, target_column: Optional[str]):
    """
    Préparation générique d'un vrai dataset, conçue pour ne JAMAIS échouer sur
    la taille ou la qualité des données : valeurs manquantes imputées,
    identifiants écartés, catégories encodées, cible continue ou trop
    variée regroupée en classes. Retourne (X, y, parts) ; `parts` garde les
    colonnes brutes pour ré-encoder une saisie utilisateur à la prédiction.

    Seuls cas d'échec (réellement impossibles) : aucune colonne cible
    identifiable, aucune ligne avec une cible renseignée, aucune variable
    explicative dans le fichier.
    """
    df = df.copy()
    df.columns = [str(c) for c in df.columns]

    if len(df) > MAX_TRAINING_ROWS:
        df = df.sample(n=MAX_TRAINING_ROWS, random_state=42).reset_index(drop=True)

    target_col = target_column or guess_target_column(df)
    if not target_col or target_col not in df.columns:
        raise TrainingError(
            "Impossible de déterminer la colonne cible de ce dataset. "
            "Renseigne-la explicitement lors de l'import (champ 'Colonne cible')."
        )

    # Les lignes sans valeur cible ne peuvent pas servir à l'entraînement.
    df = df[df[target_col].notna()]
    if pd.api.types.is_numeric_dtype(df[target_col]) and not pd.api.types.is_bool_dtype(df[target_col]):
        df = df[np.isfinite(df[target_col].astype(float))]
    df = df.reset_index(drop=True)
    if df.empty:
        raise TrainingError(f"La colonne cible '{target_col}' ne contient aucune valeur exploitable.")

    y_raw = df[target_col]
    X = df.drop(columns=[target_col])

    X_numeric, cat_df, X_final = _encode_features(X, strict=True)
    if X_final.shape[1] == 0:
        X_numeric, cat_df, X_final = _encode_features(X, strict=False)  # mode de secours
    if X_final.shape[1] == 0:
        raise TrainingError("Le fichier ne contient aucune variable explicative en dehors de la colonne cible.")

    y_values, class_labels, notes = _encode_target(y_raw, target_col)
    y = pd.Series(y_values, name="target").reset_index(drop=True)

    parts = {
        "numeric": X_numeric.reset_index(drop=True),
        "categorical": cat_df.reset_index(drop=True),
        "class_labels": class_labels,
        "target_column": target_col,
        "notes": notes,
    }
    return X_final, y, parts


def split_train_test(X: pd.DataFrame, y: pd.Series):
    """
    Sépare entraînement / test sans jamais échouer, quelle que soit la taille
    des données ou le déséquilibre des classes. Si l'échantillon est trop
    petit pour réserver un jeu de test fiable, le modèle est évalué sur ses
    propres données d'entraînement (indiqué dans la description renvoyée).
    Retourne (X_train, X_test, y_train, y_test, description).
    """
    n = len(y)
    counts = y.value_counts()
    if n >= MIN_ROWS_FOR_TEST_SPLIT:
        test_size = 0.25
        stratify = y if (counts.min() >= 2 and round(n * test_size) >= len(counts)) else None
        try:
            X_tr, X_te, y_tr, y_te = train_test_split(
                X, y, test_size=test_size, random_state=42, stratify=stratify
            )
            if y_tr.nunique() == y.nunique():
                return X_tr, X_te, y_tr, y_te, "jeu de test (25 % des données)"
        except ValueError:
            pass
    return X, X, y, y, "données d'entraînement (échantillon trop petit pour réserver un jeu de test)"


def fit_and_evaluate(X: pd.DataFrame, y: pd.Series, n_estimators: int = 150, max_depth: int = 8, min_samples_leaf: int = 1):
    """
    Entraîne un RandomForest et calcule ses métriques, sans jamais refuser un
    jeu de données pour sa taille ou son déséquilibre. Retourne
    (modèle, métriques, notes) ; `notes` liste les adaptations faites
    (échantillon trop petit, une seule classe, classe très rare...).
    """
    classes = sorted(y.unique().tolist())
    n_classes = len(classes)
    X_tr, X_te, y_tr, y_te, evaluation = split_train_test(X, y)

    notes: list[str] = []
    if not evaluation.startswith("jeu de test"):
        notes.append("Échantillon très petit : le modèle est évalué sur ses propres données d'entraînement (métriques optimistes).")
    if n_classes < 2:
        notes.append("Une seule classe est présente dans les données : le modèle prédira toujours cette classe.")
    elif int(y.value_counts().min()) < 8:
        notes.append("Classe minoritaire très rare (moins de 8 exemples) : métriques peu fiables.")

    model = RandomForestClassifier(
        n_estimators=n_estimators, max_depth=max_depth, min_samples_leaf=min_samples_leaf,
        class_weight="balanced", random_state=42,
    ).fit(X_tr, y_tr)
    y_pred = model.predict(X_te)

    # Binaire : la classe positive est la seconde (la plus grande) ; sinon moyenne pondérée.
    average = "binary" if n_classes == 2 else "weighted"
    extra = {"pos_label": classes[1]} if n_classes == 2 else {}
    metrics = {
        "accuracy": round(float(accuracy_score(y_te, y_pred)), 4),
        "f1": round(float(f1_score(y_te, y_pred, average=average, zero_division=0, **extra)), 4),
        "recall": round(float(recall_score(y_te, y_pred, average=average, zero_division=0, **extra)), 4),
        "precision": round(float(precision_score(y_te, y_pred, average=average, zero_division=0, **extra)), 4),
    }
    return model, metrics, notes


# ---------------------------------------------------------------------------
# Comparaison de plusieurs algorithmes, avec choix de la méthode d'équilibrage
# ---------------------------------------------------------------------------
ALGORITHMS = {
    "random_forest": "Random Forest",
    "logistic_regression": "Régression logistique",
    "gradient_boosting": "Gradient Boosting",
}
BALANCING_METHODS = {
    "none": "Aucun équilibrage",
    "class_weight": "Pondération des classes",
    "oversampling": "Sur-échantillonnage",
    "undersampling": "Sous-échantillonnage",
}
DEFAULT_ALGORITHMS = ["random_forest"]
DEFAULT_BALANCING = "class_weight"
MAX_BALANCED_ROWS = 20000


def normalize_training_options(algorithms, balancing) -> tuple[list[str], str]:
    """Nettoie le choix de l'utilisateur : ignore les valeurs inconnues, retire les doublons."""
    chosen: list[str] = []
    for a in (algorithms or []):
        if a in ALGORITHMS and a not in chosen:
            chosen.append(a)
    return (chosen or list(DEFAULT_ALGORITHMS)), (balancing if balancing in BALANCING_METHODS else DEFAULT_BALANCING)


def balance_training_data(X: pd.DataFrame, y: pd.Series, method: str):
    """
    Rééquilibre les classes du jeu d'ENTRAÎNEMENT uniquement (le jeu de test garde sa
    distribution réelle, sinon les métriques seraient faussées).
    - oversampling  : duplique au hasard les exemples des classes rares jusqu'à la taille de la plus grande ;
    - undersampling : réduit au hasard les classes majoritaires (au moins 20 exemples par classe si possible) ;
    - class_weight  : aucune modification des données (la pondération est faite par l'algorithme).
    """
    if method not in ("oversampling", "undersampling"):
        return X, y
    counts = y.value_counts()
    if len(counts) < 2:
        return X, y

    rng = np.random.default_rng(42)
    y_arr = y.to_numpy()
    if method == "oversampling":
        target = int(counts.max())
        if target * len(counts) > MAX_BALANCED_ROWS:
            target = max(MAX_BALANCED_ROWS // len(counts), 1)
    else:
        floor = max(int(counts.min()), 20)

    picked = []
    for cls, size in counts.items():
        idx = np.flatnonzero(y_arr == cls)
        if method == "oversampling":
            picked.append(rng.choice(idx, size=target, replace=size < target))
        else:
            picked.append(rng.choice(idx, size=min(int(size), floor), replace=False))
    chosen = rng.permutation(np.concatenate(picked))
    return X.iloc[chosen].reset_index(drop=True), y.iloc[chosen].reset_index(drop=True)


def _build_estimator(algorithm: str, balancing: str):
    class_weight = "balanced" if balancing == "class_weight" else None
    if algorithm == "random_forest":
        return RandomForestClassifier(
            n_estimators=150, max_depth=8, class_weight=class_weight, random_state=42, n_jobs=1
        )
    if algorithm == "logistic_regression":
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=1000, class_weight=class_weight, random_state=42),
        )
    if algorithm == "gradient_boosting":
        return GradientBoostingClassifier(n_estimators=100, max_depth=3, random_state=42)
    raise ValueError(f"Algorithme inconnu : {algorithm}")


def feature_importances(model):
    """Importance des variables, quel que soit l'algorithme (arbres, ou coefficients pour la régression)."""
    est = model.steps[-1][1] if hasattr(model, "steps") else model
    if hasattr(est, "feature_importances_"):
        return est.feature_importances_
    if hasattr(est, "coef_"):
        imp = np.abs(est.coef_).mean(axis=0)
        total = imp.sum()
        return imp / total if total > 0 else imp
    return None


def _evaluate(model, X_te: pd.DataFrame, y_te: pd.Series, classes: list, class_labels: dict | None = None):
    """Retourne (métriques, matrice de confusion). Lignes = classe réelle, colonnes = classe prédite."""
    labels = class_labels or {}
    n_classes = len(classes)
    y_pred = model.predict(X_te)
    average = "binary" if n_classes == 2 else "weighted"
    extra = {"pos_label": classes[1]} if n_classes == 2 else {}
    auc = None
    if n_classes == 2 and y_te.nunique() == 2:
        try:
            auc = round(float(roc_auc_score(y_te, model.predict_proba(X_te)[:, 1])), 4)
        except Exception:
            auc = None
    metrics = {
        "accuracy": round(float(accuracy_score(y_te, y_pred)), 4),
        "precision": round(float(precision_score(y_te, y_pred, average=average, zero_division=0, **extra)), 4),
        "recall": round(float(recall_score(y_te, y_pred, average=average, zero_division=0, **extra)), 4),
        "f1": round(float(f1_score(y_te, y_pred, average=average, zero_division=0, **extra)), 4),
        "roc_auc": auc,
    }
    confusion = {
        "labels": [str(labels.get(class_key(c), class_key(c))) for c in classes],
        "matrix": confusion_matrix(y_te, y_pred, labels=classes).tolist(),
    }
    return metrics, confusion


def train_and_compare(
    X: pd.DataFrame, y: pd.Series, algorithms=None, balancing=None, progress=None, class_labels=None,
) -> dict:
    """
    Entraîne chaque algorithme choisi sur le même jeu d'entraînement (rééquilibré selon la
    méthode choisie), les évalue sur le même jeu de test, et retient le meilleur (F1 le plus
    élevé, puis accuracy). `progress(pourcentage, libellé)` est appelé au fil de l'avancement
    (de 30 % à 90 %). Un algorithme qui échoue est signalé sans arrêter les autres.
    """
    algorithms, balancing = normalize_training_options(algorithms, balancing)

    def report(pct: float, label: str) -> None:
        if progress:
            progress(int(pct), label)

    classes = sorted(y.unique().tolist())
    n_classes = len(classes)
    X_tr, X_te, y_tr, y_te, evaluation = split_train_test(X, y)

    notes: list[str] = []
    if not evaluation.startswith("jeu de test"):
        notes.append("Échantillon très petit : les modèles sont évalués sur leurs propres données d'entraînement (métriques optimistes).")
    if n_classes < 2:
        notes.append("Une seule classe est présente dans les données : le modèle prédira toujours cette classe.")
    elif int(y.value_counts().min()) < 8:
        notes.append("Classe minoritaire très rare (moins de 8 exemples) : métriques peu fiables.")

    report(30, f"Équilibrage : {BALANCING_METHODS[balancing]}")
    X_fit, y_fit = balance_training_data(X_tr, y_tr, balancing)

    results: list[dict] = []
    fitted: dict[str, Any] = {}
    n = len(algorithms)
    for i, algo in enumerate(algorithms):
        label = ALGORITHMS[algo]
        report(30 + 60 * i / n, f"Entraînement : {label} ({i + 1}/{n})")
        started = time.perf_counter()
        try:
            model = _build_estimator(algo, balancing)
            fit_kwargs = {}
            if algo == "gradient_boosting" and balancing == "class_weight" and n_classes > 1:
                fit_kwargs["sample_weight"] = compute_sample_weight("balanced", y_fit)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model.fit(X_fit, y_fit, **fit_kwargs)
            metrics, confusion = _evaluate(model, X_te, y_te, classes, class_labels)
            results.append({
                "algorithm": algo, "label": label, "metrics": metrics, "confusion_matrix": confusion,
                "seconds": round(time.perf_counter() - started, 2),
            })
            fitted[algo] = model
        except Exception as exc:  # un algorithme en échec n'empêche pas les autres
            results.append({"algorithm": algo, "label": label, "error": str(exc)[:200]})
        report(30 + 60 * (i + 1) / n, f"{label} terminé")

    ok = [r for r in results if "metrics" in r]
    if not ok:
        raise TrainingError("Aucun algorithme n'a pu être entraîné : " + " | ".join(
            f"{r['label']} : {r.get('error', '?')}" for r in results))
    best = max(ok, key=lambda r: (r["metrics"]["f1"], r["metrics"]["accuracy"]))
    best["best"] = True
    best_metrics = {k: best["metrics"][k] for k in ("accuracy", "f1", "recall", "precision")}

    return {
        "model": fitted[best["algorithm"]],
        "metrics": best_metrics,
        "best": best["algorithm"],
        "balancing": balancing,
        "algorithms": algorithms,
        "results": results,
        "evaluation": evaluation,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Métadonnées du modèle (embarquées avec lui, pour l'inférence)
# ---------------------------------------------------------------------------
def build_meta(
    parts: dict,
    X_final: pd.DataFrame,
    importances=None,
    domain: Optional[str] = None,
    dataset_name: Optional[str] = None,
) -> dict:
    numeric_df: pd.DataFrame = parts["numeric"]
    categorical_df: pd.DataFrame = parts["categorical"]
    imp = dict(zip(X_final.columns, importances)) if importances is not None else {}

    numeric = []
    for c in numeric_df.columns:
        s = pd.to_numeric(numeric_df[c], errors="coerce")
        numeric.append({
            "name": str(c),
            "median": _f(s.median()),
            "min": _f(s.min()),
            "max": _f(s.max()),
            "importance": _f(imp.get(c, 0.0)),
        })

    categorical = []
    for c in categorical_df.columns:
        values = categorical_df[c].astype(str)
        uniques = sorted(values.unique().tolist())
        mode = values.mode().iloc[0] if len(values) else uniques[0]
        # get_dummies(drop_first=True) retire la première modalité (ordre trié)
        dummy_map = {v: f"{c}_{v}" for v in uniques[1:] if f"{c}_{v}" in X_final.columns}
        categorical.append({
            "name": str(c),
            "values": uniques,
            "mode": str(mode),
            "dummy_map": dummy_map,
            "importance": sum(_f(imp.get(col, 0.0)) for col in dummy_map.values()),
        })

    ranked = sorted(numeric + categorical, key=lambda f: f["importance"], reverse=True)
    form_features = [f["name"] for f in ranked[:MAX_FORM_FEATURES]]

    return {
        "version": META_VERSION,
        "feature_columns": [str(c) for c in X_final.columns],
        "numeric": numeric,
        "categorical": categorical,
        "form_features": form_features,
        "class_labels": parts.get("class_labels", {}),
        "target_column": parts.get("target_column"),
        "domain": domain,
        "dataset_name": dataset_name,
    }


# ---------------------------------------------------------------------------
# Inférence
# ---------------------------------------------------------------------------
def baseline_values(meta: dict) -> dict[str, Any]:
    base: dict[str, Any] = {f["name"]: f["median"] for f in meta["numeric"]}
    base.update({f["name"]: f["mode"] for f in meta["categorical"]})
    return base


def encode_input(meta: dict, payload: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Transforme une saisie brute en une ligne alignée sur les colonnes du
    modèle. Les variables absentes prennent leur valeur typique. Retourne
    (ligne, valeurs effectivement utilisées par variable brute).
    """
    row = {c: 0.0 for c in meta["feature_columns"]}
    used: dict[str, Any] = {}

    for f in meta["numeric"]:
        name = f["name"]
        raw = payload.get(name)
        if raw is None or raw == "":
            value = float(f["median"])
        else:
            try:
                value = float(raw)
            except (TypeError, ValueError):
                raise InputError(f"La variable « {name} » doit être un nombre.")
            if not math.isfinite(value):
                raise InputError(f"La variable « {name} » doit être un nombre fini.")
        row[name] = value
        used[name] = value

    for f in meta["categorical"]:
        name = f["name"]
        raw = payload.get(name)
        value = f["mode"] if raw is None or raw == "" else str(raw)
        if value not in f["values"]:
            options = ", ".join(f["values"][:10])
            raise InputError(f"Valeur « {value} » inconnue pour « {name} ». Valeurs possibles : {options}.")
        for modality, column in f["dummy_map"].items():
            row[column] = 1.0 if modality == value else 0.0
        used[name] = value

    return pd.DataFrame([row], columns=meta["feature_columns"]), used


def predict_and_explain(model, meta: dict, payload: dict[str, Any], top_n: int = 5) -> dict[str, Any]:
    """
    Prédit pour une saisie et explique le résultat par perturbation.
    Pour un problème binaire, le "score" est la probabilité de la classe
    positive (seconde classe) ; sinon, celle de la classe prédite.
    """
    row, used = encode_input(meta, payload)
    base = baseline_values(meta)

    rows = [row]
    names: list[str] = []
    for name, value in used.items():
        if value == base[name]:
            continue  # déjà "typique" : contribution nulle par construction
        alternative = dict(used)
        alternative[name] = base[name]
        rows.append(encode_input(meta, alternative)[0])
        names.append(name)

    proba = model.predict_proba(pd.concat(rows, ignore_index=True))
    classes = list(model.classes_)

    first = proba[0]
    predicted_idx = int(np.argmax(first))
    target_idx = 1 if len(classes) == 2 else predicted_idx
    scores = proba[:, target_idx]

    contributions = {n: float(scores[0] - scores[i + 1]) for i, n in enumerate(names)}
    top = sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)
    explanation = {k: round(v, 4) for k, v in top[:top_n] if abs(v) >= 1e-4}

    return {
        "predicted_key": class_key(classes[predicted_idx]),
        "scored_key": class_key(classes[target_idx]),
        "n_classes": len(classes),
        "probability": float(scores[0]),
        "contributions": explanation,
        "inputs": used,
    }


def _is_fraud_setting(meta: dict, scored_key: str, n_classes: int) -> bool:
    if n_classes != 2 or meta.get("domain") != "finance":
        return False
    label = meta.get("class_labels", {}).get(scored_key, scored_key)
    return str(label).strip().lower() in _POSITIVE_TOKENS


def label_prediction(meta: dict, result: dict[str, Any]) -> tuple[str, str]:
    """
    Retourne (prediction, libellé du score). Pour une détection de fraude
    binaire : "legitime" / "suspecte" ; sinon, le libellé de la classe prédite.
    """
    labels = meta.get("class_labels", {})
    scored_key = result["scored_key"]
    predicted_key = result["predicted_key"]

    if _is_fraud_setting(meta, scored_key, result["n_classes"]):
        prediction = "suspecte" if predicted_key == scored_key else "legitime"
        return prediction, "Score de risque (probabilité de fraude)"

    prediction = str(labels.get(predicted_key, predicted_key))
    scored_label = labels.get(scored_key, scored_key)
    return prediction, f"Probabilité de la classe « {scored_label} »"


def describe_fields(meta: dict) -> list[dict[str, Any]]:
    """Champs du formulaire de prédiction (les variables les plus importantes)."""
    by_name = {f["name"]: f for f in meta["numeric"]}
    by_name.update({f["name"]: f for f in meta["categorical"]})
    fields = []
    for name in meta.get("form_features", []):
        f = by_name.get(name)
        if f is None:
            continue
        if "median" in f:
            fields.append({
                "name": name, "type": "number",
                "default": round(f["median"], 4), "min": round(f["min"], 4), "max": round(f["max"], 4),
            })
        else:
            fields.append({"name": name, "type": "category", "options": f["values"], "default": f["mode"]})
    return fields
