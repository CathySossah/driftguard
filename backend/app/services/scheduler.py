"""
Planificateur (scheduler) du job de monitoring périodique — correspond au
composant 'Planificateur' du diagramme de déploiement (chapitre Conception).

En développement, APScheduler (in-process) suffit. En production à plus grande
échelle, ce rôle serait plutôt confié à Celery Beat ou à un cron déclenchant
POST /monitoring/run-now/{model_version_id} pour chaque modèle en production.
"""
import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app import models
from app.services.monitoring_service import process_monitoring_result, compute_drift_for_version

logger = logging.getLogger("driftguard.scheduler")

# Intervalle d'exécution. Valeur courte car ceci est une démonstration ;
# en production réelle, préférer "toutes les heures" ou "une fois par jour"
# (cf. page Paramètres de la maquette : fréquence configurable par l'admin).
MONITORING_INTERVAL_MINUTES = 10

scheduler = BackgroundScheduler()


def run_monitoring_cycle() -> None:
    """Exécute un cycle de monitoring pour chaque modèle actuellement en production."""
    db = SessionLocal()
    try:
        versions = (
            db.query(models.ModelVersion)
            .filter(models.ModelVersion.status == models.ModelStatusEnum.en_production)
            .all()
        )

        for version in versions:
            try:
                result = compute_drift_for_version(db, version)
                process_monitoring_result(
                    db,
                    model_version_id=version.id,
                    drift_score=result["drift_score"],
                    drift_detected=result["drift_detected"],
                    report_json=result["report_json"],
                )
                logger.info(
                    "Monitoring exécuté pour le modèle %s — drift_score=%.3f",
                    version.id, result["drift_score"],
                )
            except Exception:
                # Un modèle en erreur ne doit pas empêcher le monitoring des autres.
                db.rollback()
                logger.exception("Monitoring en échec pour le modèle %s", version.id)
    finally:
        db.close()


def start_scheduler() -> None:
    # Mode faible mémoire (hébergeur gratuit à 512 Mo) : pas de monitoring automatique,
    # le bouton « lancer maintenant » de la page Monitoring reste disponible.
    if os.getenv("LOW_MEMORY", "").strip().lower() in {"1", "true", "yes", "oui", "on"}:
        logger.info("LOW_MEMORY actif : planificateur de monitoring désactivé")
        return
    if not scheduler.running:
        scheduler.add_job(
            run_monitoring_cycle,
            "interval",
            minutes=MONITORING_INTERVAL_MINUTES,
            id="monitoring_cycle",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("Planificateur démarré (intervalle : %s min)", MONITORING_INTERVAL_MINUTES)


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
