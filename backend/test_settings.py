"""
Test de la page Paramètres (API) : lecture, modification, validation, droits, et effet réel
des seuils sur le monitoring (Evidently est exécuté : quelques secondes).
    python test_settings.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_settings.db"
for f in ["test_settings.db"]:
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app import models

client = TestClient(app)


def auth(email, role):
    client.post("/auth/register", json={"full_name": email, "email": email, "password": "motdepasse-123", "role": role})
    r = client.post("/auth/login", json={"email": email, "password": "motdepasse-123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


admin = auth("admin@settings.test", "admin")
user = auth("user@settings.test", "user")

print("=== 1. Valeurs par défaut ===")
r = client.get("/settings/", headers=user)
print("  ", r.json())
assert r.json() == {"alert_threshold": 0.2, "pvalue_threshold": 0.05, "variable_thresholds": {}}

print("=== 2. Un utilisateur simple ne peut pas modifier ===")
assert client.patch("/settings/", headers=user, json={"alert_threshold": 0.5}).status_code == 403

print("=== 3. Valeurs invalides refusées ===")
for bad in ({"alert_threshold": 0}, {"alert_threshold": 1.5}, {"pvalue_threshold": 0.9},
            {"variable_thresholds": {"x": 3}}):
    assert client.patch("/settings/", headers=admin, json=bad).status_code == 422, bad

print("=== 4. Modification et retrait d'un seuil par variable ===")
r = client.patch("/settings/", headers=admin, json={
    "alert_threshold": 0.4, "pvalue_threshold": 0.01, "variable_thresholds": {"purchase_hour": 0.2, "TransactionAmt": 0.3}})
assert r.status_code == 200 and r.json()["alert_threshold"] == 0.4
r = client.patch("/settings/", headers=admin, json={"variable_thresholds": {"TransactionAmt": None}})
assert r.json()["variable_thresholds"] == {"purchase_hour": 0.2}
assert r.json()["alert_threshold"] == 0.4  # inchangé

print("=== 4b. Alertes par e-mail : réglage et e-mail de test ===")
for var in ("EMAIL_FROM", "BREVO_API_KEY", "SMTP_HOST"):
    os.environ.pop(var, None)
r = client.get("/settings/", headers=admin).json()
assert r["email_alerts_enabled"] is True and r["email_provider"] is None
r = client.patch("/settings/", headers=admin, json={"email_alerts_enabled": False}).json()
assert r["email_alerts_enabled"] is False and r["alert_threshold"] == 0.4  # le reste est inchangé
client.patch("/settings/", headers=admin, json={"email_alerts_enabled": True})
r = client.post("/settings/test-email", headers=admin)
print("   e-mail de test sans service configuré :", r.status_code, r.json()["detail"][:60])
assert r.status_code == 400
assert client.post("/settings/test-email", headers=user).status_code == 403

print("=== 5. Effet sur le monitoring : le seuil d'alerte décide de la création d'alertes ===")
db = SessionLocal()
dataset = models.Dataset(name="Démo seuils", domain=models.DomainEnum.finance, source_path=None)
db.add(dataset)
db.commit()
db.refresh(dataset)
version = models.ModelVersion(dataset_id=dataset.id, mlflow_run_id="run-x", version_number=1,
                              status=models.ModelStatusEnum.en_production)
db.add(version)
db.commit()
db.refresh(version)
version_id = version.id
db.close()

client.patch("/settings/", headers=admin, json={"alert_threshold": 1.0, "pvalue_threshold": 0.05,
                                                "variable_thresholds": {"purchase_hour": None}})
for _ in range(4):  # la dérive simulée augmente à chaque cycle
    run = client.post(f"/monitoring/run-now/{version_id}", headers=admin).json()
print("   dernier drift_score :", run["drift_score"])
alerts = client.get("/alerts/", headers=admin).json()
if run["drift_score"] < 1.0:
    assert len(alerts) == 0, "seuil d'alerte à 100 % : aucune alerte tant que toutes les variables ne dérivent pas"

client.patch("/settings/", headers=admin, json={"alert_threshold": 0.01})
client.post(f"/monitoring/run-now/{version_id}", headers=admin)
alerts = client.get("/alerts/", headers=admin).json()
print("   alertes avec un seuil très bas :", len(alerts))

print("=== 6. Variables observées ===")
r = client.get("/settings/variables", headers=admin)
names = [v["name"] for v in r.json()]
print("  ", names)
assert {"purchase_hour", "TransactionAmt"} <= set(names)
assert all(v["kind"] in ("p_value", "distance") for v in r.json())

print("\n✅ test_settings : OK")
