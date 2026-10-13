"""Schémas Pydantic : validation des requêtes/réponses de l'API."""
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, EmailStr, ConfigDict

from app.models import (
    RoleEnum, DomainEnum, ModelStatusEnum, SeverityEnum, AlertStatusEnum, JobStatusEnum
)

# Désactive l'avertissement Pydantic sur les champs préfixés "model_"
# (ex. model_version_id) : ce préfixe n'entre pas en conflit ici, il n'y a
# pas de champ lié à un LLM dans ce projet.
_base_config = ConfigDict(protected_namespaces=())


# ---------- Users / Auth ----------
class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    role: RoleEnum = RoleEnum.user
    # Code d'invitation requis pour créer un compte administrateur
    # (voir la variable d'environnement ADMIN_SIGNUP_CODE).
    admin_code: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    full_name: str
    email: EmailStr
    role: RoleEnum
    created_at: datetime
    is_active: bool


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ---------- Datasets ----------
class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    domain: DomainEnum
    source_path: Optional[str]
    target_column: Optional[str] = None
    time_column: Optional[str] = None
    created_at: datetime


class DatasetConfigure(BaseModel):
    """Désigne, après import, quelle colonne du CSV est la cible à prédire et
    (optionnellement) quelle colonne sert de repère temporel pour le split
    référence/courant utilisé par le monitoring de dérive."""
    target_column: str
    time_column: Optional[str] = None


# ---------- Model versions ----------
class ModelVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    dataset_id: str
    mlflow_run_id: Optional[str]
    version_number: int
    status: ModelStatusEnum
    metrics: Optional[dict]
    deployed_at: Optional[datetime]


# ---------- Monitoring ----------
class MonitoringRunCreate(BaseModel):
    model_config = _base_config
    model_version_id: str
    drift_score: float
    drift_detected: bool
    report_json: Optional[dict] = None


class MonitoringRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: str
    model_version_id: str
    executed_at: datetime
    drift_score: float
    drift_detected: bool
    report_json: Optional[dict]


# ---------- Alerts ----------
class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    monitoring_run_id: str
    triggered_at: datetime
    severity: SeverityEnum
    status: AlertStatusEnum
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    comment: Optional[str]


class AlertReview(BaseModel):
    approve: bool  # True = valider (déclenche le ré-entraînement), False = rejeter
    comment: Optional[str] = None


# ---------- Retraining ----------
class RetrainingJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    alert_id: Optional[str]
    triggered_by: Optional[str]
    started_at: datetime
    finished_at: Optional[datetime]
    new_model_version_id: Optional[str]
    status: JobStatusEnum
    error_message: Optional[str]


# ---------- Predictions ----------
class PredictionRequest(BaseModel):
    model_config = _base_config
    model_version_id: str
    input_payload: dict[str, Any]


class PredictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
    id: str
    prediction: str
    shap_explanation: Optional[dict]
    created_at: datetime
    probability: Optional[float] = None
    probability_label: Optional[str] = None
    model_version_id: Optional[str] = None


class PredictableModelOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    id: str
    version_number: int
    dataset_name: str
    domain: str
    metrics: Optional[dict] = None


class PredictionSchemaOut(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_version_id: str
    version_number: int
    dataset_name: str
    domain: str
    target_column: Optional[str] = None
    fields: list[dict]


# ---------- Audit ----------
class AuditLogOut(BaseModel):
    id: str
    created_at: datetime
    user_id: Optional[str]
    user_name: Optional[str] = None
    action: str
    target: Optional[str]
    details: Optional[dict]
