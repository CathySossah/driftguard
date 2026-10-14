"""
Reproduit le scénario signalé par Catherine : un entraînement initial
échoue, puis on clique "Relancer manuellement". Avant le correctif, ça tombait sur
'Impossible de déterminer le modèle à ré-entraîner (alerte associée
introuvable)' à chaque fois, car retry_job ne savait relancer que des jobs
nés d'une alerte. Vérifie aussi que le journal d'audit s'alimente.
"""
import os
import shutil

os.environ["DATABASE_URL"] = "sqlite:///./test_retry_bug.db"
os.environ["MLFLOW_TRACKING_URI"] = "sqlite:///./test_retry_mlflow.db"
os.environ["DATASET_UPLOAD_DIR"] = "./test_retry_uploads"

for f in ["test_retry_bug.db", "test_retry_mlflow.db"]:
    if os.path.exists(f):
        os.remove(f)
if os.path.exists("./test_retry_uploads"):
    shutil.rmtree("./test_retry_uploads")

import pandas as pd
import numpy as np

# CSV volontairement très déséquilibré (1 seul cas positif) : avant, il faisait
# échouer l'entraînement avec "données insuffisantes" ; il doit désormais réussir.
rng = np.random.default_rng(1)
df = pd.DataFrame({
    "amount": rng.gamma(2, 50, 50),
    "hour": rng.integers(0, 23, 50),
    "is_fraud": [0] * 49 + [1],  # une seule fraude
})
csv_path = "/tmp/deseq.csv"
df.to_csv(csv_path, index=False)

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

print("=== 1. Import + config du dataset déséquilibré ===")
with open(csv_path, "rb") as f:
    r = client.post("/datasets/upload", headers=headers,
                     files={"file": ("deseq.csv", f, "text/csv")},
                     data={"name": "Dataset déséquilibré", "domain": "finance"})
dataset_id = r.json()["id"]
client.patch(f"/datasets/{dataset_id}/configure", headers=headers, json={"target_column": "is_fraud"})

print("\n=== 2. Entraînement initial sur le dataset déséquilibré -> doit RÉUSSIR (plus de 'données insuffisantes') ===")
r = client.post(f"/models/train-initial/{dataset_id}", headers=headers)
job_id = r.json()["id"]
job = next(j for j in client.get("/retraining-jobs/", headers=headers).json() if j["id"] == job_id)
print(job)
assert job["status"] == "reussi", job

print("\n=== 2b. Nouvel entraînement avec 3 algorithmes + sur-échantillonnage : progression, résultats, nouvelle version ===")
r = client.post(f"/models/train-initial/{dataset_id}", headers=headers, json={
    "algorithms": ["random_forest", "logistic_regression", "gradient_boosting"],
    "balancing": "oversampling",
})
assert r.status_code == 202, r.text
job_id = r.json()["id"]
job = client.get(f"/retraining-jobs/{job_id}", headers=headers).json()
print({k: job[k] for k in ("status", "progress", "progress_label")})
assert job["status"] == "reussi" and job["progress"] == 100, job
results = job["training_results"]
assert results["config"]["balancing"] == "oversampling"
assert [x["algorithm"] for x in results["results"]] == ["random_forest", "logistic_regression", "gradient_boosting"]
assert all("metrics" in x for x in results["results"]) and results["best"] in results["algorithms"]
versions = client.get("/models/", headers=headers, params={"dataset_id": dataset_id}).json()
by_number = {v["version_number"]: v for v in versions}
assert sorted(by_number) == [1, 2]
# Un modèle est déjà en production pour ce dataset : le nouveau part en STAGING (promotion manuelle)
assert by_number[1]["status"] == "en_production" and by_number[2]["status"] == "staging", by_number
assert results["published"] == {"version_number": 2, "status": "staging"}

print("\n=== 2c. Cycle de vie : staging -> production archive l'ancienne version ===")
r = client.patch(f"/models/{by_number[2]['id']}/status", headers=headers, json={"status": "en_production"})
assert r.status_code == 200 and r.json()["status"] == "en_production" and r.json()["deployed_at"]
versions = {v["version_number"]: v for v in client.get("/models/", headers=headers, params={"dataset_id": dataset_id}).json()}
assert versions[1]["status"] == "archive" and versions[2]["status"] == "en_production"
assert client.patch(f"/models/{by_number[2]['id']}/status", headers=headers, json={"status": "en_production"}).status_code == 400
r = client.patch(f"/models/{by_number[1]['id']}/status", headers=headers, json={"status": "staging"})
assert r.status_code == 200 and r.json()["status"] == "staging"
assert client.patch(f"/models/{by_number[1]['id']}/status", headers=headers, json={"status": "inconnu"}).status_code == 422
assert client.patch("/models/introuvable/status", headers=headers, json={"status": "staging"}).status_code == 404
r = client.post(f"/models/train-initial/{dataset_id}", headers=headers, json={"target_status": "bizarre"})
assert r.status_code == 422
r = client.post(f"/models/train-initial/{dataset_id}", headers=headers, json={"algorithms": ["nimporte_quoi"]})
assert r.status_code == 422
opts = client.get("/models/training-options", headers=headers).json()
assert len(opts["algorithms"]) == 3 and len(opts["balancing"]) == 3

print("\n=== 3. Un fichier disparu fait échouer un job : « Relancer » doit retomber sur la vraie cause ===")
with open(csv_path, "rb") as f:
    r = client.post("/datasets/upload", headers=headers,
                     files={"file": ("perdu.csv", f, "text/csv")},
                     data={"name": "Dataset dont le fichier disparaît", "domain": "finance"})
lost = r.json()
client.patch(f"/datasets/{lost['id']}/configure", headers=headers, json={"target_column": "is_fraud"})
os.remove(lost["source_path"])
r = client.post(f"/models/train-initial/{lost['id']}", headers=headers)
job_id = r.json()["id"]
job = next(j for j in client.get("/retraining-jobs/", headers=headers).json() if j["id"] == job_id)
print(job)
assert job["status"] == "echoue"
assert "lire le fichier" in job["error_message"].lower()

r = client.post(f"/retraining-jobs/{job_id}/retry", headers=headers)
print(r.status_code, r.json())
retried_job_id = r.json()["id"]
retried = next(j for j in client.get("/retraining-jobs/", headers=headers).json() if j["id"] == retried_job_id)
print(retried)

assert retried["status"] == "echoue", "Le fichier est toujours absent : le job doit échouer à nouveau"
assert "introuvable" not in (retried["error_message"] or "").lower(), \
    "BUG NON CORRIGÉ : le job tombe encore sur 'alerte introuvable' au lieu de retenter le vrai entraînement"
assert "lire le fichier" in retried["error_message"].lower()

print("\n✅ La relance retombe sur la vraie cause (fichier illisible), jamais sur 'alerte introuvable'.")

print("\n=== 4. Vérifier que le journal d'audit s'est bien rempli ===")
r = client.get("/audit-logs/", headers=headers)
logs = r.json()
actions = [l["action"] for l in logs]
print(actions)
assert "user.created" in actions
assert "dataset.uploaded" in actions
assert "model.initial_training" in actions
assert "retraining.retried" in actions
assert all(l["user_name"] == "Catherine Sossah" for l in logs if l["user_id"])

print("\n✅ JOURNAL D'AUDIT FONCTIONNEL — actions correctement enregistrées et attribuées.")

shutil.rmtree("./test_retry_uploads", ignore_errors=True)
os.remove(csv_path)
