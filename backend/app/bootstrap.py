"""
Démarrage automatique : prépare une instance toute neuve (ex. hébergeur dont
le disque est effacé à chaque redémarrage) pour qu'elle soit utilisable sans
aucune manipulation manuelle.

Variables d'environnement (toutes optionnelles) :
  ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_NAME   -> crée le compte administrateur
  DEMO_USER_EMAIL, DEMO_USER_PASSWORD       -> crée un compte utilisateur de démonstration
  SEED_DEMO=true                            -> crée un dataset de démonstration (données
                                               simulées) et entraîne un premier modèle en
                                               tâche de fond
"""
import json
import logging
import os
import threading
from datetime import datetime

from app.database import SessionLocal
from app import models
from app.security import hash_password, SECRET_KEY
from app.services.audit_service import log_action

logger = logging.getLogger("driftguard.bootstrap")

_DEFAULT_SECRET = "changez-moi-en-production-avec-une-cle-longue-et-aleatoire"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "oui", "on"}


def _ensure_user(db, email: str, password: str, name: str, role: models.RoleEnum) -> None:
    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        return
    user = models.User(full_name=name, email=email, password_hash=hash_password(password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    log_action(db, action="user.created", user_id=user.id, target=f"Compte {user.full_name} ({role.value}) — création automatique")
    logger.info("Compte %s créé automatiquement (%s)", email, role.value)


def _seed_demo(db) -> None:
    from app.demo_model import BUNDLE_PATH, METRICS_PATH, LOCAL_RUN_ID, DATASET_NAME

    if db.query(models.Dataset).count() > 0:
        return
    dataset = models.Dataset(
        name=DATASET_NAME,
        domain=models.DomainEnum.finance,
        source_path=None,
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    admin = db.query(models.User).filter(models.User.role == models.RoleEnum.admin).first()

    # Cas normal (image Docker) : le modèle de démonstration est déjà construit.
    # On l'enregistre simplement, sans entraînement ni MLflow : très léger en mémoire.
    if BUNDLE_PATH.exists():
        try:
            metrics = json.loads(METRICS_PATH.read_text(encoding="utf-8")).get("metrics")
        except Exception:
            metrics = None
        version = models.ModelVersion(
            dataset_id=dataset.id,
            mlflow_run_id=LOCAL_RUN_ID,
            version_number=1,
            status=models.ModelStatusEnum.en_production,
            metrics=metrics,
            deployed_at=datetime.utcnow(),
        )
        db.add(version)
        db.commit()
        log_action(db, action="model.initial_training", user_id=admin.id if admin else None,
                   target=f"Dataset {dataset.name} — modèle de démonstration pré-entraîné")
        logger.info("Dataset et modèle de démonstration enregistrés (pré-entraîné, sans MLflow)")
        return

    # Secours (développement local, sans image Docker) : entraînement en arrière-plan.
    job = models.RetrainingJob(
        alert_id=None,
        dataset_id=dataset.id,
        triggered_by=admin.id if admin else None,
        status=models.JobStatusEnum.en_cours,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    log_action(db, action="model.initial_training", user_id=admin.id if admin else None, target=f"Dataset {dataset.name} — démo automatique")

    # Import tardif : évite de charger MLflow/scikit-learn si le démarrage automatique n'est pas utilisé.
    from app.services.retraining_service import execute_initial_training_job

    threading.Thread(
        target=execute_initial_training_job, args=(job.id, dataset.id),
        name="seed-demo-training", daemon=True,
    ).start()
    logger.info("Dataset de démonstration créé, entraînement du premier modèle lancé en arrière-plan")


def run_bootstrap() -> None:
    """Ne fait jamais échouer le démarrage de l'API : une erreur est journalisée, c'est tout."""
    if SECRET_KEY == _DEFAULT_SECRET:
        logger.warning("SECRET_KEY par défaut utilisée : définissez-la en déploiement.")
    if not os.getenv("ADMIN_SIGNUP_CODE"):
        logger.warning("ADMIN_SIGNUP_CODE non défini : n'importe qui peut créer un compte administrateur.")

    db = SessionLocal()
    try:
        admin_email, admin_password = os.getenv("ADMIN_EMAIL"), os.getenv("ADMIN_PASSWORD")
        if admin_email and admin_password:
            _ensure_user(db, admin_email, admin_password, os.getenv("ADMIN_NAME", "Administrateur"), models.RoleEnum.admin)

        user_email, user_password = os.getenv("DEMO_USER_EMAIL"), os.getenv("DEMO_USER_PASSWORD")
        if user_email and user_password:
            _ensure_user(db, user_email, user_password, os.getenv("DEMO_USER_NAME", "Utilisateur démo"), models.RoleEnum.user)

        if _truthy(os.getenv("SEED_DEMO")):
            _seed_demo(db)
    except Exception:
        db.rollback()
        logger.exception("Démarrage automatique incomplet")
    finally:
        db.close()
