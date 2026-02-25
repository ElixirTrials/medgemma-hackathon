# Deploy API Service to Google Cloud Run

These steps assume you have a GCP project with billing enabled, `gcloud` CLI installed and authenticated, and (for production) a PostgreSQL database (e.g. Cloud SQL) and optional Vertex AI endpoint.

## 1. Prerequisites

- **gcloud CLI**: [Install](https://cloud.google.com/sdk/docs/install) and log in:
  ```bash
  gcloud auth login
  gcloud auth application-default login
  ```
- **Project**: Set your project and region:
  ```bash
  export PROJECT_ID=your-gcp-project-id
  export REGION=us-central1
  gcloud config set project $PROJECT_ID
  ```

## 2. Enable required APIs

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com
```

If you use **Cloud SQL** for the database:

```bash
gcloud services enable sqladmin.googleapis.com
```

If you use **Vertex AI** (MedGemma):

```bash
gcloud services enable aiplatform.googleapis.com
```

## 3. Create Artifact Registry repository

```bash
gcloud artifacts repositories create api-service \
  --repository-format=docker \
  --location=$REGION \
  --description="Docker images for API service"
```

## 4. Build and push the image

From the **repository root** (the Dockerfile expects monorepo context):

```bash
cd /path/to/medgemma-hackathon-main

# Build with Cloud Build and push to Artifact Registry
gcloud builds submit --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/api-service/api:latest .
```

Use the api-service Dockerfile by passing the dockerfile path. Default `Dockerfile` at repo root may not be the API one; the repo has the Dockerfile under `services/api-service/`:

```bash
gcloud builds submit \
  --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/api-service/api:latest \
  -f services/api-service/Dockerfile .
```

The build context is the current directory (repo root), which matches what the Dockerfile expects (`COPY pyproject.toml uv.lock`, `COPY libs/`, `COPY services/`).

## 5. Database (Cloud SQL or other)

You need a PostgreSQL instance and a connection name for Cloud Run.

- **Cloud SQL**: Create an instance, create a database and user, then note the **connection name** (`project:region:instance`). Use the [Cloud SQL Auth Proxy](https://cloud.google.com/sql/docs/postgres/connect-run) or a private IP + VPC connector for Cloud Run.
- **Connection string**: Build `DATABASE_URL` in the form:
  ```text
  postgresql://USER:PASSWORD@/DATABASE?host=/cloudsql/CONNECTION_NAME
  ```
  for Unix socket (recommended with Cloud SQL). For private IP or public (not recommended), use the host/port instead.

Store the database password in **Secret Manager** (recommended):

```bash
echo -n "your-db-password" | gcloud secrets create db-password --data-file=-
```

## 6. Deploy to Cloud Run

Minimal deploy with environment variables (replace placeholders and add any other env vars you need):

```bash
gcloud run deploy api \
  --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/api-service/api:latest \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars "ENVIRONMENT=production" \
  --set-env-vars "DATABASE_URL=postgresql://USER:PASSWORD@/DBNAME?host=/cloudsql/PROJECT:REGION:INSTANCE" \
  --set-env-vars "SESSION_SECRET=your-long-random-session-secret" \
  --set-env-vars "JWT_SECRET_KEY=your-long-random-jwt-secret" \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID}" \
  --set-env-vars "GCP_REGION=${REGION}"
```

If you use **Cloud SQL** with a Unix socket, add the Cloud SQL connection and ensure the service account has Cloud SQL Client:

```bash
gcloud run deploy api \
  --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/api-service/api:latest \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --add-cloudsql-instances PROJECT:REGION:INSTANCE \
  --set-env-vars "ENVIRONMENT=production" \
  --set-env-vars "DATABASE_URL=postgresql://USER:SECRET_PLACEHOLDER@/DBNAME?host=/cloudsql/PROJECT:REGION:INSTANCE" \
  --set-env-vars "SESSION_SECRET=..." \
  --set-env-vars "JWT_SECRET_KEY=..." \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID}" \
  --set-env-vars "GCP_REGION=${REGION}"
```

Then use **Secret Manager** for the DB password (see step 7).

### Required environment variables (production)

| Variable | Description |
|----------|-------------|
| `ENVIRONMENT` | Set to `production` (enables production checks). |
| `DATABASE_URL` | PostgreSQL URL (Cloud SQL or other). |
| `SESSION_SECRET` | Long random string for session middleware (no default in prod). |
| `JWT_SECRET_KEY` | Long random string for JWT signing (no default in prod). |

### Optional (features)

| Variable | Description |
|----------|-------------|
| `GCP_PROJECT_ID` | GCP project (for Vertex / GCS). |
| `GCP_REGION` | Region (e.g. `europe-west4`). |
| `VERTEX_ENDPOINT_ID` | Vertex AI endpoint for MedGemma. |
| `MODEL_BACKEND` | `vertex` to use Vertex MedGemma. |
| `GOOGLE_API_KEY` | Gemini Developer API key (extraction, etc.). |
| `GEMINI_MODEL_NAME` | e.g. `gemini-2.5-flash`. |
| `UMLS_API_KEY` | For UMLS terminology grounding. |
| `OMOP_VOCAB_URL` | PostgreSQL URL for OMOP vocabulary DB. |
| `GCS_BUCKET_NAME` | GCS bucket for uploads (or `USE_LOCAL_STORAGE=1` for dev). |
| `CORS_ORIGINS` | Comma-separated allowed origins. |
| `MLFLOW_TRACKING_URI` | MLflow server URL (optional). |

**Making `/health` report everything available:** To get `gcs: "ok"` and `omop_vocab: "ok"`, set `GCS_BUCKET_NAME` (and do not set `USE_LOCAL_STORAGE`), set `OMOP_VOCAB_URL` to a PostgreSQL database with the OMOP vocabulary loaded, and ensure the Cloud Run service account has Storage access on the bucket. The root repo [DEPLOYMENT.md](../../DEPLOYMENT.md) section **4.6** has step-by-step instructions (create bucket, IAM, OMOP options).

## 7. Use Secret Manager for sensitive values (recommended)

Create secrets and grant the Cloud Run service account access:

```bash
# Create secrets (one-time)
echo -n "your-db-password" | gcloud secrets create db-password --data-file=-
echo -n "your-session-secret" | gcloud secrets create session-secret --data-file=-
echo -n "your-jwt-secret" | gcloud secrets create jwt-secret --data-file=-

# Deploy with secrets (reference by secret name + version)
gcloud run deploy api \
  --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/api-service/api:latest \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --add-cloudsql-instances PROJECT:REGION:INSTANCE \
  --set-env-vars "ENVIRONMENT=production,GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION}" \
  --set-secrets "DATABASE_URL=db-url-secret:latest" \
  --set-secrets "SESSION_SECRET=session-secret:latest,JWT_SECRET_KEY=jwt-secret:latest"
```

For `DATABASE_URL` you can either store the full URL in one secret (`db-url-secret`) or build the URL from env vars and only store the password in a secret (e.g. inject `DB_PASSWORD` and set `DATABASE_URL` in the app from `DB_PASSWORD` + fixed user/db/host).

## 8. IAM for Vertex AI and Cloud SQL

Cloud Run uses a service account (default: `PROJECT_NUMBER-compute@developer.gserviceaccount.com`). Grant it:

- **Vertex AI**: so the service can call the Vertex endpoint:
  ```bash
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/aiplatform.user"
  ```
- **Cloud SQL Client** (if using Cloud SQL):
  ```bash
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/cloudsql.client"
  ```
- **Secret Manager** (if using secrets):
  ```bash
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
  ```

Replace `PROJECT_NUMBER` with your project number (`gcloud projects describe $PROJECT_ID --format='value(projectNumber)'`).

## 9. Verify the API

After deploy, Cloud Run prints the service URL. Use these commands to confirm the API is working.

**1. Get the service URL**

```bash
export API_URL=$(gcloud run services describe api --region $REGION --format='value(status.url)')
echo $API_URL
```

**2. If the service allows unauthenticated access** (you added `allUsers` as run.invoker):

```bash
curl -s "$API_URL/"
curl -s "$API_URL/health" | jq .
```

**3. If the service requires authentication** (default when no public invoker):

```bash
TOKEN=$(gcloud auth print-identity-token)
curl -s -H "Authorization: Bearer $TOKEN" "$API_URL/"
curl -s -H "Authorization: Bearer $TOKEN" "$API_URL/health" | jq .
```

**Expected responses**

- `GET /` → `{"message":"Welcome to the API Service"}`
- `GET /health` → JSON with `"status":"healthy"` and `"checks":{"database":"connected",...}`. Other checks (e.g. `omop_vocab`, `gcs`) may be `"unavailable"` until configured; the main DB must be `"connected"`.

## 10. Revisions and traffic

To deploy a new revision (e.g. after pushing a new image):

```bash
gcloud run deploy api \
  --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/api-service/api:latest \
  --region $REGION
```

Existing env vars and secrets are preserved unless you pass `--set-env-vars` / `--set-secrets` again (which replace the whole env or secrets set if you use `--clear-env-vars` / `--clear-secrets`). Omit them to keep current config.

---

**Summary**

1. Enable APIs (Run, Artifact Registry, Cloud Build; optionally Cloud SQL, Vertex).
2. Create Artifact Registry repo; build and push image from repo root with `-f services/api-service/Dockerfile`.
3. Create DB (e.g. Cloud SQL) and optional secrets in Secret Manager.
4. Deploy with `gcloud run deploy` (env vars and/or secrets, Cloud SQL connection if needed).
5. Grant the Cloud Run service account roles for Vertex, Cloud SQL, and Secret Manager as needed.
