# Deployment guide: Cloud SQL, API (Cloud Run), Frontend (Cloud Run)

This guide walks through deploying the full stack to Google Cloud: a small PostgreSQL (Cloud SQL), the API service on Cloud Run (with Vertex AI access), and the HITL frontend on Cloud Run. Order of operations and IAM are included so services can reach each other and Vertex.

**Prerequisites**

- Google Cloud project with billing enabled
- `gcloud` CLI installed and authenticated
- (Optional) Vertex AI endpoint for MedGemma already deployed

---

## 1. One-time setup: project and APIs

```bash
export PROJECT_ID=your-gcp-project-id
export REGION=europe-west4   # or e.g. us-central1

gcloud config set project $PROJECT_ID
gcloud auth login
gcloud auth application-default login
```

Enable required APIs:

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  sqladmin.googleapis.com \
  sql-component.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com
```

**If `gcloud builds submit` fails with 403 (storage.objects.get denied):** the default Compute Engine service account used by Cloud Build must be able to read the uploaded source in the Cloud Build bucket. Grant it Storage Object Viewer (once per project):

```bash
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
```

**If build logs are empty (REMOTE BUILD OUTPUT is blank) or you see "does not have permission to write logs":** grant the default compute service account **Cloud Build Builder** so build logs are written and visible:

```bash
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/cloudbuild.builds.builder"
```

(The **Cloud Build Builder** role lets the compute SA write build logs so REMOTE BUILD OUTPUT and `gcloud builds log BUILD_ID` are populated. If you prefer a narrower role, use `roles/logging.logWriter` and view logs in the [Cloud Build console](https://console.cloud.google.com/cloud-build/builds) or Logs Explorer.)

**If `gcloud builds submit` fails with "caller does not have permission to act as service account":** your user must be allowed to use the service account that runs the build (usually the default Compute Engine service account). A **project owner or admin** must run (replace with the email that runs the build):

```bash
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud iam service-accounts add-iam-policy-binding ${PROJECT_NUMBER}-compute@developer.gserviceaccount.com \
  --project=$PROJECT_ID \
  --member="user:YOUR_EMAIL@example.com" \
  --role="roles/iam.serviceAccountUser"
```

(Some projects have a dedicated `PROJECT_NUMBER@cloudbuild.gserviceaccount.com`; if that account exists and the error persists, add the same binding for it.)

**If the build fails at the Docker step and you can’t see logs:** fetch the log from the command line (use the build ID from the error message):

```bash
gcloud builds log BUILD_ID
# Example: gcloud builds log 00f80bfc-2152-4b91-b0d8-2b980cd9c7b4
```

If the log shows “No such file or directory” for `uv.lock` or `pyproject.toml`, the upload excluded them (e.g. via `.gitignore`). The repo includes a **`.gcloudignore`** that keeps `uv.lock`, `libs/`, and `services/` in the upload; ensure you’re not overriding it with `--ignore-file` and that `.gcloudignore` is committed.

---

## 2. Create a small Cloud SQL (PostgreSQL) instance

### 2.1 Create the instance

Use a small, cost-effective configuration (e.g. shared-core, 1 vCPU, ~0.6 GB RAM):

```bash
export INSTANCE_NAME=hackathon-medgemma-db
export DB_NAME=hackathon-medgemma-service
export DB_USER=hackathon-medgemma-api

# Generate a random password and set DB_PASSWORD (displayed once in the terminal)
export DB_PASSWORD=$(openssl rand -base64 24 | tr '/?&' '!@#') && echo "DB_PASSWORD=$DB_PASSWORD"

gcloud sql instances create $INSTANCE_NAME \
  --database-version=POSTGRES_16 \
  --edition=ENTERPRISE \
  --tier=db-f1-micro \
  --region=$REGION \
  --root-password="$DB_PASSWORD" \
  --storage-type=SSD \
  --storage-size=30GB
```

- `--edition=ENTERPRISE` is required for `db-f1-micro` (the default ENTERPRISE_PLUS edition uses different tiers like `db-perf-optimized-N-*`).
- `db-f1-micro`: shared-core, smallest tier (suitable for dev/small workloads).
- For slightly more capacity use `--tier=db-g1-small` (also ENTERPRISE).

**Approximate cost (per month, USD):** The `db-f1-micro` shared-core instance is about **$7.50/month** (instance), plus about **$1.70/month** for 10 GB SSD storage in a typical region (e.g. `us-central1`), so **~$9–10/month** total. Prices vary by region; see [Cloud SQL pricing](https://cloud.google.com/sql/pricing).

### 2.2 Create the database and user

```bash
# Create database
gcloud sql databases create $DB_NAME --instance=$INSTANCE_NAME

# Create a dedicated user (optional; you can use postgres + root password)
gcloud sql users create $DB_USER \
  --instance=$INSTANCE_NAME \
  --password="$DB_PASSWORD"
```

### 2.3 Create the OMOP vocabulary database (same instance)

Create a second database on the same Cloud SQL instance for the OMOP CDM vocabulary. The API will use it for concept resolution; the same DB user can connect to both databases.

```bash
gcloud sql databases create omop_vocab --instance=$INSTANCE_NAME
```

No new user is required: the user you created in 2.2 (`$DB_USER`) can connect to any database on the instance. If you use the instance’s `postgres` user for the main app, use it for OMOP as well.

### 2.4 Get the Cloud SQL connection name

```bash
gcloud sql instances describe $INSTANCE_NAME --format='value(connectionName)'
# Example: myproject:us-central1:medgemma-db
export CONNECTION_NAME=$(gcloud sql instances describe $INSTANCE_NAME --format='value(connectionName)')
```

You will use `CONNECTION_NAME` when deploying the API and building `DATABASE_URL`.

### 2.5 Fill the OMOP vocabulary database

The `omop_vocab` database must have the OMOP CDM schema and vocabulary data (at least the `concept` table). Do this once. The flow is: **download the vocabulary ZIP → extract (inflate) it → then** run Cloud SQL Proxy and load into the database.

**Result:** You use the same schema, load options, and indexes as the **docker-compose** `omop-vocab` service, so the data in Cloud SQL matches a local Docker run.

---

**Step 1 — Download the vocabulary ZIP**

- **From Athena OHDSI (recommended):** Go to [Athena OHDSI](https://athena.ohdsi.org), create an account if needed, select vocabularies (e.g. SNOMED CT, RxNorm, LOINC, ICD10CM, UCUM), and download the bundle. You get a ZIP file (often ~5–7 GB).
- **From Google Cloud Storage:** If you already uploaded the Athena ZIP to a GCS bucket (e.g. for reuse or to run from Cloud Shell), download it to your machine or Cloud Shell:
  ```bash
  gsutil cp gs://YOUR_BUCKET/path/to/vocabulary_download_v5_*.zip .
  ```
- Save the ZIP in the repo root or anywhere you prefer; you will extract it in the next step.

**Step 2 — Inflate (extract) the ZIP**

Extract the ZIP so that the CSV files (e.g. `CONCEPT.csv`, `VOCABULARY.csv`) sit in a single directory. Use the repo’s `data/omop_vocab` folder so the load script finds them by default:

```bash
cd /path/to/medgemma-hackathon-main
mkdir -p data/omop_vocab
unzip -o /path/to/vocabulary_download_v5_*.zip -d data/omop_vocab
```

Replace `/path/to/vocabulary_download_v5_*.zip` with the actual path to your ZIP (e.g. the file you downloaded from Athena or from GCS). After this, `data/omop_vocab` should contain at least: `CONCEPT.csv`, `VOCABULARY.csv`, `DOMAIN.csv`, `CONCEPT_CLASS.csv`, `RELATIONSHIP.csv`, `CONCEPT_RELATIONSHIP.csv`, `CONCEPT_SYNONYM.csv` (and optionally `DRUG_STRENGTH.csv`, `SOURCE_TO_CONCEPT_MAP.csv`).

**Step 3 — Install Cloud SQL Proxy (one-time) and start it**

If `cloud-sql-proxy` is not installed, install it once:

- **macOS (Intel):**
  ```bash
  curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.0/cloud-sql-proxy.darwin.amd64
  chmod +x cloud-sql-proxy
  sudo mv cloud-sql-proxy /usr/local/bin/   # or leave in current dir and run ./cloud-sql-proxy
  ```
- **macOS (Apple Silicon):**
  ```bash
  curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.0/cloud-sql-proxy.darwin.arm64
  chmod +x cloud-sql-proxy
  sudo mv cloud-sql-proxy /usr/local/bin/   # or run ./cloud-sql-proxy from this directory
  ```
- **Linux (amd64):**
  ```bash
  curl -o cloud-sql-proxy https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.0/cloud-sql-proxy.linux.amd64
  chmod +x cloud-sql-proxy
  sudo mv cloud-sql-proxy /usr/local/bin/   # or run ./cloud-sql-proxy from this directory
  ```
- **Alternatively, run via Docker** (no install, use the same connection name and port):
  ```bash
  docker run -d --name cloud-sql-proxy \
    -p 5432:5432 \
    gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.14.0 \
    "$CONNECTION_NAME"
  # Stop later with: docker stop cloud-sql-proxy && docker rm cloud-sql-proxy
  ```

Then start the proxy (from the repo root, with `$CONNECTION_NAME` set). Use Application Default Credentials (`gcloud auth application-default login`) or a service account key:

```bash
cloud-sql-proxy "$CONNECTION_NAME" --port=5432
# Leave this running in a terminal; you will connect to localhost:5432 for the instance.
```

**Step 4 — Apply schema, load data, create indexes**

In **another terminal**, from the **repository root**:

```bash
# Connection URL for the omop_vocab database (same user/password as main DB).
# Use the actual Cloud SQL user password (e.g. from Secret Manager), not a newly generated value:
export DB_PASSWORD=$(gcloud secrets versions access latest --secret=db-password)
export OMOP_VOCAB_URL="postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/omop_vocab"

# Apply OMOP schema
psql "$OMOP_VOCAB_URL" -f infra/omop-vocab/init-vocab-schema.sql

# Load vocabulary CSVs (reads from data/omop_vocab by default). Progress bar if 'pv' is installed (brew install pv).
chmod +x infra/omop-vocab/load-vocab-cloudsql.sh
./infra/omop-vocab/load-vocab-cloudsql.sh
# Or pass a different folder: ./infra/omop-vocab/load-vocab-cloudsql.sh /path/to/extracted/csvs

# Create indexes (can take 10–20 minutes)
psql "$OMOP_VOCAB_URL" -f infra/omop-vocab/create-indexes.sql
```

**Faster load:** The loader script uses `synchronous_commit = off` and `work_mem` and loads the two largest tables (`concept_relationship`, `concept_synonym`) in parallel, so total time is lower. If the load from your laptop is still slow (e.g. 30+ minutes), run it from **inside GCP** in the same region as Cloud SQL: upload the vocabulary ZIP to a GCS bucket, then use a **Compute Engine VM** or **Cloud Shell** (if you have enough disk) in that region, run the proxy and the same commands there. The VM→Cloud SQL link is much faster than home→proxy→Cloud SQL.

If you applied the schema and loaded data as a different user (e.g. `postgres`) and the API will connect as `$DB_USER`, grant the API user read access (run as the user that owns the tables):

```bash
psql "postgresql://postgres:PASSWORD@localhost:5432/omop_vocab" -c "
  GRANT USAGE ON SCHEMA public TO \"$DB_USER\";
  GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"$DB_USER\";
"
```

If you used `$DB_USER` in `OMOP_VOCAB_URL` for the schema and load, that user already owns the tables and no grant is needed.

After this, the same Cloud SQL instance has both the main app database and a populated `omop_vocab` database. Set `OMOP_VOCAB_URL` when deploying the API (section 4.6); use the same `host=/cloudsql/CONNECTION_NAME` and database name `omop_vocab`.

### 2.6 Store DB password in Secret Manager (recommended)

```bash
echo -n "$DB_PASSWORD" | gcloud secrets create db-password --data-file=-
```

**How to get the password (or any secret) back from Secret Manager**

To read the latest value of a secret (e.g. to build `OMOP_VOCAB_URL` or run the Cloud SQL Proxy load locally):

```bash
# DB password only (e.g. for building connection URLs)
gcloud secrets versions access latest --secret=db-password

# Full DATABASE_URL (if you stored it in db-url)
gcloud secrets versions access latest --secret=db-url

# Save into a variable (no newline)
export DB_PASSWORD=$(gcloud secrets versions access latest --secret=db-password)
```

You need permission to access the secret (e.g. **Secret Manager Secret Accessor** on the project or the secret). If the secret was created in another project, use `--project=PROJECT_ID`.

---

## 3. Artifact Registry (Docker images)

Create one repository for both images (or separate repos if you prefer):

```bash
gcloud artifacts repositories create app-images \
  --repository-format=docker \
  --location=$REGION \
  --description="API and Frontend images"
```

---

## 4. Deploy the API to Cloud Run

The API runs in the same process as the protocol processor and **calls the Vertex AI endpoint** for MedGemma. It needs: database (Cloud SQL), secrets (Session/JWT), and IAM to use Vertex AI and Secret Manager.

### 4.1 Create API secrets (Session, JWT)

```bash
# Generate and store session secret
openssl rand -base64 32 | tr -d '\n' | gcloud secrets create api-session-secret --data-file=-

# Generate and store JWT secret
openssl rand -base64 32 | tr -d '\n' | gcloud secrets create api-jwt-secret --data-file=-
```

### 4.2 Build and push the API image

From the **repository root**. Use the Cloud Build config (it specifies the Dockerfile path; `gcloud builds submit` does not accept `-f` directly):

```bash
cd /path/to/medgemma-hackathon-main

gcloud builds submit --config=cloudbuild-api.yaml --substitutions=_REGION=${REGION} .
```

### 4.3 Build DATABASE_URL for Cloud SQL

For Cloud Run + Cloud SQL Unix socket, the URL format is:

```text
postgresql://USER:PASSWORD@/DATABASE?host=/cloudsql/CONNECTION_NAME
```

If you use Secret Manager only for the password, you can either:

- Store the **full** `DATABASE_URL` in a secret (e.g. `db-url`), or  
- Pass non-secret parts as env vars and the password as a secret (e.g. `DB_PASSWORD`), and build the URL in the app if you add support for that.

Simplest for this guide: create a secret that holds the full URL:

```bash
# Replace USER, PASSWORD, DATABASE, CONNECTION_NAME
export DATABASE_URL="postgresql://${DB_USER}:${DB_PASSWORD}@/${DB_NAME}?host=/cloudsql/${CONNECTION_NAME}"
echo -n "$DATABASE_URL" | gcloud secrets create db-url --data-file=-
# If secret already exists, add a new version:
# echo -n "$DATABASE_URL" | gcloud secrets versions add db-url --data-file=-
```

### 4.3a Create GCS bucket (before API deploy)

Create the bucket for protocol PDFs and grant the Cloud Run API service account access **before** deploying the API so the first revision already has a working GCS backend.

```bash
# Cloud Run will use the default compute service account (same as in 4.5)
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export API_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Bucket name used in the deploy command (4.4)
export GCS_BUCKET_NAME="${GCS_BUCKET_NAME:-${PROJECT_ID}-api-protocols}"

# Create bucket (same region as Cloud Run)
gsutil mb -l $REGION gs://${GCS_BUCKET_NAME}

# Grant the API service account read/write on the bucket
gsutil iam ch serviceAccount:${API_SA}:objectAdmin gs://${GCS_BUCKET_NAME}
```

Keep `GCS_BUCKET_NAME` and `API_SA` set for the next steps (4.4 and 4.5).

### 4.4 Deploy the API service

Replace placeholders with your values. The API will use the **default Cloud Run service account**; we will grant it roles in the next section. On first deploy you can omit `CORS_ORIGINS` (or set it to a placeholder); set it to your **frontend** URL after deploying the frontend (step 4.6).

**For one command that regroups all secrets and env vars**, see **section 4.4b**.

**Migrations:** The container startup runs `alembic upgrade head` before starting the API (in the Dockerfile CMD). It uses `DATABASE_URL` from the environment (injected from the `db-url` secret). Migrations run automatically on every deploy; you do not need to run them manually on the Cloud SQL instance.

**Port:** The container listens on the `PORT` environment variable (Cloud Run sets `PORT=8080`). The Dockerfile uses `--port ${PORT:-8000}` so it works on Cloud Run and locally.

```bash
# GCS_BUCKET_NAME from 4.3a (bucket already created and IAM granted)
gcloud run deploy api \
  --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/app-images/api:latest \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --add-cloudsql-instances $CONNECTION_NAME \
  --set-env-vars "ENVIRONMENT=production" \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID}" \
  --set-env-vars "GCP_REGION=${REGION}" \
  --set-env-vars "MODEL_BACKEND=vertex" \
  --set-env-vars "VERTEX_ENDPOINT_ID=your-vertex-endpoint-id" \
  --set-env-vars "GCS_BUCKET_NAME=${GCS_BUCKET_NAME}" \
  --set-env-vars "USE_LOCAL_STORAGE=0" \
  --set-secrets "DATABASE_URL=db-url:latest" \
  --set-secrets "SESSION_SECRET=api-session-secret:latest" \
  --set-secrets "JWT_SECRET_KEY=api-jwt-secret:latest"
```

- **Vertex**: Set `VERTEX_ENDPOINT_ID` (and optionally `VERTEX_MODEL_NAME`) to your deployed MedGemma endpoint. The API calls Vertex via the default credential chain (Cloud Run service account).
- **CORS**: Set `CORS_ORIGINS` to your frontend URL(s). After you deploy the frontend, update the API revision with the real frontend URL (see below).
- **Optional env vars**: `GEMINI_MODEL_NAME` (e.g. `gemini-2.5-flash`), `UMLS_API_KEY`, `MLFLOW_TRACKING_URI` as needed. For **Gemini** (extraction + structuring), set `GOOGLE_API_KEY` via Secret Manager — see section **4.4a**. For health to report **gcs** and **omop_vocab** as available, set `GCS_BUCKET_NAME` and `OMOP_VOCAB_URL`; see section 4.6.

After deploy, note the service URL:

```bash
gcloud run services describe api --region $REGION --format='value(status.url)'
export API_SERVICE_URL=$(gcloud run services describe api --region $REGION --format='value(status.url)')
```

**If deploy fails with "Permission denied on secret" for db-url, api-session-secret, or api-jwt-secret:** the Cloud Run revision service account (default compute SA) needs **Secret Manager Secret Accessor**. Run the IAM step below (4.5), then redeploy.

**Vertex AI (MedGemma) — understanding `/health` and troubleshooting**

In `/health`, **`breakers.vertex_ai`** is the circuit breaker state for Vertex AI (MedGemma). **`"closed"` is the normal, healthy state** (requests are allowed). **`"open"`** means the breaker tripped after repeated failures. So **`"vertex_ai": "closed"` means OK**, not a problem.

If **Vertex calls fail at runtime** (e.g. 403, "endpoint not found" when running a protocol):

1. **Env vars** — Use `VERTEX_ENDPOINT_ID` = **endpoint ID only** (e.g. the numeric ID from the Vertex AI console), not the full resource name. The code builds `projects/{project}/locations/{region}/endpoints/{VERTEX_ENDPOINT_ID}`. Set `GCP_PROJECT_ID` and `GCP_REGION` to match the endpoint’s project and region (e.g. `europe-west4`).
2. **IAM** — The Cloud Run service account needs **Vertex AI User** (`roles/aiplatform.user`); see 4.5.
3. **Endpoint** — In Cloud Console: Vertex AI → Endpoints; confirm the endpoint is deployed and copy its ID.
4. **Logs** — In Cloud Run logs, when a request triggers MedGemma, look for `PermissionDenied`, `NotFound`, or `InvalidArgument` from the Vertex client.

**If the API crashes at startup with "DATABASE_URL environment variable is required but not set"**

You likely ran `gcloud run services update api ... --set-secrets "GOOGLE_API_KEY=..."`. The flag **`--set-secrets`** replaces *all* secrets with only the ones you list, so DATABASE_URL (and SESSION_SECRET, JWT_SECRET_KEY) were removed. Restore all required secrets in one go:

```bash
gcloud run services update api --region $REGION \
  --set-secrets "DATABASE_URL=db-url:latest,SESSION_SECRET=api-session-secret:latest,JWT_SECRET_KEY=api-jwt-secret:latest,GOOGLE_API_KEY=google-api-key:latest"
```

To only *add* Gemini without touching existing secrets, use **`--update-secrets`** (see 4.4a).

**If the API revision fails with "container failed to start and listen on the port defined by PORT=8080"**

Cloud Run reports this when the container never binds to `PORT=8080` within its startup window (or crashes before doing so). Common causes:

1. **Startup crash** — The container runs `alembic upgrade head` then `uvicorn ... --port ${PORT:-8000}`. If Alembic fails (e.g. `DATABASE_URL` missing or unreachable, migration error) or the app crashes on import (e.g. missing/forbidden secret), the process exits before listening.
2. **Slow startup** — DB in another region, many migrations, or heavy imports can exceed Cloud Run’s startup timeout (~240s); the platform then assumes the container failed to start.

**What to do:**

- **Check logs** for the failing revision:  
  **Cloud Run → api → Logs**, or:  
  `gcloud run services logs read api --region $REGION --limit 200`  
  Look for Python tracebacks, `OperationalError`/connection errors (Alembic/DB), or Secret Manager permission errors. If you just added `GOOGLE_API_KEY`, ensure the API service account has **Secret Manager Secret Accessor** and that the secret name is `google-api-key` (see 4.5 and 4.4a).
- **Confirm PORT** — The Dockerfile uses `--port ${PORT:-8000}` and `--host 0.0.0.0`; no change needed for Cloud Run’s `PORT=8080`.
- **Roll back** — If the failure started after an `update` (e.g. adding a secret), route traffic back to the last working revision:  
  `gcloud run revisions list --service api --region $REGION` to get the revision name, then  
  `gcloud run services update-traffic api --region $REGION --to-revisions REVISION_NAME=100`.  
  Then fix the new revision (secrets, IAM, or DB) and redeploy.
- **Slow startup** — Reduce work before listen: run migrations in a one-off job or at build time; keep DB in the same region as Cloud Run; avoid heavy import-time work. Cloud Run’s startup timeout is not configurable (~240s).

**How to debug when the container fails to start (and logs are empty or hard to find)**

1. **Logs for the failing revision**  
   Use the revision name from the error (e.g. `api-00009-sx8`):

   ```bash
   gcloud run services logs read api --region $REGION --limit 300
   ```

   To filter by revision:

   ```bash
   gcloud logging read 'resource.type="cloud_run_revision" resource.labels.service_name="api" resource.labels.revision_name="api-00009-sx8"' --limit 100 --format="table(timestamp,textPayload)" --project $PROJECT_ID
   ```

   In **Cloud Console**: **Logging → Logs Explorer**. Use query:

   ```
   resource.type="cloud_run_revision"
   resource.labels.service_name="api"
   resource.labels.revision_name="api-00009-sx8"
   ```

   Replace `api-00009-sx8` with your failing revision. If no entries appear, try without `revision_name` and look at the latest timestamps; logs can be delayed a few minutes.

2. **Run the same image locally**  
   This reproduces the crash on your machine so you see the traceback in the terminal:

   ```bash
   export REGION=europe-west4
   export PROJECT_ID=your-project-id
   docker pull ${REGION}-docker.pkg.dev/${PROJECT_ID}/app-images/api:latest
   # Get secrets (you need access to the project)
   export DATABASE_URL=$(gcloud secrets versions access latest --secret=db-url)
   export SESSION_SECRET=$(gcloud secrets versions access latest --secret=api-session-secret)
   export JWT_SECRET_KEY=$(gcloud secrets versions access latest --secret=api-jwt-secret)
   # Optional: GOOGLE_API_KEY, OMOP_VOCAB_URL
   docker run --rm -e PORT=8080 -e ENVIRONMENT=production -e GCP_PROJECT_ID=$PROJECT_ID -e GCP_REGION=$REGION \
     -e MODEL_BACKEND=vertex -e VERTEX_ENDPOINT_ID=your-endpoint -e GCS_BUCKET_NAME=your-bucket -e USE_LOCAL_STORAGE=0 \
     -e DATABASE_URL -e SESSION_SECRET -e JWT_SECRET_KEY -p 8080:8080 \
     ${REGION}-docker.pkg.dev/${PROJECT_ID}/app-images/api:latest
   ```

   If the app needs Cloud SQL, run **Cloud SQL Proxy** in another terminal and use `DATABASE_URL` with `localhost` (and the proxy port) instead of the Cloud SQL socket. The container will crash with the same error as on Cloud Run (e.g. `ValueError: DATABASE_URL ... not set` or a DB connection error), and you’ll see it in the terminal.

3. **Run the API without Docker (from repo)**  
   Fastest way to see a Python traceback:

   ```bash
   cd /path/to/medgemma-hackathon-main
   export DATABASE_URL="postgresql://user:pass@localhost:5432/dbname"   # or use Cloud SQL Proxy
   export SESSION_SECRET=dev-secret
   export JWT_SECRET_KEY=dev-jwt-secret
   cd services/api-service && uv run uvicorn api_service.main:app --host 0.0.0.0 --port 8080
   ```

   If something fails at import or startup, the traceback appears immediately.

4. **Check that secrets exist and the service account can read them**  
   List secrets: `gcloud secrets list`. Confirm the revision’s service account has **Secret Manager Secret Accessor** (section 4.5). Test access:  
   `gcloud secrets versions access latest --secret=db-url`  
   (run as yourself; Cloud Run uses the default compute SA, which must have the same permission.)

### 4.4a Enable Gemini (Google AI API) for Cloud Run

The API uses **Gemini** (e.g. Gemini 2.5 Flash) for **PDF extraction** and for **structuring MedGemma’s free-form output** into Pydantic models. This is separate from Vertex AI (which runs MedGemma). Gemini is called via the **Google AI (Developer) API** and requires an API key.

1. **Get a Gemini API key**  
   Go to [Google AI Studio](https://aistudio.google.com/apikey), sign in, and create an API key.

2. **Store the key in Secret Manager** (do not put it in plain env vars):

   ```bash
   echo -n "YOUR_GEMINI_API_KEY" | gcloud secrets create google-api-key --data-file=-
   # If the secret already exists, add a new version:
   # echo -n "YOUR_GEMINI_API_KEY" | gcloud secrets versions add google-api-key --data-file=-
   ```

3. **Grant the API service account access** to the secret (same SA as in 4.5). If you already granted `roles/secretmanager.secretAccessor` at project level, it can read any secret; otherwise ensure the Cloud Run service account has access to `google-api-key`.

4. **Update the API** to pass the secret and optional model name. Use **`--update-secrets`** (not `--set-secrets`) so you only add/update this secret and do not remove existing ones (DATABASE_URL, SESSION_SECRET, JWT_SECRET_KEY):

   ```bash
   gcloud run services update api --region $REGION \
     --update-secrets "GOOGLE_API_KEY=google-api-key:latest" \
     --set-env-vars "GEMINI_MODEL_NAME=gemini-2.5-flash"
   ```

   Or include them on **first deploy** (add to the `gcloud run deploy api` command in 4.4):

   ```bash
   --set-secrets "GOOGLE_API_KEY=google-api-key:latest" \
   --set-env-vars "GEMINI_MODEL_NAME=gemini-2.5-flash"
   ```

Without `GOOGLE_API_KEY`, PDF extraction and the Gemini-based structuring of MedGemma output will not work; the health check reports `breakers.gemini` (e.g. closed when calls succeed). The default model is `gemini-2.5-flash` if `GEMINI_MODEL_NAME` is not set.

### 4.4b Full API deploy and update commands (all secrets and env vars)

Use these when you want **one command** that sets every secret and env var for the API. Set the variables at the top, then run either the **deploy** (new image + config) or **update** (config only) block.

**Required variables (set before running):**

```bash
export REGION=europe-west4
export PROJECT_ID=your-gcp-project-id
export CONNECTION_NAME=your-project:your-region:your-instance
export GCS_BUCKET_NAME=hackathon-api-protocols
export VERTEX_ENDPOINT_ID="your-vertex-endpoint-id"
export CORS_ORIGINS=https://your-frontend-url.run.app
```

**Optional (only if you use them):** Gemini secret `google-api-key`, OMOP secret `omop-vocab-url`. Create them in Secret Manager first (see 4.4a and 4.6).

**Deploy (build + deploy with full config):**

```bash
# 1) Build and push image (from repo root)
gcloud builds submit --config=cloudbuild-api.yaml --substitutions=_REGION=${REGION} .

# 2) Deploy — minimal (required secrets and env vars only)
gcloud run deploy api \
  --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/app-images/api:latest \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --add-cloudsql-instances $CONNECTION_NAME \
  --set-env-vars "ENVIRONMENT=production,GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},MODEL_BACKEND=vertex,VERTEX_ENDPOINT_ID=${VERTEX_ENDPOINT_ID},GCS_BUCKET_NAME=${GCS_BUCKET_NAME},USE_LOCAL_STORAGE=0,CORS_ORIGINS=${CORS_ORIGINS}" \
  --set-secrets "DATABASE_URL=db-url:latest,SESSION_SECRET=api-session-secret:latest,JWT_SECRET_KEY=api-jwt-secret:latest"
```

Deploy **with Gemini + OMOP** (one command; include only the secrets you actually use):

```bash
gcloud run deploy api \
  --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/app-images/api:latest \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --add-cloudsql-instances $CONNECTION_NAME \
  --set-env-vars "ENVIRONMENT=production,GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},MODEL_BACKEND=vertex,VERTEX_ENDPOINT_ID=${VERTEX_ENDPOINT_ID},GCS_BUCKET_NAME=${GCS_BUCKET_NAME},USE_LOCAL_STORAGE=0,CORS_ORIGINS=${CORS_ORIGINS},GEMINI_MODEL_NAME=gemini-2.5-flash" \
  --set-secrets "DATABASE_URL=db-url:latest,SESSION_SECRET=api-session-secret:latest,JWT_SECRET_KEY=api-jwt-secret:latest,GOOGLE_API_KEY=google-api-key:latest,OMOP_VOCAB_URL=omop-vocab-url:latest"
```

**Update (config only — same image, new revision with all secrets and env vars):**

Use this to fix a revision that’s missing secrets (e.g. after an accidental `--set-secrets` that wiped others) or to set the full config in one shot.

```bash
# Minimal (required only). Add GOOGLE_API_KEY and OMOP_VOCAB_URL to --set-secrets if you use them.
gcloud run services update api --region $REGION \
  --set-env-vars "ENVIRONMENT=production,GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},MODEL_BACKEND=vertex,VERTEX_ENDPOINT_ID=${VERTEX_ENDPOINT_ID},GCS_BUCKET_NAME=${GCS_BUCKET_NAME},USE_LOCAL_STORAGE=0,CORS_ORIGINS=${CORS_ORIGINS}" \
  --set-secrets "DATABASE_URL=db-url:latest,SESSION_SECRET=api-session-secret:latest,JWT_SECRET_KEY=api-jwt-secret:latest"
```

With **Gemini + OMOP** (include every secret you use; `--set-secrets` replaces the whole map):

```bash
gcloud run services update api --region $REGION \
  --set-env-vars "ENVIRONMENT=production,GCP_PROJECT_ID=${PROJECT_ID},GCP_REGION=${REGION},MODEL_BACKEND=vertex,VERTEX_ENDPOINT_ID=${VERTEX_ENDPOINT_ID},GCS_BUCKET_NAME=${GCS_BUCKET_NAME},USE_LOCAL_STORAGE=0,CORS_ORIGINS=${CORS_ORIGINS},GEMINI_MODEL_NAME=gemini-2.5-flash" \
  --set-secrets "DATABASE_URL=db-url:latest,SESSION_SECRET=api-session-secret:latest,JWT_SECRET_KEY=api-jwt-secret:latest,GOOGLE_API_KEY=google-api-key:latest,OMOP_VOCAB_URL=omop-vocab-url:latest"
```

- **Secrets:** `--set-secrets` replaces the entire secret map. List every secret the API should have (required: `DATABASE_URL`, `SESSION_SECRET`, `JWT_SECRET_KEY`; optional: `GOOGLE_API_KEY`, `OMOP_VOCAB_URL`). Omit optional ones if you don’t use them.
- **Env vars:** `--set-env-vars` replaces all env vars. Add optional keys (e.g. `UMLS_API_KEY`, `MLFLOW_TRACKING_URI`) to the comma-separated list as needed.

### 4.5 IAM: API service account (Cloud SQL, Vertex, Secret Manager)

Cloud Run uses the default compute service account. Get its email and grant roles:

```bash
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export API_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
```

Grant:

- **Cloud SQL Client** (connect to Cloud SQL)
- **Vertex AI User** (call Vertex endpoint)
- **Secret Manager Secret Accessor** (read DATABASE_URL, SESSION_SECRET, JWT_SECRET_KEY, and optionally GOOGLE_API_KEY; see 4.4a)
- **Storage Object Admin** on the GCS bucket you use for protocol storage (see 4.6) — or `roles/storage.objectAdmin` at project level if you prefer.

```bash
for role in roles/cloudsql.client roles/aiplatform.user roles/secretmanager.secretAccessor; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${API_SA}" \
    --role="$role"
done
```

If you use a dedicated GCS bucket (recommended), grant the API SA access to that bucket only (do this after creating the bucket in 4.6):

```bash
gsutil iam ch serviceAccount:${API_SA}:objectAdmin gs://YOUR_BUCKET_NAME
```

If you use a **custom service account** for the API, use that email instead of `API_SA` and attach it with `--service-account=${API_SA}` in `gcloud run deploy api`.

**Access control:** If you do not add `allUsers` as run.invoker (and do not use `--no-invoker-iam-check`), the API is **private**: only identities that you grant `roles/run.invoker` to can call it. You control access by adding or removing that role for users, groups, or service accounts.

**If you get "Forbidden - Your client does not have permission to get URL"** when opening the API URL or `/docs`: the service is not allowing unauthenticated callers.

- **If your project allows public access:** grant the public invoker role:  
  `gcloud run services add-iam-policy-binding api --region=$REGION --member=allUsers --role=roles/run.invoker`

- **If org policy blocks `allUsers`** ("users named in the policy do not belong to a permitted customer"): you cannot make the service public. Grant **run.invoker** to specific users or a group, then call the API with an identity token. Example for a user:

  ```bash
  # Grant your user (or a group) permission to invoke the service
  gcloud run services add-iam-policy-binding api --region=$REGION \
    --member="user:your-email@your-domain.com" \
    --role=roles/run.invoker
  ```

  To call the API or open `/docs` (e.g. from curl), send an identity token:

  ```bash
  # Get a token and call the API (use your API URL)
  TOKEN=$(gcloud auth print-identity-token)
  curl -H "Authorization: Bearer $TOKEN" https://YOUR-API-URL.run.app/health
  ```

### 4.6 Make GCS and OMOP vocabulary available

**Why the API needs a bucket**  
The API uses a GCS bucket to store **protocol PDFs** (trial protocols uploaded by users). Flow: the frontend calls `POST /protocols/upload`, the API returns a **signed upload URL** so the browser uploads the PDF directly to GCS; the API stores the object path (`gs://bucket/protocols/...`) in the database. Later, extraction and review use that path, and the API issues **signed download URLs** when users open a protocol. Without a bucket (and without `USE_LOCAL_STORAGE=1`), upload and download of protocol files do not work in production.

The `/health` endpoint reports **gcs** and **omop_vocab** as well as the main database. To get **everything available** (`"database":"connected"`, `"omop_vocab":"ok"`, `"gcs":"ok"`):

| Order | What | Section / step below |
|-------|------|----------------------|
| 1 | Create GCS bucket + grant API SA access | **4.3a** (before API deploy) |
| 2 | Deploy API (includes `GCS_BUCKET_NAME` and `USE_LOCAL_STORAGE=0`) | 4.4 |
| 3 | Ensure OMOP database exists and is filled | Section 2.3–2.5 |
| 4 | Update the API with `OMOP_VOCAB_URL` | OMOP vocabulary below; one-shot update |

**GCS (protocol storage)**  
Bucket creation and IAM are done in **section 4.3a** before the first API deploy. The deploy command in **4.4** already sets `GCS_BUCKET_NAME` and `USE_LOCAL_STORAGE=0`, so after deploy the API uses the bucket and health reports `"gcs": "ok"`.

If you deployed the API without 4.3a, create the bucket and grant access (same commands as in 4.3a), then update the revision:

```bash
export GCS_BUCKET_NAME="${GCS_BUCKET_NAME:-${PROJECT_ID}-api-protocols}"
gsutil mb -l $REGION gs://${GCS_BUCKET_NAME}
gsutil iam ch serviceAccount:${API_SA}:objectAdmin gs://${GCS_BUCKET_NAME}
gcloud run services update api --region $REGION \
  --set-env-vars "GCS_BUCKET_NAME=${GCS_BUCKET_NAME},USE_LOCAL_STORAGE=0"
```

**OMOP vocabulary**

The API expects a PostgreSQL database with the OMOP CDM vocabulary schema and at least the `concept` table populated. If you followed **section 2.3–2.5**, you already created the `omop_vocab` database on your Cloud SQL instance and filled it; set the URL when deploying or updating the API.

- **Option A — Env var:** Set `OMOP_VOCAB_URL` (password will be visible in Cloud Run env). Use the same `CONNECTION_NAME`, `DB_USER`, and the **actual** DB password (e.g. from Secret Manager):

  ```bash
  export DB_PASSWORD=$(gcloud secrets versions access latest --secret=db-password)
  export OMOP_VOCAB_URL="postgresql://${DB_USER}:${DB_PASSWORD}@/omop_vocab?host=/cloudsql/${CONNECTION_NAME}"
  gcloud run services update api --region $REGION \
    --set-env-vars "OMOP_VOCAB_URL=${OMOP_VOCAB_URL}"
  ```

- **Option B — Secret (recommended):** Store the full URL in Secret Manager so the password is not in env:

  ```bash
  export DB_PASSWORD=$(gcloud secrets versions access latest --secret=db-password)
  export OMOP_VOCAB_URL="postgresql://${DB_USER}:${DB_PASSWORD}@/omop_vocab?host=/cloudsql/${CONNECTION_NAME}"
  echo -n "$OMOP_VOCAB_URL" | gcloud secrets create omop-vocab-url --data-file=-
  # If secret already exists: echo -n "$OMOP_VOCAB_URL" | gcloud secrets versions add omop-vocab-url --data-file=-
  gcloud run services update api --region $REGION \
    --set-secrets "OMOP_VOCAB_URL=omop-vocab-url:latest"
  ```

After OMOP is loaded and the URL is set, health will report `"omop_vocab": "ok"` (and optionally `omop_concept_count`). The **readiness** probe (`/ready`) requires OMOP to be available.

**One-shot update (OMOP only)**

Once the `omop_vocab` database is filled (section 2.3–2.5):

1. Store OMOP URL in Secret Manager (if not already):  
   `export DB_PASSWORD=$(gcloud secrets versions access latest --secret=db-password)`  
   `export OMOP_VOCAB_URL="postgresql://${DB_USER}:${DB_PASSWORD}@/omop_vocab?host=/cloudsql/${CONNECTION_NAME}"`  
   Then either `echo -n "$OMOP_VOCAB_URL" | gcloud secrets create omop-vocab-url --data-file=-` or, if the secret exists, `echo -n "$OMOP_VOCAB_URL" | gcloud secrets versions add omop-vocab-url --data-file=-`.

2. Update the API revision with OMOP (GCS is already set from 4.3a + 4.4):

   ```bash
   gcloud run services update api --region $REGION \
     --set-secrets "OMOP_VOCAB_URL=omop-vocab-url:latest"
   ```

Then re-check `/health`: you should see `"omop_vocab":"ok"` and `"gcs":"ok"` (GCS was configured at deploy).

### 4.6a Deploy MLflow tracking server (optional)

The API can send experiment/trace data to an MLflow tracking server when `MLFLOW_TRACKING_URI` is set. The **simplest** way is to run MLflow on Cloud Run, using your existing **Cloud SQL** for metadata and **GCS** for artifacts. The backend store URI is stored in Secret Manager (no DB password in env).

**1. Create MLflow database and artifact location**

On your existing Cloud SQL instance, create a database for MLflow and a GCS path for artifacts:

```bash
# Reuse CONNECTION_NAME, INSTANCE_NAME, DB_USER from section 2
gcloud sql databases create mlflow --instance=$INSTANCE_NAME

# GCS bucket for MLflow artifacts
export MLFLOW_ARTIFACT_BUCKET="${MLFLOW_ARTIFACT_BUCKET:-${PROJECT_ID}-mlflow-artifacts}"
gsutil mb -l $REGION gs://${MLFLOW_ARTIFACT_BUCKET} 2>/dev/null || true
# Grant the default compute SA (same as API) access so MLflow on Cloud Run can write
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud storage buckets add-iam-policy-binding gs://${MLFLOW_ARTIFACT_BUCKET} \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
```

**2. Store the MLflow backend store URI in Secret Manager**

Build the Postgres URL for the `mlflow` database using the **DB password from Secret Manager**, then create a secret so the password is never in env or deploy commands:

```bash
# DB password from the same secret you use for the API (e.g. db-password or from db-url)
export DB_PASSWORD=$(gcloud secrets versions access latest --secret=db-password)
# Backend: Postgres on Cloud SQL (same instance, database "mlflow")
export MLFLOW_BACKEND_URI="postgresql://${DB_USER}:${DB_PASSWORD}@/mlflow?host=/cloudsql/${CONNECTION_NAME}"
echo -n "$MLFLOW_BACKEND_URI" | gcloud secrets create mlflow-backend-uri --data-file=-
# If the secret already exists (e.g. you're re-running): add a new version
# echo -n "$MLFLOW_BACKEND_URI" | gcloud secrets versions add mlflow-backend-uri --data-file=-
```

Ensure the Cloud Run default compute service account can read this secret (it can if you already granted **Secret Manager Secret Accessor** in section 4.5 for the API).

**3. Build and push the MLflow image**

From the repo root:

```bash
gcloud builds submit --config=cloudbuild-mlflow.yaml --substitutions=_REGION=${REGION} .
```

**4. Deploy MLflow to Cloud Run**

Inject the backend store URI from the secret; pass the artifact root as env (not sensitive):

```bash
export MLFLOW_ARTIFACT_ROOT="gs://${MLFLOW_ARTIFACT_BUCKET}/artifacts"

gcloud run deploy mlflow \
  --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/app-images/mlflow:latest \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --add-cloudsql-instances $CONNECTION_NAME \
  --set-env-vars "MLFLOW_DEFAULT_ARTIFACT_ROOT=${MLFLOW_ARTIFACT_ROOT}" \
  --set-secrets "MLFLOW_BACKEND_STORE_URI=mlflow-backend-uri:latest"
```

**If the MLflow deployment fails,** check logs:

```bash
gcloud run services logs read mlflow --region $REGION --limit 200
```

Or in **Logging → Logs Explorer**: `resource.type="cloud_run_revision"` and `resource.labels.service_name="mlflow"`. Look for Python tracebacks, database connection errors, or Secret Manager permission errors.

**5. Point the API at MLflow**

After deploy, set the tracking URI on the API:

```bash
export MLFLOW_URL=$(gcloud run services describe mlflow --region $REGION --format='value(status.url)')
gcloud run services update api --region $REGION \
  --update-env-vars "MLFLOW_TRACKING_URI=${MLFLOW_URL}"
```

The API will then log runs/traces to MLflow when `MLFLOW_TRACKING_URI` is set (e.g. LangChain autolog for extraction/grounding).

**If you don’t have a `db-password` secret:** Use the same credentials you used to create `db-url` (section 2). You can create a dedicated secret: `echo -n "YOUR_DB_PASSWORD" | gcloud secrets create db-password --data-file=-`, or temporarily set `DB_PASSWORD` when building the URI and creating `mlflow-backend-uri` (the password is only in the secret after that).

**Summary**

| Step | Command / action |
|------|------------------|
| DB + GCS | Create DB `mlflow`, bucket, grant default compute SA `objectAdmin` on bucket |
| Secret | Get `DB_PASSWORD` from Secret Manager; build Postgres URL for `mlflow` DB; create secret `mlflow-backend-uri` |
| Build | `gcloud builds submit --config=cloudbuild-mlflow.yaml .` |
| Deploy | `gcloud run deploy mlflow` with `--set-secrets "MLFLOW_BACKEND_STORE_URI=mlflow-backend-uri:latest"` and `--set-env-vars "MLFLOW_DEFAULT_ARTIFACT_ROOT=gs://..."` |
| API | `gcloud run services update api --update-env-vars "MLFLOW_TRACKING_URI=<mlflow-url>"` |

### 4.7 Update CORS after frontend URL is known

After deploying the frontend (section 5), set CORS to the frontend origin:

```bash
export FRONTEND_URL="https://frontend-XXXXX-${REGION}.a.run.app"
gcloud run services update api --region $REGION \
  --set-env-vars "CORS_ORIGINS=${FRONTEND_URL}"
```

### 4.8 Updating the existing deployment

After the API is deployed once, use the following to update it.

**Code or image change (new build)**

1. Rebuild and push the image (same as 4.2):

   ```bash
   cd /path/to/medgemma-hackathon-main
   gcloud builds submit --config=cloudbuild-api.yaml --substitutions=_REGION=${REGION} .
   ```

2. Deploy the new image with the same config as 4.4. **For a single command that includes all secrets and env vars**, use the deploy block in **section 4.4b** (set `REGION`, `PROJECT_ID`, `CONNECTION_NAME`, `GCS_BUCKET_NAME`, `VERTEX_ENDPOINT_ID`, `CORS_ORIGINS`, then run the deploy command there).

**Env vars or secrets only (no new image)**

Use `gcloud run services update api` so Cloud Run creates a new revision with updated config but the same image. **To set the full set of secrets and env vars in one command**, use the update block in **section 4.4b**.

To change only one or two values without replacing everything:

```bash
# Add/update a single secret (keeps other secrets)
gcloud run services update api --region $REGION --update-secrets "GOOGLE_API_KEY=google-api-key:latest"

# Add/update env vars (merge with existing)
gcloud run services update api --region $REGION --update-env-vars "CORS_ORIGINS=https://frontend-xxx.run.app,GEMINI_MODEL_NAME=gemini-2.5-flash"
```

- `--set-env-vars` replaces all env vars with the ones you list (include every var the service needs).
- `--update-env-vars` adds or updates only the given keys; other env vars are unchanged.
- `--set-secrets` / `--update-secrets` work the same way for secrets.

After any update, the new revision serves traffic. Check `/health` to confirm.

---

## 5. Deploy the Frontend to Cloud Run

The frontend is a static SPA (Vite + React) built into a Docker image and served with Nginx. It needs the **API base URL at build time** (`VITE_API_URL`).

### 5.1 Build and push the frontend image

The frontend Dockerfile accepts build args `VITE_API_URL` and `BASE_PATH`. The API URL is baked into the static assets at build time.

**Option A: Cloud Build** (recommended; no local Docker needed)

Use the repo’s `cloudbuild-frontend.yaml`, which passes build args via substitutions. From the **repository root**:

```bash
# Set to your API Cloud Run URL (from step 4.4)
export API_SERVICE_URL="https://api-XXXXX-${REGION}.a.run.app"

gcloud builds submit \
  --config=cloudbuild-frontend.yaml \
  --substitutions=_VITE_API_URL="${API_SERVICE_URL}",_BASE_PATH="/",_REGION="${REGION}" \
  .
```

**Option B: Local Docker**

```bash
export API_SERVICE_URL="https://api-XXXXX-${REGION}.a.run.app"

docker build -f apps/hitl-ui/Dockerfile \
  --build-arg VITE_API_URL="${API_SERVICE_URL}" \
  --build-arg BASE_PATH="/" \
  -t ${REGION}-docker.pkg.dev/${PROJECT_ID}/app-images/frontend:latest \
  .

docker push ${REGION}-docker.pkg.dev/${PROJECT_ID}/app-images/frontend:latest
```

Configure Docker for Artifact Registry auth if needed: `gcloud auth configure-docker ${REGION}-docker.pkg.dev`.

### 5.2 Deploy the frontend service

The frontend does not need secrets or Cloud SQL. It only needs to be reachable by users; it calls the API from the browser (using the URL baked in at build time).

```bash
gcloud run deploy frontend \
  --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/app-images/frontend:latest \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated
```

Cloud Run will serve the container; the default port the Dockerfile exposes is **8080**, which matches Cloud Run’s default.

### 5.3 Make the frontend public (allow unauthenticated access)

To let anyone open the frontend URL in a browser (no login), grant the public invoker role on the **frontend** service:

```bash
gcloud run services add-iam-policy-binding frontend \
  --region=$REGION \
  --member=allUsers \
  --role=roles/run.invoker
```

If you used `--allow-unauthenticated` when you ran `gcloud run deploy frontend`, this binding may already exist. If you still get **Forbidden** when opening the frontend URL, run the command above explicitly.

**If your org policy blocks `allUsers`** (error: "One or more users named in the policy do not belong to a permitted customer"):

- **Option A — Grant invoker to specific users:**  
  `gcloud run services add-iam-policy-binding frontend --region=$REGION --member="user:email@example.com" --role=roles/run.invoker`  
  Access from a browser still requires an identity token. Use **Identity-Aware Proxy (IAP)** in front of the frontend (and optionally the API) so users sign in with Google and IAP forwards the token; or use a small proxy that adds the token.
- **Option B — Host the frontend elsewhere:** Build the same static assets and serve them from **Firebase Hosting**, **Cloud Storage + Load Balancer**, or another host (Vercel, Netlify, etc.). Then the frontend URL is not Cloud Run and is not subject to Cloud Run IAM. Point `VITE_API_URL` at your API and set API CORS to the new frontend origin.
- **Option C — Org admin:** See **Appendix: Allow public Cloud Run (for org admins)** below.

### 5.4 Frontend IAM (service account)

The frontend is a static site; it does not call GCP APIs from the server. It only needs to be **invokable by unauthenticated users** (or by your chosen identity if you restrict access). No extra IAM roles are required for the frontend service account for “reaching” the API: the browser calls the API URL directly, and CORS is configured on the API side (step 4.6).

If you later add server-side API calls from the frontend container, you would grant the frontend’s service account only the roles needed for those calls.

---

## 6. OAuth (optional): Google login

If you use Google OAuth for the UI:

1. In [APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials), create OAuth 2.0 Client ID (Web application).
2. Add **Authorized redirect URIs**:
   - `https://YOUR-FRONTEND-URL/auth/callback`
   - `https://YOUR-API-URL/auth/callback` (if the API serves the callback)
3. Set env vars on the **API** (not the frontend):
   - `GOOGLE_CLIENT_ID=...`
   - `GOOGLE_CLIENT_SECRET=...` (store in Secret Manager and inject via `--set-secrets` if you prefer).

---

## 7. Summary: order of operations and permissions

| Step | What | Notes |
|------|------|--------|
| 1 | Enable APIs, set project/region | One-time |
| 2 | Create Cloud SQL instance, database, user; store password (and optionally full DATABASE_URL) in Secret Manager | Tiny instance: e.g. `db-f1-micro` |
| 3 | Create Artifact Registry repo | One-time |
| 4 | Build API image → push → deploy API to Cloud Run with Cloud SQL connection, env vars, secrets | Set CORS after frontend URL is known |
| 4.5 | Grant API service account: Cloud SQL Client, Vertex AI User, Secret Manager Secret Accessor | So API can reach DB, Vertex, and secrets |
| 5 | Build frontend image with `VITE_API_URL` = API Cloud Run URL → push → deploy frontend to Cloud Run | No extra IAM for “calling API”; browser uses API URL |
| 6 | Update API CORS to frontend URL | So browser can call API from frontend origin |

**Who calls what**

- **Browser** → Frontend (Cloud Run) → static assets.  
- **Browser** → API (Cloud Run) → API handles auth, DB, and triggers protocol processing.  
- **API (Cloud Run)** → Cloud SQL (via Unix socket), Secret Manager, **Vertex AI endpoint** (MedGemma).  
- Frontend does not need GCP IAM to “reach” the API; CORS on the API allows the frontend origin.

---

## 8. Quick reference: env vars and secrets

**API (Cloud Run)** — For a single deploy/update command that sets all of these, see **section 4.4b**.

- **Required**: `ENVIRONMENT=production`, `DATABASE_URL` (secret), `SESSION_SECRET` (secret), `JWT_SECRET_KEY` (secret).  
- **Vertex**: `GCP_PROJECT_ID`, `GCP_REGION`, `MODEL_BACKEND=vertex`, `VERTEX_ENDPOINT_ID` (or `VERTEX_MODEL_NAME`).  
- **CORS**: `CORS_ORIGINS=https://your-frontend-url`.  
- **Optional**: `GEMINI_MODEL_NAME` (env), `GOOGLE_API_KEY` (secret — see 4.4a for Gemini), `UMLS_API_KEY`, `OMOP_VOCAB_URL`, `GCS_BUCKET_NAME`, `MLFLOW_TRACKING_URI`, OAuth client id/secret.
- **Health (omop_vocab + gcs available):** Set `GCS_BUCKET_NAME` and `USE_LOCAL_STORAGE=0`; set `OMOP_VOCAB_URL` (env or secret). Create bucket, grant API SA `objectAdmin` on it, fill OMOP DB (2.3–2.5). See **section 4.6**.

**Frontend**

- **Build-time only**: `VITE_API_URL` (Cloud Run API URL), `BASE_PATH` (e.g. `/`). No runtime secrets required for basic deployment.

**IAM (API service account)**

- `roles/cloudsql.client`  
- `roles/aiplatform.user`  
- `roles/secretmanager.secretAccessor`  
- GCS: `gsutil iam ch serviceAccount:${API_SA}:objectAdmin gs://YOUR_BUCKET_NAME` (or project-level `roles/storage.objectAdmin`)

---

## Appendix: Allow public Cloud Run (for org admins)

When a developer runs:

```bash
gcloud run services add-iam-policy-binding frontend --region=REGION --member=allUsers --role=roles/run.invoker
```

and gets **"One or more users named in the policy do not belong to a permitted customer, perhaps due to an organization policy"**, an organization policy is blocking the use of `allUsers` (public access) on Cloud Run.

**What the org admin needs to do**

1. **Identify the policy**  
   In [Google Cloud Console](https://console.cloud.google.com/) → **IAM & Admin** → **Organization policies** (or go to the **Resource Manager** and select the org/folder).  
   The constraint is usually one of:
   - **Domain restricted sharing** (`iam.allowedPolicyMemberDomains`) — limits which principals (e.g. which domains) can be added to IAM policies; `allUsers` is not in any domain, so it is blocked.
   - A **custom org policy** that restricts “public” or “unauthenticated” access to certain resources.

2. **Add an exception for the project (or for Cloud Run)**  
   - Open the policy that restricts public/allUsers (e.g. **Domain restricted sharing**).
   - **Edit** the policy.
   - Add a **rule** that applies only to the **project** (or folder) where the frontend/API run, and set it to **Allow** or **Replace** so that this project is **exempt** from the restriction.  
   - Or, if the policy has a list of allowed principals or conditions, add an exception that allows `allUsers` for the role `roles/run.invoker` on Cloud Run services in that project (syntax depends on the constraint).

3. **Typical flow for “Domain restricted sharing”**  
   - Policy is set at **Organization** or **Folder** level.
   - Add a **policy exception** for the **project ID** where the developer deploys the frontend (and API).  
   - Exception type: “Allow” or “Replace” so the policy is not enforced on that project (or so `allUsers` is allowed for Cloud Run in that project).  
   - Save. After a few minutes, the developer can retry the `add-iam-policy-binding` command.

4. **If the org does not allow exceptions**  
   The developer must use **Option A** (invoker for specific users + IAP or proxy) or **Option B** (host the frontend on Firebase Hosting, Vercel, etc.) from section 5.3.

**References**

- [Organization policy constraints](https://cloud.google.com/resource-manager/docs/organization-policy/org-policy-constraints)  
- [Domain restricted sharing](https://cloud.google.com/resource-manager/docs/organization-policy/restricting-domains)  
- [Cloud Run IAM](https://cloud.google.com/run/docs/securing/managing-access)
