from typing import Optional

import os
import uuid

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import get_current_user, require_admin
from app.services.real_data_service import guess_target_column
from app.services.audit_service import log_action

router = APIRouter(prefix="/datasets", tags=["Datasets"])

UPLOAD_DIR = os.getenv("DATASET_UPLOAD_DIR", "./data/uploads")
MAX_UPLOAD_SIZE_MB = 50


@router.get("/", response_model=list[schemas.DatasetOut])
def list_datasets(
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    """Liste des jeux de données (finance, santé, agriculture) — sélecteur de domaine."""
    return db.query(models.Dataset).all()


@router.post("/upload", response_model=schemas.DatasetOut, status_code=201)
async def upload_dataset(
    file: UploadFile = File(...),
    name: str = Form(...),
    domain: models.DomainEnum = Form(...),
    target_column: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    """
    Upload d'un jeu de données réel au format CSV (bouton 'Importer un dataset'
    de l'interface). Le fichier est stocké sur disque, puis un enregistrement
    Dataset est créé en base avec le chemin correspondant.

    `target_column` (optionnel) précise la colonne à prédire pour
    l'entraînement (ex. "isFraud" pour IEEE-CIS Fraud Detection, "readmitted"
    pour un dataset de réadmission hospitalière). Si elle n'est pas fournie,
    le système tente de la deviner automatiquement (colonnes usuelles comme
    isFraud, target, label, class, churn...) ; à défaut, l'entraînement sur
    ce dataset échouera avec un message explicite demandant de la préciser.

    Le fichier est validé comme un CSV exploitable (lisible par pandas, au
    moins 1 ligne) avant d'être accepté — utile par exemple pour importer
    IEEE-CIS Fraud Detection (finance), UCI Diabetes 130-US Hospitals (santé),
    ou un extrait FAOSTAT (agriculture) pour les scénarios de généralisabilité
    du chapitre 4.3 du mémoire.
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Seuls les fichiers .csv sont acceptés.")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_filename = f"{uuid.uuid4().hex}_{file.filename}"
    destination = os.path.join(UPLOAD_DIR, safe_filename)

    size = 0
    with open(destination, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                out.close()
                os.remove(destination)
                raise HTTPException(status_code=400, detail=f"Fichier trop volumineux (max {MAX_UPLOAD_SIZE_MB} Mo).")
            out.write(chunk)

    try:
        preview = pd.read_csv(destination, nrows=5)
        if preview.empty:
            raise ValueError("Le fichier CSV ne contient aucune ligne exploitable.")
    except Exception as e:
        os.remove(destination)
        raise HTTPException(status_code=400, detail=f"Fichier CSV invalide ou illisible : {e}")

    if target_column and target_column not in preview.columns:
        os.remove(destination)
        raise HTTPException(
            status_code=400,
            detail=f"La colonne cible '{target_column}' n'existe pas dans ce fichier. "
                   f"Colonnes disponibles : {', '.join(preview.columns)}",
        )
    resolved_target = target_column or guess_target_column(preview)

    dataset = models.Dataset(name=name, domain=domain, source_path=destination, target_column=resolved_target)
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    log_action(db, action="dataset.uploaded", user_id=_admin.id, target=f"{dataset.name} ({dataset.domain.value})")
    return dataset


@router.patch("/{dataset_id}/configure", response_model=schemas.DatasetOut)
def configure_dataset(
    dataset_id: str,
    payload: schemas.DatasetConfigure,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_admin),
):
    """
    Désigne, après import, la colonne cible (obligatoire pour l'entraînement)
    et éventuellement une colonne temporelle (pour un split référence/courant
    chronologique plus fidèle lors du calcul de dérive). Utilisé par la page
    Datasets une fois l'aperçu des colonnes consulté.
    """
    dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
    if not dataset or not dataset.source_path or not os.path.exists(dataset.source_path):
        raise HTTPException(status_code=404, detail="Dataset introuvable ou fichier manquant sur le serveur.")

    columns = pd.read_csv(dataset.source_path, nrows=0).columns
    if payload.target_column not in columns:
        raise HTTPException(status_code=400, detail=f"Colonne cible '{payload.target_column}' absente du fichier.")
    if payload.time_column and payload.time_column not in columns:
        raise HTTPException(status_code=400, detail=f"Colonne temporelle '{payload.time_column}' absente du fichier.")

    dataset.target_column = payload.target_column
    dataset.time_column = payload.time_column
    db.commit()
    db.refresh(dataset)
    return dataset


@router.get("/{dataset_id}/preview")
def preview_dataset(
    dataset_id: str,
    rows: int = 10,
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    """Aperçu des premières lignes d'un dataset importé (colonnes détectées, extrait)."""
    dataset = db.query(models.Dataset).filter(models.Dataset.id == dataset_id).first()
    if not dataset or not dataset.source_path or not os.path.exists(dataset.source_path):
        raise HTTPException(status_code=404, detail="Dataset introuvable ou fichier manquant sur le serveur.")

    df = pd.read_csv(dataset.source_path, nrows=rows)
    return {
        "columns": list(df.columns),
        "row_count_preview": len(df),
        "preview": df.fillna("").to_dict(orient="records"),
    }
