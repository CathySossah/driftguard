"""
Test unitaire de la préparation des variables et de l'inférence réelle.
Ne dépend ni de FastAPI, ni de MLflow, ni de la base de données :
    python test_ml_features.py
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from app.services import ml_features as mf

print("=== 1. Jeu simulé : l'encodage d'une saisie reproduit exactement celui de l'entraînement ===")
X, y, parts = mf.build_simulated_training_frame(drift_level=0.0, n=4000)
model = RandomForestClassifier(n_estimators=100, max_depth=8, class_weight="balanced", random_state=42).fit(X, y)
meta = mf.build_meta(parts, X, importances=model.feature_importances_, domain="finance", dataset_name="démo")

raw = pd.concat([parts["numeric"], parts["categorical"]], axis=1)
for i in np.random.default_rng(0).choice(len(raw), 25, replace=False):
    payload = raw.iloc[i].to_dict()
    row, _ = mf.encode_input(meta, payload)
    assert np.allclose(row.iloc[0].to_numpy(dtype=float), X.iloc[i].to_numpy(dtype=float)), f"ligne {i} différente"
print("   OK (25 lignes comparées)")

print("=== 2. La prédiction réagit aux entrées (heure tardive + mobile => risque plus élevé) ===")
rng0 = np.random.default_rng(7)
n0 = 3000
d = pd.DataFrame({
    "TransactionAmt": rng0.gamma(2, 50, n0),
    "purchase_hour": rng0.integers(0, 24, n0).astype(float),
    "device_type": rng0.choice(["mobile", "desktop"], n0),
})
fraud_p = 0.05 + 0.6 * (d.purchase_hour > 21) + 0.2 * ((d.device_type == "mobile") & (d.purchase_hour > 21))
d["isFraud"] = rng0.binomial(1, np.clip(fraud_p, 0, 0.95))
X, y, parts = mf.build_real_training_frame(d, "isFraud")
assert "TransactionAmt" in X.columns, "une variable continue ne doit pas être prise pour un identifiant"
model = RandomForestClassifier(n_estimators=100, max_depth=8, class_weight="balanced", random_state=42).fit(X, y)
meta = mf.build_meta(parts, X, importances=model.feature_importances_, domain="finance", dataset_name="synthétique")

high = mf.predict_and_explain(model, meta, {"TransactionAmt": 100, "purchase_hour": 23, "device_type": "mobile"})
low = mf.predict_and_explain(model, meta, {"TransactionAmt": 100, "purchase_hour": 10, "device_type": "desktop"})
print("   risque élevé :", round(high["probability"], 3), high["contributions"])
print("   risque faible:", round(low["probability"], 3), low["contributions"])
assert 0 <= high["probability"] <= 1 and 0 <= low["probability"] <= 1
assert high["probability"] > low["probability"] + 0.15
assert high["contributions"].get("purchase_hour", 0) > 0

print("=== 3. Libellés (domaine finance, binaire) ===")
pred, lab = mf.label_prediction(meta, high)
print("  ", pred, "|", lab)
assert pred == "suspecte" and mf.label_prediction(meta, low)[0] == "legitime"

print("=== 4. Saisies invalides ===")
for bad in ({"purchase_hour": "abc"}, {"device_type": "fax"}, {"TransactionAmt": float("inf")}):
    try:
        mf.encode_input(meta, bad)
        raise SystemExit(f"devrait échouer : {bad}")
    except mf.InputError as e:
        print("   refusé :", e)

print("=== 5. Champs du formulaire ===")
fields = mf.describe_fields(meta)
assert 1 <= len(fields) <= mf.MAX_FORM_FEATURES
assert {f["type"] for f in fields} <= {"number", "category"}
assert fields[0]["name"] == "purchase_hour"  # la variable la plus importante vient en premier
print("  ", [f["name"] for f in fields])

print("=== 6. Vrai dataset : valeurs manquantes, identifiants, cible texte ===")
rng = np.random.default_rng(1)
n = 400
df = pd.DataFrame({
    "TransactionID": np.arange(n),
    "amount": np.where(rng.random(n) < 0.1, np.nan, rng.gamma(2, 50, n)),
    "channel": rng.choice(["app", "ussd", None], n),
    "label": rng.choice(["fraud", "legit"], n, p=[0.2, 0.8]),
})
df.loc[:4, "label"] = None  # lignes sans cible : doivent être ignorées
X2, y2, parts2 = mf.build_real_training_frame(df, "label")
assert "TransactionID" not in X2.columns and len(X2) == n - 5
assert not X2.isna().any().any()
assert parts2["class_labels"] == {"0": "fraud", "1": "legit"}, parts2["class_labels"]
m2 = RandomForestClassifier(n_estimators=20, random_state=0).fit(X2, y2)
meta2 = mf.build_meta(parts2, X2, importances=m2.feature_importances_, domain="sante", dataset_name="t")
res2 = mf.predict_and_explain(m2, meta2, {"amount": 80, "channel": "ussd"})
p2, _ = mf.label_prediction(meta2, res2)
print("   prédiction :", p2, "| probabilité :", round(res2["probability"], 3))
assert p2 in ("fraud", "legit")

print("=== 7. Cible numérique 0/1 en finance -> legitime/suspecte ; cible continue refusée ===")
df3 = pd.DataFrame({"a": rng.normal(size=n), "isFraud": rng.choice([0, 1], n, p=[0.8, 0.2])})
X3, y3, parts3 = mf.build_real_training_frame(df3, None)  # cible devinée
m3 = RandomForestClassifier(n_estimators=20, random_state=0).fit(X3, y3)
meta3 = mf.build_meta(parts3, X3, importances=m3.feature_importances_, domain="finance")
r3 = mf.predict_and_explain(m3, meta3, {"a": 0.5})
assert mf.label_prediction(meta3, r3)[0] in ("legitime", "suspecte")
df4 = pd.DataFrame({"a": rng.normal(size=n), "rendement": rng.normal(size=n)})
X4, y4, parts4 = mf.build_real_training_frame(df4, "rendement")
assert y4.nunique() == 3 and parts4["notes"], "une cible continue doit être découpée en classes, pas refusée"
print("   cible continue acceptée :", parts4["notes"][0][:80], "...")

print("=== 8. Aucun dataset ne doit faire échouer l'entraînement (petit, déséquilibré, atypique) ===")


def train_on(df, target, label):
    X_, y_, parts_ = mf.build_real_training_frame(df, target)
    model_, metrics_, notes_ = mf.fit_and_evaluate(X_, y_)
    meta_ = mf.build_meta(parts_, X_, importances=model_.feature_importances_, domain="finance")
    res_ = mf.predict_and_explain(model_, meta_, {})
    mf.label_prediction(meta_, res_)
    print(f"   {label:<42} OK  classes={y_.nunique()}  rows={len(X_):<4} {notes_[:1]}")


r8 = np.random.default_rng(3)
# 1 seule fraude sur 50 lignes (le cas qui échouait avant : « données insuffisantes »)
train_on(pd.DataFrame({"amount": r8.gamma(2, 50, 50), "hour": r8.integers(0, 23, 50), "is_fraud": [0] * 49 + [1]}), "is_fraud", "1 fraude sur 50 lignes")
# une seule classe
train_on(pd.DataFrame({"a": r8.normal(size=12), "y": [1] * 12}), "y", "une seule classe")
# 3 lignes seulement
train_on(pd.DataFrame({"a": [1.0, 2.0, 3.0], "y": [0, 1, 0]}), "y", "3 lignes")
# 1 seule ligne
train_on(pd.DataFrame({"a": [1.0], "y": [1]}), "y", "1 ligne")
# classes binaires non 0/1
train_on(pd.DataFrame({"a": r8.normal(size=60), "y": r8.choice([3, 5], 60)}), "y", "classes {3, 5}")
# cible texte avec beaucoup de valeurs
train_on(pd.DataFrame({"a": r8.normal(size=300), "y": [f"culture_{i % 45}" for i in range(300)]}), "y", "45 classes texte")
# uniquement des colonnes texte très variées + identifiant
train_on(pd.DataFrame({"id": np.arange(300), "nom": [f"n{i}" for i in range(300)], "y": r8.choice([0, 1], 300)}), "y", "identifiants et texte libre seulement")
# valeurs manquantes partout
train_on(pd.DataFrame({"a": [np.nan] * 40, "b": r8.choice(["x", None], 40), "y": r8.choice([0, 1], 40)}), "y", "colonnes presque vides")

print("=== 9. Modèle de démonstration pré-entraîné (construit sans MLflow) ===")
import pathlib
import tempfile

import joblib

from app import demo_model

with tempfile.TemporaryDirectory() as tmp:
    bundle_path = pathlib.Path(tmp) / "demo_model.joblib"
    demo_model.build(bundle_path)
    bundle = joblib.load(bundle_path)
night = mf.predict_and_explain(bundle["model"], bundle["meta"],
                               {"TransactionAmt": 80, "purchase_hour": 2, "device_type": "mobile", "card_type": "visa"})
day = mf.predict_and_explain(bundle["model"], bundle["meta"],
                             {"TransactionAmt": 80, "purchase_hour": 11, "device_type": "desktop", "card_type": "amex"})
print("   nuit/mobile :", round(night["probability"], 3), "| jour/desktop :", round(day["probability"], 3))
assert night["probability"] > day["probability"] + 0.3

print("=== 10. Comparaison d'algorithmes et équilibrage ===")
r10 = np.random.default_rng(11)
n10 = 1500
d10 = pd.DataFrame({"amt": r10.gamma(2, 50, n10), "hour": r10.integers(0, 24, n10), "dev": r10.choice(["m", "d"], n10)})
d10["fraud"] = r10.binomial(1, np.clip(0.02 + 0.5 * (d10.hour > 21) + 0.2 * (d10.amt > 200), 0, 0.9))
X10, y10, parts10 = mf.build_real_training_frame(d10, "fraud")

over_X, over_y = mf.balance_training_data(X10, y10, "oversampling")
assert over_y.value_counts().nunique() == 1 and len(over_y) > len(y10), "sur-échantillonnage : classes à égalité"
under_X, under_y = mf.balance_training_data(X10, y10, "undersampling")
assert under_y.value_counts().nunique() == 1 and len(under_y) < len(y10), "sous-échantillonnage : classes à égalité"
same_X, same_y = mf.balance_training_data(X10, y10, "class_weight")
assert len(same_y) == len(y10)

for balancing in mf.BALANCING_METHODS:
    steps = []
    out = mf.train_and_compare(X10, y10, list(mf.ALGORITHMS), balancing, progress=lambda p, l: steps.append(p))
    assert len(out["results"]) == 3 and all("metrics" in r for r in out["results"])
    assert sum(1 for r in out["results"] if r.get("best")) == 1
    assert steps[0] == 30 and steps[-1] == 90 and steps == sorted(steps), steps
    assert set(out["metrics"]) == {"accuracy", "f1", "recall", "precision"}
    print(f"   {balancing:<14} meilleur = {mf.ALGORITHMS[out['best']]:<22}",
          {r["label"]: r["metrics"]["f1"] for r in out["results"]})

# tout algorithme doit pouvoir servir à la prédiction réelle (probabilités + explication)
for algo in mf.ALGORITHMS:
    o = mf.train_and_compare(X10, y10, [algo], "class_weight")
    m10 = mf.build_meta(parts10, X10, importances=mf.feature_importances(o["model"]), domain="finance")
    res10 = mf.predict_and_explain(o["model"], m10, {"amt": 300, "hour": 23, "dev": "m"})
    assert 0 <= res10["probability"] <= 1
assert mf.normalize_training_options(["inconnu", "random_forest", "random_forest"], "bizarre") == (["random_forest"], "class_weight")

print("\n✅ test_ml_features : OK")
