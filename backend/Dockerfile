FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Dossiers d'écriture (base SQLite, uploads, MLflow). Sur un hébergeur gratuit
# ils sont éphémères : les données repartent de zéro à chaque redémarrage.
RUN mkdir -p /data && chmod -R 777 /data
ENV DATABASE_URL=sqlite:////data/driftguard.db \
    MLFLOW_TRACKING_URI=sqlite:////data/mlflow.db \
    MLFLOW_ARTIFACT_ROOT=/data/mlruns \
    DATASET_UPLOAD_DIR=/data/uploads

EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
