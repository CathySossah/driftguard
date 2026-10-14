"""
Modèles ORM SQLAlchemy — reflètent exactement le modèle de données défini
dans le mémoire (chapitre Conception) : users, datasets, model_versions,
monitoring_runs, alerts, retraining_jobs, prediction_logs.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Float, Boolean, DateTime, ForeignKey, Text, Enum, JSON, Integer
)
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class RoleEnum(str, enum.Enum):
    admin = "admin"
    user = "user"


class DomainEnum(str, enum.Enum):
    finance = "finance"
    sante = "sante"
    agriculture = "agriculture"


class ModelStatusEnum(str, enum.Enum):
    """
    Cycle de vie d'une version de modèle :
      en_test       -> modèle fraîchement entraîné, en cours d'évaluation ;
      staging       -> validé en pré-production, prêt à être promu (non servi aux utilisateurs) ;
      en_production -> servi aux utilisateurs et surveillé (un seul par dataset) ;
      archive       -> ancienne version retirée, conservée pour l'historique et la comparaison.
    """
    en_test = "en_test"
    staging = "staging"
    en_production = "en_production"
    archive = "archive"


class SeverityEnum(str, enum.Enum):
    faible = "faible"
    moyenne = "moyenne"
    critique = "critique"


class AlertStatusEnum(str, enum.Enum):
    en_attente = "en_attente"
    validee = "validee"
    rejetee = "rejetee"
    expiree = "expiree"


class JobStatusEnum(str, enum.Enum):
    en_cours = "en_cours"
    reussi = "reussi"
    echoue = "echoue"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(RoleEnum), default=RoleEnum.user, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    prediction_logs = relationship("PredictionLog", back_populates="user")
    reviewed_alerts = relationship("Alert", back_populates="reviewer")


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    domain = Column(Enum(DomainEnum), nullable=False)
    source_path = Column(String, nullable=True)
    target_column = Column(String, nullable=True)  # colonne à prédire, ex. "isFraud"
    time_column = Column(String, nullable=True)     # colonne temporelle, pour un split référence/courant chronologique
    created_at = Column(DateTime, default=datetime.utcnow)

    model_versions = relationship("ModelVersion", back_populates="dataset")


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(String, primary_key=True, default=gen_uuid)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=False)
    mlflow_run_id = Column(String, nullable=True)
    version_number = Column(Integer, nullable=False)
    status = Column(Enum(ModelStatusEnum), default=ModelStatusEnum.en_test)
    metrics = Column(JSON, nullable=True)  # {"accuracy":..., "f1":..., "recall":...}
    deployed_at = Column(DateTime, nullable=True)

    dataset = relationship("Dataset", back_populates="model_versions")
    monitoring_runs = relationship("MonitoringRun", back_populates="model_version")
    prediction_logs = relationship("PredictionLog", back_populates="model_version")


class MonitoringRun(Base):
    __tablename__ = "monitoring_runs"

    id = Column(String, primary_key=True, default=gen_uuid)
    model_version_id = Column(String, ForeignKey("model_versions.id"), nullable=False)
    executed_at = Column(DateTime, default=datetime.utcnow)
    drift_score = Column(Float, nullable=False)
    drift_detected = Column(Boolean, default=False)
    report_json = Column(JSON, nullable=True)  # sortie brute Evidently AI

    model_version = relationship("ModelVersion", back_populates="monitoring_runs")
    alert = relationship("Alert", back_populates="monitoring_run", uselist=False)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String, primary_key=True, default=gen_uuid)
    monitoring_run_id = Column(String, ForeignKey("monitoring_runs.id"), nullable=False)
    triggered_at = Column(DateTime, default=datetime.utcnow)
    severity = Column(Enum(SeverityEnum), nullable=False)
    status = Column(Enum(AlertStatusEnum), default=AlertStatusEnum.en_attente)
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    comment = Column(Text, nullable=True)

    monitoring_run = relationship("MonitoringRun", back_populates="alert")
    reviewer = relationship("User", back_populates="reviewed_alerts")
    retraining_job = relationship("RetrainingJob", back_populates="alert", uselist=False)


class RetrainingJob(Base):
    __tablename__ = "retraining_jobs"

    id = Column(String, primary_key=True, default=gen_uuid)
    alert_id = Column(String, ForeignKey("alerts.id"), nullable=True)
    dataset_id = Column(String, ForeignKey("datasets.id"), nullable=True)  # pour les jobs nés d'un entraînement initial (sans alerte)
    triggered_by = Column(String, ForeignKey("users.id"), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    new_model_version_id = Column(String, ForeignKey("model_versions.id"), nullable=True)
    status = Column(Enum(JobStatusEnum), default=JobStatusEnum.en_cours)
    error_message = Column(Text, nullable=True)
    # Suivi de l'entraînement : avancement en %, étape en cours, et résultats par algorithme
    # (configuration choisie, métriques de chaque algorithme, meilleur modèle...).
    progress = Column(Integer, default=0)
    progress_label = Column(String, nullable=True)
    training_results = Column(JSON, nullable=True)

    alert = relationship("Alert", back_populates="retraining_job")


class AppSetting(Base):
    """Paramètres de l'application modifiables depuis la page Paramètres (clé -> valeur JSON)."""
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PredictionLog(Base):
    __tablename__ = "prediction_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    model_version_id = Column(String, ForeignKey("model_versions.id"), nullable=False)
    input_payload = Column(JSON, nullable=False)
    prediction = Column(String, nullable=False)
    shap_explanation = Column(JSON, nullable=True)
    probability = Column(Float, nullable=True)  # score du modèle (probabilité de la classe suivie)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="prediction_logs")
    model_version = relationship("ModelVersion", back_populates="prediction_logs")


class AuditLog(Base):
    """
    Journal centralisé des actions effectuées sur la plateforme (page
    'Journal d'audit' de la maquette). Certaines informations existent déjà
    de façon éparse (Alert.reviewed_by, RetrainingJob.triggered_by...), mais
    cette table les rassemble chronologiquement, avec les actions qui n'ont
    pas d'autre table dédiée (connexion, création de compte, désactivation,
    import de dataset, déploiement manuel d'une version...).
    """
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=gen_uuid)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)  # nullable : actions système (planificateur)
    action = Column(String, nullable=False)   # ex. "alert.validated", "user.created"
    target = Column(String, nullable=True)    # description lisible de la cible, ex. "Alerte #1 — purchase_hour"
    details = Column(JSON, nullable=True)      # contexte additionnel libre

    user = relationship("User")
