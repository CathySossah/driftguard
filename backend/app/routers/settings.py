from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import get_current_user, require_admin
from app.services.audit_service import log_action
from app.services.settings_service import get_settings, update_settings, SettingsError
from app.services import email_service

router = APIRouter(prefix="/settings", tags=["Paramètres"])


@router.get("/", response_model=schemas.SettingsOut)
def read_settings(
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    """Seuils de surveillance du drift actuellement appliqués, et état des alertes par e-mail."""
    return {**get_settings(db), "email_provider": email_service.provider()}


@router.patch("/", response_model=schemas.SettingsOut)
def change_settings(
    payload: schemas.SettingsUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """Modifie les seuils (seuil d'alerte, seuil de p-value, seuils par variable). Réservé aux administrateurs."""
    try:
        updated = update_settings(
            db,
            alert_threshold=payload.alert_threshold,
            pvalue_threshold=payload.pvalue_threshold,
            variable_thresholds=payload.variable_thresholds,
            email_alerts_enabled=payload.email_alerts_enabled,
        )
    except SettingsError as e:
        raise HTTPException(status_code=422, detail=str(e))
    log_action(db, action="settings.updated", user_id=admin.id, target="Seuils de surveillance du drift",
               details=payload.model_dump(exclude_none=True))
    return {**updated, "email_provider": email_service.provider()}


@router.post("/test-email")
def send_test_email(
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """Envoie un e-mail de test à l'administrateur connecté pour vérifier la configuration d'envoi."""
    if email_service.provider() is None:
        raise HTTPException(
            status_code=400,
            detail="Aucun service d'e-mail configuré : définissez RESEND_API_KEY (gratuit) sur le serveur.",
        )
    try:
        email_service.send_email(
            [admin.email],
            "[DriftGuard] E-mail de test",
            "Ceci est un e-mail de test : les alertes de drift pourront vous être envoyées à cette adresse.\n\n— DriftGuard",
        )
    except email_service.EmailError as e:
        raise HTTPException(status_code=502, detail=str(e))
    log_action(db, action="settings.test_email", user_id=admin.id, target=f"E-mail de test envoyé à {admin.email}")
    return {"message": f"E-mail de test envoyé à {admin.email}."}


@router.get("/variables")
def monitored_variables(
    db: Session = Depends(get_db),
    _current_user: models.User = Depends(get_current_user),
):
    """
    Variables observées lors des derniers cycles de monitoring (une entrée par nom de variable),
    avec leur dernière valeur de test, le seuil appliqué et le seuil personnalisé éventuel.
    Alimente le tableau « Seuils par variable » de la page Paramètres.
    """
    current = get_settings(db)["variable_thresholds"]
    latest_by_version: dict[str, models.MonitoringRun] = {}
    for run in db.query(models.MonitoringRun).order_by(models.MonitoringRun.executed_at.desc()).all():
        latest_by_version.setdefault(run.model_version_id, run)

    variables: dict[str, dict] = {}
    for run in latest_by_version.values():
        for name, info in ((run.report_json or {}).get("columns") or {}).items():
            variables.setdefault(name, {
                "name": name,
                "kind": info.get("kind", "p_value"),
                "method": info.get("method"),
                "last_value": info.get("p_value"),
                "applied_threshold": info.get("threshold"),
                "default_threshold": info.get("default_threshold", info.get("threshold")),
                "drifted": info.get("drifted"),
                "custom_threshold": current.get(name),
            })
    # Seuils personnalisés dont la variable n'apparaît plus dans les derniers cycles : on les garde visibles.
    for name, value in current.items():
        variables.setdefault(name, {
            "name": name, "kind": None, "method": None, "last_value": None,
            "applied_threshold": value, "default_threshold": None, "drifted": None, "custom_threshold": value,
        })
    return sorted(variables.values(), key=lambda v: v["name"])
