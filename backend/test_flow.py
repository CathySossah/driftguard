"""
Test manuel du flux complet, exécuté directement en mémoire via TestClient
(pas besoin de lancer un serveur réseau séparé).
"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_flow.db"

# Repartir d'une base vierge à chaque exécution
if os.path.exists("test_flow.db"):
    os.remove("test_flow.db")

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

print("=== 1. Inscription d'un administrateur ===")
r = client.post("/auth/register", json={
    "full_name": "Catherine Sossah",
    "email": "catherine@driftguard.sn",
    "password": "testpass123",
    "role": "admin",
})
print(r.status_code, r.json())
assert r.status_code == 201

print("\n=== 2. Inscription d'un utilisateur standard ===")
r = client.post("/auth/register", json={
    "full_name": "Aida Ndiaye",
    "email": "aida@driftguard.sn",
    "password": "userpass123",
    "role": "user",
})
print(r.status_code, r.json())
assert r.status_code == 201

print("\n=== 3. Connexion admin ===")
r = client.post("/auth/login", json={"email": "catherine@driftguard.sn", "password": "testpass123"})
print(r.status_code, r.json())
assert r.status_code == 200
admin_token = r.json()["access_token"]
admin_headers = {"Authorization": f"Bearer {admin_token}"}

print("\n=== 4. Connexion utilisateur ===")
r = client.post("/auth/login", json={"email": "aida@driftguard.sn", "password": "userpass123"})
user_token = r.json()["access_token"]
user_headers = {"Authorization": f"Bearer {user_token}"}
print(r.status_code, "token obtenu")

print("\n=== 5. Accès /users/me (admin) ===")
r = client.get("/users/me", headers=admin_headers)
print(r.status_code, r.json())
assert r.status_code == 200

print("\n=== 6. Accès sans token -> doit échouer (401) ===")
r = client.get("/users/me")
print(r.status_code)
assert r.status_code == 401

print("\n=== 7. Liste des utilisateurs (admin) ===")
r = client.get("/users/", headers=admin_headers)
print(r.status_code, len(r.json()), "utilisateur(s)")
assert r.status_code == 200

print("\n=== 8. Liste des utilisateurs par un non-admin -> doit échouer (403) ===")
r = client.get("/users/", headers=user_headers)
print(r.status_code)
assert r.status_code == 403

print("\n=== 9. Créer un dataset, une version de modèle (via accès direct DB pour le test) ===")
from app.database import SessionLocal
from app import models
db = SessionLocal()
dataset = models.Dataset(name="IEEE-CIS Fraud", domain=models.DomainEnum.finance, source_path="/data/ieee_cis.csv")
db.add(dataset)
db.commit()
db.refresh(dataset)

version = models.ModelVersion(
    dataset_id=dataset.id,
    mlflow_run_id="run-abc123",
    version_number=12,
    status=models.ModelStatusEnum.en_production,
    metrics={"accuracy": 0.942, "f1": 0.91},
)
db.add(version)
db.commit()
db.refresh(version)
dataset_id = dataset.id
version_id = version.id
db.close()
print("Dataset et version créés :", dataset_id, version_id)

print("\n=== 10. Enregistrer un run de monitoring AVEC dérive (doit créer une alerte) ===")
r = client.post("/monitoring/", headers=admin_headers, json={
    "model_version_id": version_id,
    "drift_score": 0.31,
    "drift_detected": True,
    "report_json": {"purchase_hour": 0.31},
})
print(r.status_code, r.json())
assert r.status_code == 201

print("\n=== 11. Vérifier qu'une alerte a bien été créée automatiquement ===")
r = client.get("/alerts/", headers=admin_headers)
alerts = r.json()
print(r.status_code, alerts)
assert len(alerts) == 1
assert alerts[0]["status"] == "en_attente"
alert_id = alerts[0]["id"]

print("\n=== 12. Valider l'alerte (doit créer un RetrainingJob) ===")
r = client.patch(f"/alerts/{alert_id}/review", headers=admin_headers, json={"approve": True, "comment": "Confirmé, dérive réelle"})
print(r.status_code, r.json())
assert r.status_code == 200
assert r.json()["status"] == "validee"

print("\n=== 13. Vérifier le RetrainingJob créé (résolu immédiatement : entraînement réel) ===")
r = client.get("/retraining-jobs/", headers=admin_headers)
jobs = r.json()
print(r.status_code, jobs)
assert len(jobs) == 1
assert jobs[0]["status"] in ("reussi", "echoue")  # entraînement réel exécuté en tâche de fond
job_id = jobs[0]["id"]

print("\n=== 14. Forcer artificiellement un état d'échec (test de l'endpoint /complete) ===")
r = client.patch(f"/retraining-jobs/{job_id}/complete?success=false&error_message=Donnees+insuffisantes", headers=admin_headers)
print(r.status_code, r.json())
assert r.json()["status"] == "echoue"

print("\n=== 15. Relancer manuellement le job échoué (relance un entraînement réel) ===")
r = client.post(f"/retraining-jobs/{job_id}/retry", headers=admin_headers)
print(r.status_code, r.json())
assert r.status_code == 201

print("\n=== 16. Prédiction sur un modèle sans artefact MLflow -> 409 explicite (pas de faux résultat) ===")
r = client.post("/predictions/", headers=user_headers, json={
    "model_version_id": version_id,
    "input_payload": {"TransactionAmt": 128500, "purchase_hour": 23},
})
print(r.status_code, r.json())
assert r.status_code == 409
# (La prédiction réelle sur un modèle entraîné est testée dans test_predictions.py)

print("\n=== 17. Historique des prédictions (utilisateur) : rien d'enregistré après un refus ===")
r = client.get("/predictions/history", headers=user_headers)
print(r.status_code, len(r.json()), "prédiction(s)")
assert len(r.json()) == 0

print("\n✅ TOUS LES TESTS SONT PASSÉS AVEC SUCCÈS")
