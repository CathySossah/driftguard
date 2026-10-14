"""
Alertes par e-mail : prévient les administrateurs lorsqu'une alerte de drift est créée.

Trois modes d'envoi, choisis selon les variables d'environnement (priorité : Resend, Brevo, SMTP) :
  1. API HTTPS de Resend (gratuit, sans carte bancaire) :
        RESEND_API_KEY  (EMAIL_FROM facultatif : par défaut « DriftGuard <onboarding@resend.dev> »)
        Sans domaine vérifié chez Resend, les e-mails ne peuvent être envoyés qu'à l'adresse du compte Resend.
  2. API HTTPS de Brevo :
        BREVO_API_KEY + EMAIL_FROM  (EMAIL_FROM doit être une adresse expéditrice validée chez Brevo)
  3. SMTP classique :
        SMTP_HOST (+ SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_USE_TLS) + EMAIL_FROM
Attention : Render bloque les ports SMTP (25/465/587) sur les services gratuits ; il faut alors un mode HTTPS
(1 ou 2, port 443) ou un plan payant.

Autres variables : FRONTEND_URL (lien dans l'e-mail), ALERT_EXTRA_RECIPIENTS (adresses supplémentaires,
séparées par des virgules). Ce module n'importe que la bibliothèque standard au chargement ; l'envoi ne
lève jamais d'exception vers le monitoring (une panne d'e-mail ne doit pas bloquer la surveillance).
"""
import json
import logging
import os
import smtplib
import threading
import urllib.error
import urllib.request
from email.message import EmailMessage
from typing import Any, Optional

logger = logging.getLogger("driftguard.email")

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
RESEND_URL = "https://api.resend.com/emails"
RESEND_DEFAULT_SENDER = "onboarding@resend.dev"
USER_AGENT = "DriftGuard/1.0"  # Resend (Cloudflare) refuse les requêtes sans User-Agent explicite


class EmailError(Exception):
    """Échec d'envoi (message lisible, affiché à l'administrateur lors du test)."""


def provider() -> Optional[str]:
    """'resend', 'brevo', 'smtp' ou None si aucun service d'envoi n'est configuré."""
    if os.getenv("RESEND_API_KEY"):
        return "resend"  # l'expéditeur a une valeur par défaut : EMAIL_FROM n'est pas obligatoire
    if not os.getenv("EMAIL_FROM"):
        return None
    if os.getenv("BREVO_API_KEY"):
        return "brevo"
    if os.getenv("SMTP_HOST"):
        return "smtp"
    return None


def _send_brevo(recipients: list[str], subject: str, text: str, timeout: int) -> None:
    sender = os.environ["EMAIL_FROM"]
    payload = {
        "sender": {"name": "DriftGuard", "email": sender},
        "to": [{"email": r} for r in recipients],
        "subject": subject,
        "textContent": text,
    }
    request = urllib.request.Request(
        BREVO_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "api-key": os.environ["BREVO_API_KEY"],
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            pass
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise EmailError(f"Brevo a refusé l'envoi (HTTP {e.code}) : {detail}")
    except Exception as e:
        raise EmailError(f"Brevo injoignable : {e}")


def _resend_sender() -> str:
    """Expéditeur Resend : EMAIL_FROM s'il est défini, sinon l'adresse de test fournie par Resend."""
    sender = (os.getenv("EMAIL_FROM") or RESEND_DEFAULT_SENDER).strip()
    return sender if "<" in sender else f"DriftGuard <{sender}>"


def _send_resend(recipients: list[str], subject: str, text: str, timeout: int) -> None:
    """
    Un envoi par destinataire : avec l'adresse de test de Resend (sans domaine vérifié), seul le propriétaire du
    compte Resend peut recevoir des e-mails ; les autres destinataires sont refusés (HTTP 403). L'envoi est donc
    considéré comme réussi dès qu'au moins un destinataire a reçu le message.
    """
    sender = _resend_sender()
    delivered, errors = [], []
    for recipient in recipients:
        payload = {"from": sender, "to": [recipient], "subject": subject, "text": text}
        request = urllib.request.Request(
            RESEND_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout):
                pass
            delivered.append(recipient)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            hint = ""
            if e.code == 403 and RESEND_DEFAULT_SENDER in sender:
                hint = (" — sans domaine vérifié, Resend n'envoie qu'à l'adresse e-mail avec laquelle le compte "
                        "Resend a été créé")
            elif e.code in (401, 403) and "api" in detail.lower() and "key" in detail.lower():
                hint = " — vérifiez RESEND_API_KEY"
            errors.append(f"{recipient} : HTTP {e.code}{hint} ({detail})")
        except Exception as e:
            errors.append(f"{recipient} : Resend injoignable ({e})")
    if errors and not delivered:
        raise EmailError("Resend a refusé l'envoi — " + " ; ".join(errors))
    for err in errors:
        logger.warning("Resend : destinataire ignoré — %s", err)


def _send_smtp(recipients: list[str], subject: str, text: str, timeout: int) -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    user, password = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
    use_tls = os.getenv("SMTP_USE_TLS", "true").strip().lower() not in {"0", "false", "no", "non"}

    message = EmailMessage()
    message["From"] = os.environ["EMAIL_FROM"]
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(text)
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=timeout)
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
        with server:
            if port != 465 and use_tls:
                server.starttls()
            if user and password:
                server.login(user, password)
            server.send_message(message)
    except Exception as e:
        raise EmailError(f"Envoi SMTP impossible ({host}:{port}) : {e}")


def send_email(recipients: list[str], subject: str, text: str, timeout: int = 15) -> None:
    """Envoie un e-mail via le service configuré. Lève EmailError en cas de problème."""
    mode = provider()
    if mode is None:
        raise EmailError(
            "Aucun service d'e-mail configuré : définissez RESEND_API_KEY (gratuit), "
            "ou EMAIL_FROM avec BREVO_API_KEY / SMTP_HOST."
        )
    recipients = [r for r in recipients if r]
    if not recipients:
        raise EmailError("Aucun destinataire.")
    {"resend": _send_resend, "brevo": _send_brevo, "smtp": _send_smtp}[mode](recipients, subject, text, timeout)


def build_alert_email(
    dataset_name: str,
    version_number: int,
    severity: str,
    drift_score: float,
    alert_threshold: float,
    columns: dict[str, Any],
    link: str,
) -> tuple[str, str]:
    """Sujet et corps (texte brut, en français) de l'e-mail d'alerte."""
    drifted = [(name, info) for name, info in (columns or {}).items() if info.get("drifted")]
    lines = [
        "Bonjour,",
        "",
        f"DriftGuard a détecté une dérive des données pour le modèle v{version_number} du dataset « {dataset_name} ».",
        "",
        f"- Part de variables en dérive : {drift_score * 100:.0f} % (seuil d'alerte : {alert_threshold * 100:.0f} %)",
        f"- Sévérité : {severity}",
    ]
    if drifted:
        lines.append(f"- Variables en dérive ({len(drifted)}) :")
        for name, info in drifted[:10]:
            kind = "distance" if info.get("kind") == "distance" else "p-value"
            lines.append(f"    • {name} ({kind} = {info.get('p_value'):.4g}, seuil = {info.get('threshold'):.4g})")
        if len(drifted) > 10:
            lines.append(f"    … et {len(drifted) - 10} autre(s)")
    lines += [
        "",
        "Aucun ré-entraînement n'a été lancé : il n'a lieu qu'après validation de l'alerte par un administrateur.",
        f"Consulter et valider l'alerte : {link}",
        "",
        "— DriftGuard",
    ]
    subject = f"[DriftGuard] Alerte de drift ({severity}) — {dataset_name} v{version_number}"
    return subject, "\n".join(lines)


def notify_new_alert(alert_id: str) -> None:
    """
    Envoie l'e-mail d'une alerte nouvellement créée à tous les administrateurs. S'exécute dans un thread
    (voir start_alert_notification) avec sa propre session ; ne lève jamais d'exception.
    """
    try:
        if provider() is None:
            return
        from app import models
        from app.database import SessionLocal
        from app.services.settings_service import get_settings

        db = SessionLocal()
        try:
            settings = get_settings(db)
            if not settings.get("email_alerts_enabled", True):
                return
            alert = db.query(models.Alert).filter(models.Alert.id == alert_id).first()
            if alert is None:
                return
            run = db.query(models.MonitoringRun).filter(models.MonitoringRun.id == alert.monitoring_run_id).first()
            version = db.query(models.ModelVersion).filter(models.ModelVersion.id == run.model_version_id).first()
            dataset = db.query(models.Dataset).filter(models.Dataset.id == version.dataset_id).first()

            recipients = [u.email for u in db.query(models.User).filter(models.User.role == models.RoleEnum.admin).all()]
            recipients += [r.strip() for r in os.getenv("ALERT_EXTRA_RECIPIENTS", "").split(",") if r.strip()]
            recipients = list(dict.fromkeys(recipients))  # sans doublons

            subject, body = build_alert_email(
                dataset_name=dataset.name if dataset else "—",
                version_number=version.version_number,
                severity=alert.severity.value,
                drift_score=run.drift_score,
                alert_threshold=settings["alert_threshold"],
                columns=(run.report_json or {}).get("columns") or {},
                link=os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/") + "/alerts",
            )
        finally:
            db.close()
        send_email(recipients, subject, body)
        logger.info("E-mail d'alerte envoyé à %d administrateur(s)", len(recipients))
    except Exception:
        logger.warning("E-mail d'alerte non envoyé", exc_info=True)


def start_alert_notification(alert_id: str) -> None:
    """Lance l'envoi en arrière-plan : le monitoring n'attend jamais le serveur d'e-mail."""
    if provider() is None:
        return
    threading.Thread(target=notify_new_alert, args=(alert_id,), name="alert-email", daemon=True).start()
