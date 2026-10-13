"""
Teste le pipeline de ré-entraînement RÉEL de bout en bout :
alerte validée -> entraînement RandomForest -> journalisation MLflow ->
nouvelle ModelVersion publiée -> ancienne version archivée.
"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_retraining.db"
os.environ["MLFLOW_TRACKING_URI"] = "sqlite:///./test_mlflow.db"

for f in ["test_retraining.db", "test_mlflow.db"]:
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import models

client = TestClient(app)

# --- Setup ---
client.post("/auth/register", json={
    "full_name": "Catherine Sossah", "email": "admin@driftguard.sn",
    "password": "testpass123", "role": "admin",
})
token = client.post("/auth/login", json={
    "email": "admin@driftguard.sn", "password": "testpass123",
}).json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

db = SessionLocal()
dataset = models.Dataset(name="IEEE-CIS Fraud", domain=models.DomainEnum.finance)
db.add(dataset)
db.commit()
db.refresh(dataset)

version = models.ModelVersion(
    dataset_id=dataset.id, version_number=12,
    status=models.ModelStatusEnum.en_production,
    metrics={"accuracy": 0.942},
)
db.add(version)
db.commit()
db.refresh(version)
version_id = version.id
dataset_id = dataset.id
db.close()

print(f"Modèle initial en production : v{version.version_number} ({version_id})\n")

# --- 1. Provoquer une dérive détectée (plusieurs cycles) ---
print("=== Cycles de monitoring jusqu'à détection de dérive ===")
alert_id = None
for cycle in range(1, 6):
    r = client.post(f"/monitoring/run-now/{version_id}", headers=headers)
    run = r.json()
    print(f"  Cycle {cycle} : drift_score={run['drift_score']:.3f} détecté={run['drift_detected']}")
    alerts = client.get("/alerts/", headers=headers, params={"status_filter": "en_attente"}).json()
    if alerts:
        alert_id = alerts[0]["id"]
        print(f"  -> Alerte créée : {alert_id} (sévérité {alerts[0]['severity']})")
        break

assert alert_id is not None, "Aucune alerte créée après 5 cycles"

# --- 2. Valider l'alerte -> déclenche le ré-entraînement réel en tâche de fond ---
print("\n=== Validation de l'alerte (déclenche le ré-entraînement réel) ===")
r = client.patch(f"/alerts/{alert_id}/review", headers=headers, json={"approve": True, "comment": "Confirmé"})
print("Statut alerte :", r.json()["status"])

# --- 3. Vérifier le résultat du job (le TestClient exécute les BackgroundTasks avant de rendre la main) ---
print("\n=== Résultat du job de ré-entraînement ===")
jobs = client.get("/retraining-jobs/", headers=headers).json()
job = jobs[0]
print(f"  Statut       : {job['status']}")
print(f"  Nouvelle v°  : {job['new_model_version_id']}")
print(f"  Erreur       : {job['error_message']}")

assert job["status"] == "reussi", f"Le job aurait dû réussir, statut obtenu : {job['status']}"
assert job["new_model_version_id"] is not None

# --- 4. Vérifier la nouvelle ModelVersion et ses métriques réelles ---
print("\n=== Nouvelle version de modèle publiée ===")
r = client.get("/models/", headers=headers, params={"dataset_id": dataset_id})
versions = r.json()
for v in sorted(versions, key=lambda x: x["version_number"]):
    print(f"  v{v['version_number']} — statut={v['status']} — métriques={v['metrics']}")

new_version = next(v for v in versions if v["id"] == job["new_model_version_id"])
old_version_after = next(v for v in versions if v["id"] == version_id)

assert new_version["version_number"] == 13
assert new_version["status"] == "en_production"
assert old_version_after["status"] == "archive"
assert new_version["metrics"] is not None
assert new_version["mlflow_run_id"] is not None
print(f"\n  Run MLflow associé : {new_version['mlflow_run_id']}")

# --- 5. Vérifier que le run est bien consultable dans MLflow ---
import mlflow
mlflow.set_tracking_uri("sqlite:///./test_mlflow.db")
run_data = mlflow.get_run(new_version["mlflow_run_id"])
print("\n=== Vérification directe dans MLflow ===")
print("  Params  :", run_data.data.params)
print("  Metrics :", run_data.data.metrics)

assert run_data.data.metrics["accuracy"] == new_version["metrics"]["accuracy"]

print("\n✅ PIPELINE DE RÉ-ENTRAÎNEMENT COMPLET VALIDÉ (entraînement réel + MLflow réel)")
