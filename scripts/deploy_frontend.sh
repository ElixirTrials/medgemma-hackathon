#!/bin/bash
#
# Deploy the latest frontend code to Cloud Run (europe-west4).
# Run from the repository root, or the script will cd to the repo root automatically.
# Usage: make deploy-frontend  (or  bash scripts/deploy_frontend.sh)
#
# Configuration is read from the repo root .env (GCP_PROJECT_ID, GCP_REGION, API_SERVICE_URL).
# Prerequisites: gcloud CLI installed and authenticated.
#
# After deploy, the live app is served at:
#   https://frontend-<PROJECT_NUMBER>.<REGION>.run.app/
#
# See DEPLOYMENT.md section 5 for full details.

set -e

# --- Repo root (script may be run from instructions/) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- Configuration: defaults, then override from .env ---
REGION="${REGION:-europe-west4}"
PROJECT_ID="${PROJECT_ID:-}"
API_SERVICE_URL="${API_SERVICE_URL:-}"
BASE_PATH="${BASE_PATH:-/}"

if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  source "$REPO_ROOT/.env"
  set +a
  # Prefer GCP_* from .env for deploy
  [ -n "$GCP_PROJECT_ID" ] && PROJECT_ID="$GCP_PROJECT_ID"
  [ -n "$GCP_REGION" ] && REGION="$GCP_REGION"
  # Use API_SERVICE_URL from .env only if it looks like a real URL (not placeholder)
  if [ -n "$API_SERVICE_URL" ] && [[ "$API_SERVICE_URL" == *"XXXXX"* ]]; then
    API_SERVICE_URL=""
  fi
fi

# Env / CLI still override
REGION="${REGION:-europe-west4}"
PROJECT_ID="${PROJECT_ID:-$GCP_PROJECT_ID}"

if [ -z "$PROJECT_ID" ]; then
  echo "Error: PROJECT_ID not set. Set GCP_PROJECT_ID or PROJECT_ID in .env or export PROJECT_ID." >&2
  exit 1
fi

echo "Using REGION=$REGION PROJECT_ID=$PROJECT_ID"
if [ -z "$API_SERVICE_URL" ]; then
  echo "Fetching API service URL..."
  API_SERVICE_URL="$(gcloud run services describe api --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')"
  if [ -z "$API_SERVICE_URL" ]; then
    echo "Error: Could not get API URL. Is the 'api' service deployed in $REGION? Set API_SERVICE_URL manually if needed." >&2
    exit 1
  fi
  echo "API_SERVICE_URL=$API_SERVICE_URL"
fi

cd "$REPO_ROOT"

echo "Building frontend image (Cloud Build)..."
gcloud builds submit \
  --project "$PROJECT_ID" \
  --config=cloudbuild-frontend.yaml \
  --substitutions=_VITE_API_URL="${API_SERVICE_URL}",_BASE_PATH="${BASE_PATH}",_REGION="${REGION}" \
  .

echo "Deploying frontend to Cloud Run..."
gcloud run deploy frontend \
  --project "$PROJECT_ID" \
  --image "${REGION}-docker.pkg.dev/${PROJECT_ID}/app-images/frontend:latest" \
  --region "$REGION" \
  --platform managed \
  --no-invoker-iam-check

FRONTEND_URL="$(gcloud run services describe frontend --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)' 2>/dev/null)" || true
echo "Done. Frontend URL: ${FRONTEND_URL:-unknown}"
