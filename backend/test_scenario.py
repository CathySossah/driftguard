"""
Teste le protocole expérimental "dérive progressive" (chapitre 2.4) :
plusieurs cycles successifs de monitoring réel (Evidently AI) sur le même
modèle, jusqu'à franchissement du seuil et création automatique d'une alerte.
"""
import os
os.environ["DATABASE_URL"] = "sqlite:///./test_scenario.db"
if os.path.exists("test_scenario.db"):
    os.remove("test_scenario.db")

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import models

client = TestClient(app)

# --- Setup : admin + dataset + version en production ---
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
db.close()

print(f"Modèle en production créé : v{version.version_number} ({version_id})\n")

print(f"{'Cycle':<8}{'Niveau simulé':<16}{'Score de dérive':<18}{'Dérive détectée':<18}{'Alerte créée'}")
print("-" * 80)

for cycle in range(1, 9):
    r = client.post(f"/monitoring/run-now/{version_id}", headers=headers)
    assert r.status_code == 201, r.text
    run = r.json()

    alerts = client.get("/alerts/", headers=headers).json()
    alert_created = "OUI" if len(alerts) > 0 and cycle == next(
        (c for c in range(1, 9) if False), None
    ) else ("OUI" if alerts else "non")

    sim_level = run["report_json"]["simulated_drift_level"]
    print(f"{cycle:<8}{sim_level:<16.2f}{run['drift_score']:<18.3f}{str(run['drift_detected']):<18}{len(alerts)} alerte(s) au total")

print("\n--- Détail du dernier rapport de dérive (par variable) ---")
last_run = client.get("/monitoring/", headers=headers).json()[0]
for col, detail in last_run["report_json"]["columns"].items():
    status = "⚠️ DÉRIVE" if detail["drifted"] else "stable"
    print(f"  {col:<16} p-value={detail['p_value']:.4f}  ({detail['method']})  -> {status}")

print("\n--- Alertes créées au cours du scénario ---")
alerts = client.get("/alerts/", headers=headers).json()
for a in alerts:
    print(f"  Sévérité: {a['severity']:<10} Statut: {a['status']}")

assert len(alerts) >= 1, "Le scénario aurait dû déclencher au moins une alerte"
print("\n✅ Scénario de dérive progressive validé : l'alerte se déclenche bien quand le seuil est franchi.")
