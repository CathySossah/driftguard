"""
DriftGuard — API backend
Point d'entrée principal : initialise la base de données, configure CORS,
et branche l'ensemble des routers correspondant aux pages de la maquette.
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import auth, users, datasets, model_versions, monitoring, alerts, retraining, predictions, audit
from app.services.scheduler import start_scheduler, stop_scheduler
from app.migrations import ensure_schema
from app.bootstrap import run_bootstrap

# Crée les tables si elles n'existent pas encore (suffisant pour le développement ;
# utilisez Alembic pour les migrations en production).
Base.metadata.create_all(bind=engine)
ensure_schema()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Démarrage : comptes/démo automatiques puis planificateur ; arrêt : planificateur."""
    run_bootstrap()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(
    title="DriftGuard API",
    description="API de monitoring et de ré-entraînement automatisé pour la détection du data drift.",
    version="0.1.0",
    lifespan=lifespan,
)

# Origines autorisées : localhost par défaut (développement). En déploiement,
# définir CORS_ORIGINS avec l'URL du frontend, séparées par des virgules, ex :
#   CORS_ORIGINS=https://driftguard.vercel.app
CORS_ORIGINS = [
    o.strip().rstrip("/")
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(datasets.router)
app.include_router(model_versions.router)
app.include_router(monitoring.router)
app.include_router(alerts.router)
app.include_router(retraining.router)
app.include_router(predictions.router)
app.include_router(audit.router)


@app.get("/")
def root():
    return {"message": "DriftGuard API — voir /docs pour la documentation interactive."}
