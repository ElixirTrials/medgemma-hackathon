# Gemini & Vertex AI authentication

This project uses two Google auth paths:

| Use case | Auth method | Env / config |
|----------|-------------|--------------|
| **Gemini API** (extraction, criterion rerun, grounding structuring) | API key | `GOOGLE_API_KEY` (see below) |
| **Vertex AI** (MedGemma endpoint, GCS) | Application Default Credentials (ADC) | `gcloud auth application-default login` + quota project |

## 1. Gemini API (GOOGLE_API_KEY)

To **use Google Cloud credits** (recommended): create the API key in your GCP project so usage bills to that project:

1. In [Cloud Console](https://console.cloud.google.com/apis/credentials) select the same project as `GCP_PROJECT_ID`.
2. Ensure **Generative Language API** is enabled: [Enable API](https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com).
3. **Create credentials** → **API key**. (Optional: restrict the key to “Generative Language API”.)
4. Set `GOOGLE_API_KEY=` in `.env` to that key.

Alternative: you can use a key from [Google AI Studio](https://aistudio.google.com/apikey); billing then uses the project linked to that key (may not use your GCP credits).

If `.env` (or your API key) was ever committed or exposed, create a new key and revoke the old one.

## 2. Vertex AI & GCS (Application Default Credentials)

Vertex AI and Google Cloud Storage use **Application Default Credentials**. For local development:

### One-time: create ADC

```bash
gcloud auth application-default login
```

This opens a browser and writes credentials to `~/.config/gcloud/application_default_credentials.json`. Do **not** set `GOOGLE_APPLICATION_CREDENTIALS` if you want to use these user credentials.

### Set the quota project

Without a quota project, Vertex/GCS calls can fail with 403 (billing/quota not attributed). Set the project that should be billed and quota-limited:

```bash
# From repo root; reads GCP_PROJECT_ID or GOOGLE_CLOUD_QUOTA_PROJECT from .env
make setup-adc
```

Or manually:

```bash
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
```

Your account must have `serviceusage.services.use` on that project. The same project should usually have Vertex AI and billing enabled.

### Optional: use a service account key

For CI or when user ADC is not desired, set:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

The quota project is then the project that owns the service account; you do not need `set-quota-project`.

## 3. Quotas

- **Gemini API (API key):** For Cloud Console keys, quotas and billing use your GCP project; adjust in [Quotas](https://console.cloud.google.com/iam-admin/quotas) (filter by “Generative Language API”). For AI Studio keys, use [AI Studio](https://aistudio.google.com/).
- **Vertex AI:** Quotas are per project in [Cloud Console → IAM & Admin → Quotas](https://console.cloud.google.com/iam-admin/quotas). Filter by “Vertex AI” or “AI Platform” and request increases if needed.

## 4. Quick check

- **Gemini API:** From repo root run `uv run python scripts/verify_gemini_access.py`. It uses `GOOGLE_API_KEY` from `.env` and calls Gemini with a simple prompt.
- **Vertex / ADC:** Run `make setup-adc` (after `gcloud auth application-default login`), then start the stack with `make run-dev` and trigger a flow that uses the MedGemma endpoint or GCS.
