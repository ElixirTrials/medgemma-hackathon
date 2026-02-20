# Gemini & Vertex AI Authentication

ElixirTrials supports two backends for Gemini model access: the **Gemini Developer API** (default) and **Vertex AI** (for MedGemma).

## Gemini Developer API (Default)

Used for criteria extraction, entity decomposition, logic detection, and ordinal resolution.

### Setup

1. Get an API key from [Google AI Studio](https://aistudio.google.com/apikey)
2. Add to `.env`:

```bash
GOOGLE_API_KEY=your-key-here
GEMINI_MODEL_NAME=gemini-2.5-flash   # default
```

### Verify

```bash
make verify-gemini
```

This runs `scripts/verify_gemini_access.py` which makes a test call to the Gemini API.

## Vertex AI (MedGemma)

Used for agentic grounding retry loop (MedGemma reasoning).

### Setup

1. Create a GCP project with Vertex AI enabled
2. Deploy MedGemma to a Vertex AI endpoint
3. Configure Application Default Credentials:

```bash
gcloud auth application-default login
make setup-adc    # Sets quota project from .env
```

4. Add to `.env`:

```bash
MODEL_BACKEND=vertex
GCP_PROJECT_ID=your-project-id
GCP_REGION=europe-west4
VERTEX_ENDPOINT_ID=your-endpoint-id
```

### ADC Setup Script

The `make setup-adc` command runs `scripts/setup-gcloud-adc.sh`, which:

1. Reads `GCP_PROJECT_ID` or `GOOGLE_CLOUD_QUOTA_PROJECT` from `.env`
2. Sets the quota project on your Application Default Credentials
3. Required when using user-level ADC (not service accounts) for Vertex AI

### Docker Compose

For Docker deployment, ADC credentials are mounted as a read-only volume:

```yaml
volumes:
  - ${GOOGLE_ADC_PATH:-~/.config/gcloud/application_default_credentials.json}:/tmp/keys/application_default_credentials.json:ro
environment:
  - GOOGLE_APPLICATION_CREDENTIALS=/tmp/keys/application_default_credentials.json
```

## Google OAuth (UI Login)

For the HITL UI authentication:

1. Create OAuth 2.0 credentials at [GCP Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials)
2. Set redirect URI to `http://localhost:8000/auth/callback`
3. Add to `.env`:

```bash
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
```

OAuth is optional for local development — the API works without it configured.

## Environment Variable Reference

| Variable | Required for | Default |
|----------|-------------|---------|
| `GOOGLE_API_KEY` | Gemini Developer API | — |
| `GEMINI_MODEL_NAME` | Gemini model selection | `gemini-2.5-flash` |
| `MODEL_BACKEND` | Backend selection | (Gemini Developer API) |
| `GCP_PROJECT_ID` | Vertex AI | — |
| `GCP_REGION` | Vertex AI | `europe-west4` |
| `VERTEX_ENDPOINT_ID` | MedGemma endpoint | — |
| `GOOGLE_CLIENT_ID` | OAuth login | — |
| `GOOGLE_CLIENT_SECRET` | OAuth login | — |
| `GCLOUD_PROFILE` | gcloud config profile | — |
| `MLFLOW_TRACKING_URI` | Experiment tracking | `http://localhost:5001` |
| `UMLS_API_KEY` | UMLS grounding | — |
