"""
Teste l'upload d'un vrai fichier CSV (bouton 'Importer un dataset' de l'interface) :
validation du format, stockage sur disque, création du Dataset en base, aperçu.
"""
import os
import shutil

os.environ["DATABASE_URL"] = "sqlite:///./test_upload.db"
os.environ["DATASET_UPLOAD_DIR"] = "./test_data_uploads"

for f in ["test_upload.db"]:
    if os.path.exists(f):
        os.remove(f)
if os.path.exists("./test_data_uploads"):
    shutil.rmtree("./test_data_uploads")

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

print("=== 1. Upload d'un CSV valide ===")
csv_content = b"TransactionAmt,purchase_hour,device_type,is_fraud\n120.5,14,mobile,0\n45.0,23,desktop,1\n89.2,11,mobile,0\n"
files = {"file": ("mini_ieee_cis.csv", csv_content, "text/csv")}
data = {"name": "IEEE-CIS Fraud (extrait test)", "domain": "finance"}
r = client.post("/datasets/upload", headers=headers, files=files, data=data)
print(r.status_code, r.json())
assert r.status_code == 201
dataset_id = r.json()["id"]

print("\n=== 2. Vérifier que le dataset apparaît dans la liste ===")
r = client.get("/datasets/", headers=headers)
print(r.status_code, len(r.json()), "dataset(s)")
assert len(r.json()) == 1

print("\n=== 3. Aperçu du dataset importé ===")
r = client.get(f"/datasets/{dataset_id}/preview", headers=headers)
print(r.status_code, r.json())
assert r.status_code == 200
assert r.json()["columns"] == ["TransactionAmt", "purchase_hour", "device_type", "is_fraud"]

print("\n=== 4. Rejet d'un fichier non-CSV ===")
files_bad = {"file": ("photo.png", b"\x89PNG\r\n", "image/png")}
r = client.post("/datasets/upload", headers=headers, files=files_bad, data={"name": "Mauvais fichier", "domain": "finance"})
print(r.status_code, r.json())
assert r.status_code == 400

print("\n=== 5. Rejet d'un CSV vide/invalide ===")
files_empty = {"file": ("vide.csv", b"", "text/csv")}
r = client.post("/datasets/upload", headers=headers, files=files_empty, data={"name": "CSV vide", "domain": "finance"})
print(r.status_code, r.json())
assert r.status_code == 400

print("\n=== 6. Un utilisateur non-admin ne peut pas uploader ===")
client.post("/auth/register", json={
    "full_name": "Aida Ndiaye", "email": "aida@driftguard.sn",
    "password": "userpass123", "role": "user",
})
user_token = client.post("/auth/login", json={
    "email": "aida@driftguard.sn", "password": "userpass123",
}).json()["access_token"]
r = client.post("/datasets/upload", headers={"Authorization": f"Bearer {user_token}"}, files=files, data=data)
print(r.status_code)
assert r.status_code == 403

print("\n✅ UPLOAD DE DATASET VALIDÉ (succès, aperçu, rejets, contrôle d'accès)")

shutil.rmtree("./test_data_uploads", ignore_errors=True)
