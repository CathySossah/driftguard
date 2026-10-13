"""
Mini-migration : ajoute les colonnes apparues après la création de la base.
`Base.metadata.create_all()` crée les tables manquantes mais ne modifie pas
une table existante ; sans cela, une base SQLite créée avec une version
précédente de l'application ferait planter les requêtes. (Pour des
évolutions plus nombreuses, passer à Alembic.)
"""
import logging

from sqlalchemy import inspect, text

from app.database import engine

logger = logging.getLogger("driftguard.migrations")

_COLUMNS = [
    ("prediction_logs", "probability", "FLOAT"),
]


def ensure_schema() -> None:
    try:
        inspector = inspect(engine)
        for table, column, ddl_type in _COLUMNS:
            if table not in inspector.get_table_names():
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            if column not in existing:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
                logger.info("Colonne ajoutée : %s.%s", table, column)
    except Exception:
        logger.exception("Mise à jour du schéma impossible")
