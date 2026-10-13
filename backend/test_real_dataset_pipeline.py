"""
Teste le pipeline COMPLET avec un vrai fichier CSV (structure inspirée
d'IEEE-CIS Fraud Detection, générée ici pour ne pas dépendre d'un compte
Kaggle dans cet environnement de test — mais le code exercé est exactement
celui qui traitera le vrai fichier une fois téléchargé et importé) :

import CSV -> configuration (colonne cible + temporelle) -> entraînement
initial réel -> monitoring réel sur données réelles -> alerte -> validation
-> ré-entraînement réel -> nouvelle version.
"""
import os
import shutil

os.environ["DATABASE_URL"] = "sqlite:///./test_real_pipeline.db"
os.environ["MLFLOW_TRACKING_URI"] = "sqlite:///./test_real_mlflow.db"
os.environ["DATASET_UPLOAD_DIR"] = "./test_real_uploads"

for f in ["test_real_pipeline.db", "test_real_mlflow.db"]:
    if os.path.exists(f):
        os.remove(f)
if os.path.exists("./test_real_uploads"):
    shutil.rmtree("./test_real_uploads")

import numpy as np
import pandas as pd

# --- Génère un CSV réaliste, structure proche d'IEEE-CIS Fraud Detection ---
# (TransactionDT = secondes depuis un point de référence, comme le vrai dataset)
rng = np.random.default_rng(7)
N_REF, N_CUR = 800, 300
N = N_REF + N_CUR

t = np.arange(N) * 3600  # une transaction par heure simulée
hour_of_day = (t // 3600) % 24
# Dérive volontaire dans la seconde moitié : les transactions tardives augmentent
drift_point = N_REF
purchase_hour = hour_of_day.copy().astype(float)
purchase_hour[drift_point:] = np.clip(rng.normal(22, 2, N - drift_point), 0, 23)

df = pd.DataFrame({
    "TransactionID": np.arange(100000, 100000 + N),
    "TransactionDT": t,
    "TransactionAmt": rng.gamma(2, 60, N).round(2),
    "ProductCD": rng.choice(["W", "C", "R", "H"], N, p=[0.6, 0.2, 0.1, 0.1]),
    "card_type": rng.choice(["visa", "mastercard", "amex"], N, p=[0.5, 0.35, 0.15]),
    "purchase_hour": purchase_hour,
    "P_emaildomain": rng.choice(["gmail.com", "yahoo.com", "outlook.com", "orange.sn"], N),
})
fraud_prob = 0.04 + 0.2 * (df["purchase_hour"] > 20).astype(float)
df["isFraud"] = rng.binomial(1, np.clip(fraud_prob, 0, 0.9))

csv_path = "/tmp/mini_ieee_cis_realistic.csv"
df.to_csv(csv_path, index=False)
print(f"CSV de test généré : {csv_path} ({len(df)} lignes, {len(df.columns)} colonnes)")

# --- Pipeline réel ---
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

client.post("/auth/register", json={
    "full_name": "Catherine Sossah", "email": "admin@driftguard.sn",
    "password": "testpass123", "role": "admin",
})
token = client.post("/auth/login", json={
    "email": "admin@driftguard.sn", "password": "testpass123",
}).json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

print("\n=== 1. Import du dataset réel ===")
with open(csv_path, "rb") as f:
    r = client.post(
        "/datasets/upload", headers=headers,
        files={"file": ("mini_ieee_cis_realistic.csv", f, "text/csv")},
        data={"name": "IEEE-CIS Fraud (extrait réaliste)", "domain": "finance"},
    )
print(r.status_code, r.json())
assert r.status_code == 201
dataset_id = r.json()["id"]
assert r.json()["target_column"] == "isFraud", "La cible aurait dû être devinée automatiquement"

print("\n=== 2. Configuration explicite (cible + colonne temporelle) ===")
r = client.patch(f"/datasets/{dataset_id}/configure", headers=headers, json={
    "target_column": "isFraud",
    "time_column": "TransactionDT",
})
print(r.status_code, r.json())
assert r.status_code == 200

print("\n=== 3. Entraînement du premier modèle sur les VRAIES données ===")
r = client.post(f"/models/train-initial/{dataset_id}", headers=headers)
print(r.status_code, r.json())
assert r.status_code == 202
job_id = r.json()["id"]

r = client.get("/retraining-jobs/", headers=headers)
job = next(j for j in r.json() if j["id"] == job_id)
print(job)
assert job["status"] == "reussi", f"Échec inattendu : {job.get('error_message')}"
new_model_id = job["new_model_version_id"]

print("\n=== 4. Vérifier la version de modèle créée ===")
r = client.get("/models/", headers=headers)
versions = r.json()
print(versions)
v1 = versions[0]
assert v1["version_number"] == 1
assert v1["status"] == "en_production"
assert v1["metrics"]["accuracy"] is not None
assert v1["mlflow_run_id"] is not None

print("\n=== 5. Vérifier dans MLflow que l'entraînement a bien utilisé les vraies données ===")
import mlflow
mlflow.set_tracking_uri("sqlite:///./test_real_mlflow.db")
run_data = mlflow.get_run(v1["mlflow_run_id"])
print("Params:", run_data.data.params)
assert "dataset réel" in run_data.data.params.get("data_source", ""), "L'entraînement n'a pas utilisé le vrai dataset !"
assert int(run_data.data.params["feature_count"]) > 4, "Le nombre de features suggère les données simulées, pas le vrai CSV"

print("\n=== 6. Monitoring RÉEL sur le vrai dataset (split chronologique via TransactionDT) ===")
r = client.post(f"/monitoring/run-now/{new_model_id}", headers=headers)
print(r.status_code, r.json())
assert r.status_code == 201
run = r.json()
assert run["report_json"]["source"] == "dataset_reel", "Le monitoring a utilisé le simulateur au lieu du vrai dataset !"
print(f"Score de dérive réel calculé : {run['drift_score']}")
print("Détail par variable :", list(run["report_json"]["columns"].keys()))
assert "purchase_hour" in run["report_json"]["columns"]

print("\n=== 7. Vérifier qu'une alerte a été créée (la dérive volontaire doit être détectée) ===")
r = client.get("/alerts/", headers=headers)
alerts = r.json()
print(alerts)
assert len(alerts) >= 1, "La dérive volontairement injectée (purchase_hour) aurait dû déclencher une alerte"
alert_id = alerts[0]["id"]

print("\n=== 8. Valider l'alerte -> ré-entraînement réel sur les vraies données ===")
r = client.patch(f"/alerts/{alert_id}/review", headers=headers, json={"approve": True, "comment": "Dérive confirmée"})
print(r.status_code, r.json())
assert r.status_code == 200

r = client.get("/retraining-jobs/", headers=headers)
jobs = r.json()
print(jobs)
retrain_job = [j for j in jobs if j["alert_id"] == alert_id][0]
assert retrain_job["status"] == "reussi", f"Le ré-entraînement aurait dû réussir : {retrain_job.get('error_message')}"

print("\n=== 9. Vérifier la v2, entraînée sur le même vrai dataset ===")
r = client.get("/models/", headers=headers)
versions = r.json()
v2 = next(v for v in versions if v["version_number"] == 2)
print(v2)
assert v2["status"] == "en_production"

print("\n✅ PIPELINE COMPLET AVEC VRAI DATASET VALIDÉ : import -> configuration -> entraînement -> monitoring -> alerte -> ré-entraînement, tout sur des données réelles.")

shutil.rmtree("./test_real_uploads", ignore_errors=True)
os.remove(csv_path)
