#!/usr/bin/env bash
# Set up Application Default Credentials (ADC) and quota project for Gemini/Vertex.
#
# Usage:
#   ./scripts/setup-gcloud-adc.sh   # reads .env for GCP_PROJECT_ID or GOOGLE_CLOUD_QUOTA_PROJECT
#   ./scripts/setup-gcloud-adc.sh my-project-id
#
# Prerequisites:
#   - gcloud CLI installed and in PATH
#   - For first-time setup: run `gcloud auth application-default login` (opens browser)
#   - Your account must have serviceusage.services.use on the quota project

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"

# ADC file location (same as gcloud SDK)
if [[ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" && -f "$GOOGLE_APPLICATION_CREDENTIALS" ]]; then
  echo "GOOGLE_APPLICATION_CREDENTIALS is set to a file; ADC from gcloud is not used."
  echo "Quota project for that key is the project that owns the service account."
  exit 0
fi

ADC_FILE="${HOME}/.config/gcloud/application_default_credentials.json"
if [[ "$(uname -s)" == "Darwin" ]] && [[ -n "${HOME:-}" ]]; then
  : # use $HOME
elif [[ -n "${APPDATA:-}" ]]; then
  ADC_FILE="${APPDATA}/gcloud/application_default_credentials.json"
fi

if [[ ! -f "$ADC_FILE" ]]; then
  echo "Application Default Credentials not found at: $ADC_FILE"
  echo ""
  echo "Run the following (opens a browser to sign in):"
  echo "  gcloud auth application-default login"
  echo ""
  echo "Then run this script again to set the quota project."
  exit 1
fi

# Resolve quota project: arg > GOOGLE_CLOUD_QUOTA_PROJECT > GCP_PROJECT_ID from .env
QUOTA_PROJECT="${1:-}"
if [[ -z "$QUOTA_PROJECT" && -f "$ENV_FILE" ]]; then
  QUOTA_PROJECT=$(grep -E '^GOOGLE_CLOUD_QUOTA_PROJECT=' "$ENV_FILE" | cut -d= -f2 | tr -d '\r' || true)
fi
if [[ -z "$QUOTA_PROJECT" && -f "$ENV_FILE" ]]; then
  QUOTA_PROJECT=$(grep -E '^GCP_PROJECT_ID=' "$ENV_FILE" | cut -d= -f2 | tr -d '\r' || true)
fi

if [[ -z "$QUOTA_PROJECT" ]]; then
  echo "Quota project not set. Either:"
  echo "  1. Pass project ID: $0 YOUR_PROJECT_ID"
  echo "  2. Set GOOGLE_CLOUD_QUOTA_PROJECT= or GCP_PROJECT_ID= in .env"
  exit 1
fi

echo "Setting ADC quota project to: $QUOTA_PROJECT"
gcloud auth application-default set-quota-project "$QUOTA_PROJECT"
echo "Done. Vertex AI and other Google client libraries will use this project for billing and quota."
