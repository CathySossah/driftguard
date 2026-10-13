"""
Test de bout en bout : code d'invitation admin, démarrage automatique (comptes
+ dataset de démonstration + premier modèle entraîné en arrière-plan), puis
PRÉDICTIONS RÉELLES avec explication.

    python test_predictions.py      (≈ 1 à 2 minutes : un vrai modèle est entraîné)
"""
import os
import shutil
import time

os.environ["DATABASE_URL"] = "sqlite:///./test_predictions.db"
os.environ["MLFLOW_TRACKING_URI"] = "sqlite:///./test_predictions_mlflow.db"
os.environ["MLFLOW_ARTIFACT_ROOT"] = os.path.abspath("./test_predictions_mlruns")
os.environ["ADMIN_SIGNUP_CODE"] = "code-secret-test"
os.environ["ADMIN_EMAIL"] = "boot@driftguard.test"
os.environ["ADMIN_PASSWORD"] = "bootpass123"
os.environ["DEMO_USER_EMAIL"] = "demo@driftguard.test"
os.environ["DEMO_USER_PASSWORD"] = "demopass123"
os.environ["SEED_DEMO"] = "true"

for f in ["test_predictions.db", "test_predictions_mlflow.db"]:
    if os.path.exists(f):
        os.remove(f)
shutil.rmtree("test_predictions_mlruns", ignore_errors=True)

from fastapi.testclient import TestClient
from app.main import app


def login(client, email, password):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# `with` => exécute le démarrage de l'application (comptes automatiques + démo)
with TestClient(app) as client:
    print("=== 1. Code d'invitation administrateur ===")
    body = {"full_name": "Pirate", "email": "pirate@x.test", "password": "pirate-pass-1", "role": "admin"}
    r = client.post("/auth/register", json=body)
    print("   sans code :", r.status_code)
    assert r.status_code == 403
    r = client.post("/auth/register", json={**body, "admin_code": "mauvais"})
    print("   mauvais code :", r.status_code)
    assert r.status_code == 403
    r = client.post("/auth/register", json={**body, "admin_code": "code-secret-test"})
    print("   bon code :", r.status_code)
    assert r.status_code == 201
    r = client.post("/auth/register", json={
        "full_name": "Simple", "email": "simple@x.test", "password": "simple-pass-1", "role": "user"})
    assert r.status_code == 201, "un utilisateur standard n'a pas besoin de code"

    print("=== 2. Démarrage automatique : comptes créés ===")
    admin_headers = login(client, "boot@driftguard.test", "bootpass123")
    user_headers = login(client, "demo@driftguard.test", "demopass123")
    r = client.get("/users/me", headers=admin_headers)
    assert r.json()["role"] == "admin"
    print("   admin et utilisateur de démo : OK")

    print("=== 3. Dataset de démo + premier modèle entraîné en arrière-plan ===")
    deadline = time.time() + 240
    models_available = []
    while time.time() < deadline:
        jobs = client.get("/retraining-jobs/", headers=admin_headers).json()
        if jobs and jobs[0]["status"] == "echoue":
            raise SystemExit(f"L'entraînement de démo a échoué : {jobs[0]['error_message']}")
        models_available = client.get("/predictions/models", headers=user_headers).json()
        if models_available:
            break
        time.sleep(3)
    assert models_available, "aucun modèle disponible après 4 minutes"
    version = models_available[0]
    print("   modèle prêt :", version["dataset_name"], "v%s" % version["version_number"], version["metrics"])

    print("=== 4. Formulaire de prédiction du modèle ===")
    r = client.get(f"/predictions/schema/{version['id']}", headers=user_headers)
    assert r.status_code == 200, r.text
    fields = r.json()["fields"]
    names = [f["name"] for f in fields]
    print("   champs :", names)
    assert {"TransactionAmt", "purchase_hour", "device_type", "card_type"} <= set(names)

    print("=== 5. Prédictions réelles ===")
    results = []
    for payload in (
        {"TransactionAmt": 120, "purchase_hour": 23, "device_type": "mobile", "card_type": "visa"},
        {"TransactionAmt": 120, "purchase_hour": 10, "device_type": "desktop", "card_type": "amex"},
    ):
        r = client.post("/predictions/", headers=user_headers, json={
            "model_version_id": version["id"], "input_payload": payload})
        print("  ", r.status_code, r.json())
        assert r.status_code == 201, r.text
        out = r.json()
        assert out["prediction"] in ("legitime", "suspecte")
        assert 0.0 <= out["probability"] <= 1.0
        results.append(out)
    assert results[0]["probability"] != results[1]["probability"], "la prédiction ne dépend pas de la saisie !"

    print("=== 6. Saisies et modèles invalides ===")
    r = client.post("/predictions/", headers=user_headers, json={
        "model_version_id": version["id"], "input_payload": {"purchase_hour": "abc"}})
    print("   texte à la place d'un nombre :", r.status_code, r.json())
    assert r.status_code == 422
    r = client.post("/predictions/", headers=user_headers, json={
        "model_version_id": version["id"], "input_payload": {"device_type": "fax"}})
    assert r.status_code == 422
    r = client.post("/predictions/", headers=user_headers, json={
        "model_version_id": "inexistant", "input_payload": {}})
    assert r.status_code == 404

    from app.database import SessionLocal
    from app import models
    db = SessionLocal()
    ds = db.query(models.Dataset).first()
    fake = models.ModelVersion(dataset_id=ds.id, mlflow_run_id="run-inexistant", version_number=99,
                               status=models.ModelStatusEnum.en_test)
    db.add(fake)
    db.commit()
    db.refresh(fake)
    fake_id = fake.id
    db.close()
    r = client.post("/predictions/", headers=user_headers, json={"model_version_id": fake_id, "input_payload": {}})
    print("   modèle sans artefact :", r.status_code)
    assert r.status_code == 409

    print("=== 7. Historique et accès ===")
    r = client.get("/predictions/history", headers=user_headers)
    assert r.status_code == 200 and len(r.json()) == 2
    assert all(h["probability"] is not None for h in r.json())
    assert client.get("/predictions/models").status_code == 401

print("\n✅ test_predictions : OK")
