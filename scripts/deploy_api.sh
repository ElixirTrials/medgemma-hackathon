#!/bin/bash
#
# Rebuild and deploy the API to Cloud Run.
# Run from repo root, or the script will cd to the repo root.
# Usage: make deploy-api  (or  bash scripts/deploy_api.sh)
# Loads environment variables from the repo root .env (GCP_PROJECT_ID, GCP_REGION,
# CONNECTION_NAME, CORS_ORIGINS, GCS_BUCKET_NAME, VERTEX_ENDPOINT_ID, etc.).
#
# See DEPLOYMENT.md sections 4.2, 4.4, 4.4b for full details.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load .env first so all deploy variables can come from there
if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$REPO_ROOT/.env"
    set +a
fi

# Apply defaults only where still unset (env / CLI override .env)
REGION="${REGION:-${GCP_REGION:-europe-west4}}"
PROJECT_ID="${PROJECT_ID:-$GCP_PROJECT_ID}"
CONNECTION_NAME="${CONNECTION_NAME:-}"
GCS_BUCKET_NAME="${GCS_BUCKET_NAME:-}"
VERTEX_ENDPOINT_ID="${VERTEX_ENDPOINT_ID:-}"
GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-}"
GOOGLE_CLIENT_SECRET="${GOOGLE_CLIENT_SECRET:-}"
# Use FRONTEND_URL for deploy CORS when set (so .env can keep CORS_ORIGINS for local dev)
CORS_ORIGINS="${FRONTEND_URL:-$CORS_ORIGINS}"

if [ -z "$PROJECT_ID" ]; then
    echo "Error: PROJECT_ID not set. Set GCP_PROJECT_ID in .env or export PROJECT_ID." >&2
    exit 1
fi

# Deploy requires these; set in .env or export before running
if [ -z "$CONNECTION_NAME" ]; then
    echo "Error: CONNECTION_NAME not set (Cloud SQL connection name). Set in .env or export." >&2
    exit 1
fi
if [ -z "$CORS_ORIGINS" ]; then
    echo "Error: CORS_ORIGINS not set (frontend URL). Set in .env or export." >&2
    exit 1
fi

# Prefer GCS_BUCKET_NAME_PROD for deploy (local .env GCS_BUCKET_NAME may be the cloudbuild bucket)
GCS_BUCKET_NAME="${GCS_BUCKET_NAME_PROD:-${GCS_BUCKET_NAME:-${PROJECT_ID}-api-protocols}}"

if [ -z "$VERTEX_ENDPOINT_ID" ]; then
    echo "Error: VERTEX_ENDPOINT_ID not set. Set in .env or export." >&2
    exit 1
fi

if [ -z "$GOOGLE_CLIENT_ID" ] || [ -z "$GOOGLE_CLIENT_SECRET" ]; then
    echo "Warning: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not set. Google OAuth login will be unavailable." >&2
fi

# Auto-resolve MLflow URL from Cloud Run if not explicitly set
MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-}"
if [ -z "$MLFLOW_TRACKING_URI" ]; then
    MLFLOW_TRACKING_URI=$(gcloud run services describe mlflow \
        --region "$REGION" --project "$PROJECT_ID" \
        --format='value(status.url)' 2>/dev/null || true)
    if [ -n "$MLFLOW_TRACKING_URI" ]; then
        echo "Auto-resolved MLFLOW_TRACKING_URI: $MLFLOW_TRACKING_URI"
    else
        echo "Warning: No MLflow service found. Tracing will be disabled (protocol processing unaffected)." >&2
    fi
fi

cd "$REPO_ROOT"

echo "Building API image (Cloud Build)..."
gcloud builds submit \
    --project "$PROJECT_ID" \
    --config=cloudbuild-api.yaml \
    --substitutions=_REGION="${REGION}" \
    .

echo "Deploying API to Cloud Run..."
gcloud run deploy api \
    --project "$PROJECT_ID" \
    --image "${REGION}-docker.pkg.dev/${PROJECT_ID}/app-images/api:latest" \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --no-cpu-throttling \
    --add-cloudsql-instances "$CONNECTION_NAME" \
    --startup-probe=httpGet.path=/health,initialDelaySeconds=5,periodSeconds=10,failureThreshold=6 \
    --set-env-vars "^||^ENVIRONMENT=production||GCP_PROJECT_ID=${PROJECT_ID}||GCP_REGION=${REGION}||MODEL_BACKEND=vertex||VERTEX_ENDPOINT_ID=${VERTEX_ENDPOINT_ID}||GCS_BUCKET_NAME=${GCS_BUCKET_NAME}||USE_LOCAL_STORAGE=0||CORS_ORIGINS=${CORS_ORIGINS}||GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}||GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}||MLFLOW_TRACKING_URI=${MLFLOW_TRACKING_URI}||MLFLOW_ENABLE_ASYNC_TRACE_LOGGING=true" \
    --set-secrets "DATABASE_URL=db-url:latest,SESSION_SECRET=api-session-secret:latest,JWT_SECRET_KEY=api-jwt-secret:latest,OMOP_VOCAB_URL=omop-vocab-url:latest"

# Post-deploy health check
API_URL=$(gcloud run services describe api \
    --region "$REGION" --project "$PROJECT_ID" \
    --format='value(status.url)' 2>/dev/null)

echo "API URL: ${API_URL:-unknown}"

if [ -n "$API_URL" ]; then
    echo "Verifying deployment health..."
    HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 "${API_URL}/health" 2>/dev/null || echo "000")
    if [ "$HTTP_STATUS" = "200" ]; then
        echo "Health check PASSED (HTTP $HTTP_STATUS)"
    else
        echo "Warning: Health check returned HTTP $HTTP_STATUS (new revision may still be starting)" >&2
    fi
else
    echo "Warning: Could not determine API URL for health check" >&2
fi
