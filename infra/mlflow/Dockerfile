# MLflow tracking server for Cloud Run.
# Uses same Cloud SQL (Postgres) for metadata and GCS for artifacts.
# Env: MLFLOW_BACKEND_STORE_URI, MLFLOW_DEFAULT_ARTIFACT_ROOT (set at deploy).
FROM ghcr.io/mlflow/mlflow:v2.19.0

# PostgreSQL backend requires psycopg2 (not included in the base image)
RUN pip install --no-cache-dir psycopg2-binary

# Cloud Run sets PORT=8080
ENV PORT=8080
EXPOSE 8080

# Run MLflow server; backend and artifact root from env (set by Cloud Run).
CMD ["sh", "-c", "mlflow server --host 0.0.0.0 --port ${PORT} --backend-store-uri \"${MLFLOW_BACKEND_STORE_URI}\" --default-artifact-root \"${MLFLOW_DEFAULT_ARTIFACT_ROOT}\""]
