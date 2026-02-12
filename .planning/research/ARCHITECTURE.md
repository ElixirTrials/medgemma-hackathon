# Architecture Research: Terraform GCP Cloud Run Deployment

**Domain:** Terraform-based GCP Cloud Run deployment for containerized microservices monorepo
**Researched:** 2026-02-12
**Confidence:** HIGH

## Standard Architecture

### System Overview: Terraform Integration with Existing Services

```
┌─────────────────────────────────────────────────────────────────────┐
│                   Local Development Environment                      │
├─────────────────────────────────────────────────────────────────────┤
│  .env → infra/.env.example → Docker Compose → Services              │
│  (PostgreSQL, MLflow, PubSub emulator, 4 containerized services)    │
└─────────────────────────────────────────────────────────────────────┘
                                    ↓
                    .env → terraform.tfvars (manual mapping)
                                    ↓
┌─────────────────────────────────────────────────────────────────────┐
│              Terraform Deployment Layer (infra/terraform/)           │
├─────────────────────────────────────────────────────────────────────┤
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐            │
│  │   Foundation  │  │   Networking  │  │    Secrets    │            │
│  │   Module      │  │   Module      │  │    Module     │            │
│  │ • Project     │  │ • VPC         │  │ • Secret Mgr  │            │
│  │ • APIs        │  │ • VPC Conn    │  │ • DB creds    │            │
│  │ • Artifact    │  │ • Firewall    │  │ • API keys    │            │
│  │   Registry    │  │               │  │               │            │
│  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘            │
│          │                  │                  │                     │
│  ┌───────┴──────────────────┴──────────────────┴───────┐            │
│  │              Database Module                         │            │
│  │  • Cloud SQL PostgreSQL 16                           │            │
│  │  • Private IP (VPC)                                  │            │
│  │  • Automated backups                                 │            │
│  └────────────────────────┬─────────────────────────────┘            │
│                           │                                          │
│  ┌────────────────────────┴─────────────────────────────┐            │
│  │           Cloud Run Services Module                  │            │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ │            │
│  │  │api-service│ extraction │ grounding │ │ hitl-ui │ │            │
│  │  └──────────┘ └──────────┘ └──────────┘ └─────────┘ │            │
│  │  Each with: VPC connector, env vars, secrets, IAM   │            │
│  └──────────────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    GCP Production Environment                        │
├─────────────────────────────────────────────────────────────────────┤
│  Cloud Run Services → VPC Connector → Cloud SQL (private IP)        │
│  Containers from Artifact Registry → Secret Manager → env vars      │
│  IAM service accounts → least privilege access                      │
│  GCS bucket → PDF storage → signed URLs                             │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Integration with Existing Architecture |
|-----------|----------------|----------------------------------------|
| **Foundation Module** | GCP project setup, API enablement, Artifact Registry | NEW - Manages GCP APIs and container registry for Dockerfiles |
| **Networking Module** | VPC, VPC Serverless Connector, firewall rules | NEW - Enables Cloud Run to Cloud SQL private communication |
| **Secrets Module** | Secret Manager, secret versions, IAM bindings | NEW - Replaces .env files with Secret Manager in production |
| **Database Module** | Cloud SQL PostgreSQL 16, private IP, backups | REPLACES - Docker Compose `db` service with managed Cloud SQL |
| **Cloud Run Services Module** | Deploy 4 containerized services with env vars, secrets, VPC | DEPLOYS - Existing Dockerfiles (api, extraction, grounding, ui) |
| **IAM Module** | Service accounts, role bindings, least privilege | NEW - Production service identity management |
| **Storage Module** | GCS bucket for PDFs, lifecycle policies | ENHANCES - Production GCS bucket (local dev uses mock/local storage) |

## Recommended Terraform Project Structure

```
infra/terraform/
├── README.md                        # Deployment instructions
├── main.tf                          # Root module - orchestrates all modules
├── variables.tf                     # Root-level input variables
├── outputs.tf                       # Root-level outputs (service URLs, DB connection)
├── terraform.tfvars                 # Environment-specific values (gitignored)
├── terraform.tfvars.example         # Template for terraform.tfvars
├── backend.tf                       # GCS backend for state management
├── provider.tf                      # GCP provider configuration
│
├── modules/                         # Reusable Terraform modules
│   ├── foundation/                  # Project setup and Artifact Registry
│   │   ├── main.tf                  # google_project_service, google_artifact_registry_repository
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── README.md
│   ├── networking/                  # VPC and VPC Serverless Connector
│   │   ├── main.tf                  # google_compute_network, google_vpc_access_connector
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── README.md
│   ├── secrets/                     # Secret Manager secrets
│   │   ├── main.tf                  # google_secret_manager_secret, google_secret_manager_secret_version
│   │   ├── variables.tf             # Accepts sensitive values from root module
│   │   ├── outputs.tf               # Secret IDs for Cloud Run reference
│   │   └── README.md
│   ├── database/                    # Cloud SQL PostgreSQL
│   │   ├── main.tf                  # google_sql_database_instance, google_sql_database, google_sql_user
│   │   ├── variables.tf
│   │   ├── outputs.tf               # Connection name, private IP
│   │   └── README.md
│   ├── cloud-run-service/           # Reusable Cloud Run service module
│   │   ├── main.tf                  # google_cloud_run_v2_service, google_cloud_run_service_iam_member
│   │   ├── variables.tf             # Service name, image, env vars, secrets, VPC connector
│   │   ├── outputs.tf               # Service URL, service name
│   │   └── README.md
│   ├── iam/                         # Service accounts and IAM bindings
│   │   ├── main.tf                  # google_service_account, google_project_iam_member
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── README.md
│   └── storage/                     # GCS bucket for PDFs
│       ├── main.tf                  # google_storage_bucket, google_storage_bucket_iam_member
│       ├── variables.tf
│       ├── outputs.tf
│       └── README.md
│
├── environments/                    # (Optional) Environment-specific configs
│   ├── dev/
│   │   ├── terraform.tfvars
│   │   └── backend.tf
│   ├── staging/
│   │   ├── terraform.tfvars
│   │   └── backend.tf
│   └── prod/
│       ├── terraform.tfvars
│       └── backend.tf
│
└── scripts/                         # Helper scripts
    ├── init-backend.sh              # Create GCS bucket for Terraform state
    ├── build-and-push.sh            # Build Docker images, push to Artifact Registry
    └── deploy.sh                    # terraform init, plan, apply workflow
```

### Structure Rationale

- **modules/**: Each module represents a logical grouping of GCP resources with clear boundaries. Modules are reusable across environments (dev/staging/prod).
- **cloud-run-service/**: Generic module invoked 4 times (api, extraction, grounding, ui) with different parameters. Avoids code duplication.
- **secrets/**: Centralized secret creation. Root module passes sensitive values (from tfvars or env vars), this module creates Secret Manager secrets and versions.
- **environments/**: Optional multi-environment support. For single-environment deployments (pilot), use root-level terraform.tfvars.
- **scripts/**: Automation for CI/CD. build-and-push.sh bridges Docker build with Terraform (builds images, pushes to Artifact Registry, updates tfvars with image tags).

## Architectural Patterns

### Pattern 1: Environment Variable Flow - .env → terraform.tfvars → Secret Manager → Cloud Run

**What:** Local development uses .env files for configuration. Production uses Secret Manager for secrets and Terraform variables for non-sensitive config. The flow is: developer edits .env → manually maps to terraform.tfvars → Terraform creates Secret Manager secrets → Cloud Run services reference secrets via environment variables.

**When to use:** When transitioning from Docker Compose local development to GCP Cloud Run production. Separates sensitive (secrets) from non-sensitive (API URLs, ports) configuration. Enables secret rotation without code changes.

**Trade-offs:**
- **Pro:** Secrets never in source control; Secret Manager provides versioning, audit logs, IAM-controlled access; Cloud Run services get updated secrets on restart; clear separation of dev (local .env) and prod (Secret Manager).
- **Con:** Manual mapping from .env to terraform.tfvars (error-prone); secrets must be created before Terraform can reference them; requires Secret Manager API enabled; adds operational complexity vs hardcoded env vars.

**Example:**
```hcl
# infra/terraform/terraform.tfvars (gitignored)
project_id = "clinical-trials-prod"
region     = "us-central1"

# Database credentials (will be stored in Secret Manager)
db_password = "super-secret-password"  # From .env POSTGRES_PASSWORD
umls_api_key = "umls-api-key-value"    # From .env UMLS_API_KEY

# Non-sensitive config
database_name = "clinical_trials"      # From .env POSTGRES_DB
cors_origins  = "https://app.example.com"  # From .env CORS_ORIGINS

# infra/terraform/modules/secrets/main.tf
resource "google_secret_manager_secret" "db_password" {
  secret_id = "db-password"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password  # From terraform.tfvars
}

# infra/terraform/main.tf
module "api_service" {
  source = "./modules/cloud-run-service"

  service_name = "api-service"
  image        = "us-central1-docker.pkg.dev/${var.project_id}/app-repo/api-service:latest"

  # Environment variables (non-sensitive)
  env_vars = {
    DATABASE_NAME = var.database_name
    CORS_ORIGINS  = var.cors_origins
  }

  # Secrets (sensitive, from Secret Manager)
  secrets = {
    DATABASE_PASSWORD = {
      secret_name    = module.secrets.db_password_secret_id
      secret_version = "latest"  # Or pin to specific version
    }
    UMLS_API_KEY = {
      secret_name    = module.secrets.umls_api_key_secret_id
      secret_version = "latest"
    }
  }
}

# infra/terraform/modules/cloud-run-service/main.tf
resource "google_cloud_run_v2_service" "service" {
  name     = var.service_name
  location = var.region

  template {
    containers {
      image = var.image

      # Non-sensitive environment variables
      dynamic "env" {
        for_each = var.env_vars
        content {
          name  = env.key
          value = env.value
        }
      }

      # Secrets as environment variables
      dynamic "env" {
        for_each = var.secrets
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value.secret_name
              version = env.value.secret_version
            }
          }
        }
      }
    }

    vpc_access {
      connector = var.vpc_connector_id
      egress    = "PRIVATE_RANGES_ONLY"  # Only use VPC for private IPs (Cloud SQL)
    }
  }
}
```

**Mapping Process:**
```bash
# Local .env
POSTGRES_PASSWORD=local-dev-password
UMLS_API_KEY=dev-api-key

# Developer creates infra/terraform/terraform.tfvars (gitignored)
db_password = "production-password"  # NEVER copy from .env - use prod values
umls_api_key = "prod-api-key"
```

### Pattern 2: VPC Serverless Connector for Cloud SQL Private IP Access

**What:** Cloud Run services are serverless and don't natively run in a VPC. To connect to Cloud SQL via private IP (more secure, no public IP exposure), you create a VPC Serverless Connector. This connector acts as a bridge between Cloud Run and the VPC where Cloud SQL has a private IP. Cloud Run sends traffic through the connector to reach Cloud SQL.

**When to use:** When Cloud SQL should not have a public IP for security reasons. Required for HIPAA/SOC2 compliance where database access must be restricted to internal networks. Reduces attack surface by eliminating public database endpoints.

**Trade-offs:**
- **Pro:** Enhanced security (no public IP); traffic stays within Google's network; supports existing VPC firewall rules; enables access to other VPC resources (Cloud Memorystore, internal services).
- **Con:** Additional cost (~$0.06/hour per connector instance); requires VPC and subnet setup; connector has throughput limits (300 Mbps default, 1 Gbps max); adds complexity vs public IP with Cloud SQL Proxy; connector requires its own /28 subnet.

**Example:**
```hcl
# infra/terraform/modules/networking/main.tf
resource "google_compute_network" "vpc" {
  name                    = "clinical-trials-vpc"
  auto_create_subnetworks = false
}

# Subnet for VPC Connector (requires /28 CIDR block)
resource "google_compute_subnetwork" "vpc_connector_subnet" {
  name          = "vpc-connector-subnet"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = "10.8.0.0/28"  # 16 IPs for connector instances
}

# VPC Serverless Connector
resource "google_vpc_access_connector" "connector" {
  name          = "cloud-run-connector"
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = "10.8.0.0/28"  # Must match subnet

  min_instances = 2
  max_instances = 3

  machine_type = "e2-micro"  # Sufficient for <50 protocols/month
}

# infra/terraform/modules/database/main.tf
resource "google_sql_database_instance" "postgres" {
  name             = "clinical-trials-db"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier = "db-f1-micro"  # Smallest tier for pilot

    ip_configuration {
      ipv4_enabled    = false  # No public IP
      private_network = var.vpc_id
      require_ssl     = true
    }

    backup_configuration {
      enabled    = true
      start_time = "03:00"  # Daily backups at 3 AM UTC
    }
  }

  depends_on = [google_service_networking_connection.private_vpc_connection]
}

# Required for Cloud SQL private IP
resource "google_compute_global_address" "private_ip_address" {
  name          = "private-ip-address"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = var.vpc_id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = var.vpc_id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_address.name]
}

# infra/terraform/modules/cloud-run-service/main.tf
resource "google_cloud_run_v2_service" "service" {
  # ... (other config)

  template {
    containers {
      # ... (image, env vars)

      # Cloud SQL connection via private IP
      env {
        name  = "DATABASE_URL"
        value = "postgresql://${var.db_user}:${var.db_password}@${var.cloud_sql_private_ip}:5432/${var.db_name}"
      }
    }

    # VPC Connector enables private IP access
    vpc_access {
      connector = var.vpc_connector_id
      egress    = "PRIVATE_RANGES_ONLY"  # Only VPC traffic goes through connector
    }
  }
}
```

**Dependency Order:**
1. VPC network
2. VPC connector subnet
3. VPC Serverless Connector
4. Service networking connection (for Cloud SQL private IP peering)
5. Cloud SQL instance (with private IP)
6. Cloud Run services (reference VPC connector and Cloud SQL private IP)

### Pattern 3: Artifact Registry Integration with Existing Dockerfiles

**What:** Existing Dockerfiles in `services/api-service/`, `services/extraction-service/`, `services/grounding-service/`, and `apps/hitl-ui/` are built and pushed to GCP Artifact Registry. Terraform creates the Artifact Registry repository, but does not build images (that's handled by CI/CD or manual scripts). Cloud Run services reference images by full Artifact Registry URL.

**When to use:** When transitioning from Docker Compose (local builds) to GCP Cloud Run (registry-hosted images). Decouples infrastructure provisioning (Terraform) from application builds (Docker/CI). Enables immutable deployments with versioned container images.

**Trade-offs:**
- **Pro:** Artifact Registry is GCP-native, integrated with IAM; supports vulnerability scanning; close proximity to Cloud Run (fast pulls); versioning via image tags; cheaper than alternatives (Docker Hub, ECR cross-region).
- **Con:** Images must be built and pushed before Terraform can deploy Cloud Run services; requires authentication (gcloud auth configure-docker); adds build step to deployment workflow; storage costs for image history.

**Example:**
```hcl
# infra/terraform/modules/foundation/main.tf
# Enable required APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "artifactregistry.googleapis.com",
    "run.googleapis.com",
    "sql-component.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "vpcaccess.googleapis.com",
  ])

  project = var.project_id
  service = each.key

  disable_on_destroy = false
}

# Artifact Registry repository for Docker images
resource "google_artifact_registry_repository" "app_repo" {
  location      = var.region
  repository_id = "app-repo"
  format        = "DOCKER"

  description = "Docker images for Clinical Trials services"

  depends_on = [google_project_service.apis]
}

# Grant Cloud Run service accounts pull access
resource "google_artifact_registry_repository_iam_member" "cloud_run_reader" {
  location   = google_artifact_registry_repository.app_repo.location
  repository = google_artifact_registry_repository.app_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${var.cloud_run_service_account_email}"
}
```

**Build and Push Script (scripts/build-and-push.sh):**
```bash
#!/bin/bash
set -e

PROJECT_ID="clinical-trials-prod"
REGION="us-central1"
REPO="app-repo"

# Authenticate with Artifact Registry
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# Build and push each service
SERVICES=("api-service" "extraction-service" "grounding-service")
for service in "${SERVICES[@]}"; do
  IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${service}:$(git rev-parse --short HEAD)"

  docker build -t ${IMAGE_TAG} -f services/${service}/Dockerfile .
  docker push ${IMAGE_TAG}

  echo "${service} image: ${IMAGE_TAG}"
done

# Build and push UI (different path)
UI_IMAGE_TAG="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/hitl-ui:$(git rev-parse --short HEAD)"
docker build -t ${UI_IMAGE_TAG} -f apps/hitl-ui/Dockerfile .
docker push ${UI_IMAGE_TAG}

echo "hitl-ui image: ${UI_IMAGE_TAG}"
echo ""
echo "Update terraform.tfvars with these image tags before deploying"
```

**Terraform Variables (terraform.tfvars):**
```hcl
# Updated by build-and-push.sh or CI/CD
api_service_image        = "us-central1-docker.pkg.dev/clinical-trials-prod/app-repo/api-service:a3f2c1d"
extraction_service_image = "us-central1-docker.pkg.dev/clinical-trials-prod/app-repo/extraction-service:a3f2c1d"
grounding_service_image  = "us-central1-docker.pkg.dev/clinical-trials-prod/app-repo/grounding-service:a3f2c1d"
hitl_ui_image            = "us-central1-docker.pkg.dev/clinical-trials-prod/app-repo/hitl-ui:a3f2c1d"
```

**Workflow:**
1. Developer makes code changes
2. Run `scripts/build-and-push.sh` (builds 4 images, pushes to Artifact Registry)
3. Update `terraform.tfvars` with new image tags
4. Run `terraform apply` (deploys Cloud Run services with new images)

### Pattern 4: IAM Service Accounts with Least Privilege

**What:** Each Cloud Run service runs with its own dedicated service account, granted only the minimum IAM roles needed for its function. api-service needs Cloud SQL Client and Storage Object Viewer (read PDFs from GCS). extraction-service and grounding-service need Cloud SQL Client only. hitl-ui needs no backend permissions (static frontend, talks to api-service). This follows the principle of least privilege.

**When to use:** Always, for production deployments. Reduces blast radius of security incidents. Enables IAM-based audit trails (which service accessed what). Required for SOC2/HIPAA compliance.

**Trade-offs:**
- **Pro:** Security isolation; precise audit trails; compromised service can't access other resources; easier to debug permission issues (clear role boundaries); supports Workload Identity Federation for cross-cloud.
- **Con:** More IAM resources to manage; requires understanding GCP IAM roles; initial setup complexity; permission changes require Terraform updates; troubleshooting "403 Forbidden" errors.

**Example:**
```hcl
# infra/terraform/modules/iam/main.tf
# Service account for api-service
resource "google_service_account" "api_service" {
  account_id   = "api-service-sa"
  display_name = "API Service Account"
  description  = "Service account for api-service Cloud Run"
}

# Grant Cloud SQL Client role (connect to Cloud SQL)
resource "google_project_iam_member" "api_service_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api_service.email}"
}

# Grant Storage Object Viewer (read PDFs from GCS)
resource "google_storage_bucket_iam_member" "api_service_gcs_viewer" {
  bucket = var.gcs_bucket_name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.api_service.email}"
}

# Grant Secret Manager Secret Accessor (read secrets)
resource "google_secret_manager_secret_iam_member" "api_service_secret_accessor" {
  for_each = toset(var.secret_ids)

  secret_id = each.key
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api_service.email}"
}

# Service account for extraction-service
resource "google_service_account" "extraction_service" {
  account_id   = "extraction-service-sa"
  display_name = "Extraction Service Account"
}

# Extraction service needs Cloud SQL Client only (no GCS - api-service provides signed URLs)
resource "google_project_iam_member" "extraction_service_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.extraction_service.email}"
}

# Grant Secret Manager access for extraction service
resource "google_secret_manager_secret_iam_member" "extraction_service_secret_accessor" {
  for_each = toset(var.secret_ids)

  secret_id = each.key
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.extraction_service.email}"
}

# Service account for grounding-service (same as extraction)
resource "google_service_account" "grounding_service" {
  account_id   = "grounding-service-sa"
  display_name = "Grounding Service Account"
}

resource "google_project_iam_member" "grounding_service_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.grounding_service.email}"
}

# Service account for hitl-ui (minimal permissions - no backend access)
resource "google_service_account" "hitl_ui" {
  account_id   = "hitl-ui-sa"
  display_name = "HITL UI Service Account"
}

# hitl-ui only needs Cloud Run Invoker (self-invoke, no backend access)
# All API calls go to api-service with user auth
```

**Permission Matrix:**

| Service | Cloud SQL Client | Storage Object Viewer | Secret Manager Accessor | Vertex AI User |
|---------|------------------|----------------------|-------------------------|----------------|
| api-service | ✓ | ✓ (GCS bucket) | ✓ | ✗ (via API key) |
| extraction-service | ✓ | ✗ | ✓ | ✓ (Gemini, Document AI) |
| grounding-service | ✓ | ✗ | ✓ | ✓ (MedGemma via Vertex) |
| hitl-ui | ✗ | ✗ | ✗ | ✗ |

### Pattern 5: Terraform State Management with GCS Backend

**What:** Terraform state file is stored in a GCS bucket with versioning enabled. This allows team collaboration (shared state), state locking (prevents concurrent applies), and state recovery (version history). The GCS bucket is created manually before Terraform runs (chicken-and-egg problem: can't use Terraform to create its own state bucket).

**When to use:** Always, for any non-trivial deployment. Required for team collaboration. Enables CI/CD pipelines to run Terraform. Provides state backup and recovery.

**Trade-offs:**
- **Pro:** Team collaboration; state locking prevents conflicts; versioning enables rollback; encrypted at rest; IAM-controlled access; audit logs for state changes.
- **Con:** Manual bucket creation required; requires GCS bucket permissions; state contains sensitive data (protect with IAM); bucket deletion can lose state; cross-region latency for state reads.

**Example:**
```bash
# scripts/init-backend.sh
#!/bin/bash
set -e

PROJECT_ID="clinical-trials-prod"
REGION="us-central1"
BUCKET_NAME="${PROJECT_ID}-terraform-state"

# Create GCS bucket for Terraform state
gcloud storage buckets create gs://${BUCKET_NAME} \
  --project=${PROJECT_ID} \
  --location=${REGION} \
  --uniform-bucket-level-access

# Enable versioning (state recovery)
gcloud storage buckets update gs://${BUCKET_NAME} \
  --versioning

echo "Terraform state bucket created: gs://${BUCKET_NAME}"
echo "Update infra/terraform/backend.tf with this bucket name"
```

```hcl
# infra/terraform/backend.tf
terraform {
  backend "gcs" {
    bucket = "clinical-trials-prod-terraform-state"
    prefix = "terraform/state"  # State file path within bucket

    # Optional: state locking (prevents concurrent applies)
    # GCS backend uses object versioning for locking by default
  }
}
```

```hcl
# infra/terraform/provider.tf
terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"  # Pin major version, allow minor updates
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
```

**Initialization:**
```bash
cd infra/terraform

# First time: create state bucket
../scripts/init-backend.sh

# Initialize Terraform (downloads providers, configures backend)
terraform init

# Migrate existing local state to GCS (if upgrading from local state)
terraform init -migrate-state
```

## Data Flow

### Data Flow 1: .env to GCP Deployment

```
[Developer Local Environment]
    ↓
.env file (gitignored)
  - POSTGRES_PASSWORD=local-dev
  - UMLS_API_KEY=dev-key
  - GCS_BUCKET_NAME=local-test-bucket
    ↓
[Manual Mapping Step]
    ↓
infra/terraform/terraform.tfvars (gitignored)
  - db_password = "prod-password"      # NOT copied from .env
  - umls_api_key = "prod-key"
  - gcs_bucket_name = "prod-bucket"
    ↓
[Terraform Apply]
    ↓
modules/secrets/main.tf
  - Creates Secret Manager secrets
  - Stores secret versions
    ↓
modules/database/main.tf
  - Creates Cloud SQL instance
  - Uses db_password from Secret Manager
    ↓
modules/cloud-run-service/main.tf
  - Creates Cloud Run services
  - Injects env vars from terraform.tfvars
  - References secrets from Secret Manager
    ↓
[GCP Production Environment]
  - Cloud Run services read env vars at startup
  - Secret Manager provides sensitive values
  - Cloud SQL receives connections with credentials from secrets
```

**Key Insight:** .env values are NEVER directly copied to production. Developer manually creates terraform.tfvars with production values. Secrets stored in Secret Manager, not tfvars (tfvars is input to Terraform, which creates secrets).

### Data Flow 2: Container Build to Cloud Run Deployment

```
[Developer Code Changes]
    ↓
services/*/Dockerfile (existing)
apps/hitl-ui/Dockerfile (existing)
    ↓
[scripts/build-and-push.sh]
  1. gcloud auth configure-docker
  2. docker build -t <ARTIFACT_REGISTRY_URL>:<git-sha> -f services/api-service/Dockerfile .
  3. docker push <ARTIFACT_REGISTRY_URL>:<git-sha>
  4. Repeat for extraction, grounding, hitl-ui
    ↓
[Artifact Registry]
  - Stores 4 container images with git-sha tags
  - Images: api-service:a3f2c1d, extraction-service:a3f2c1d, etc.
    ↓
[Update terraform.tfvars]
  - api_service_image = "us-central1-docker.pkg.dev/.../api-service:a3f2c1d"
  - extraction_service_image = "..."
    ↓
[terraform apply]
    ↓
modules/cloud-run-service/main.tf
  - Creates/updates google_cloud_run_v2_service
  - Sets container.image to Artifact Registry URL
    ↓
[Cloud Run Deployment]
  - Pulls image from Artifact Registry
  - Starts container with env vars and secrets
  - Connects to Cloud SQL via VPC Connector
    ↓
[Production Service Running]
  - Serves traffic at Cloud Run URL
  - Access to Cloud SQL, GCS, Secret Manager via IAM
```

**Automation Opportunity:** CI/CD (Cloud Build, GitHub Actions) can automate build-and-push.sh → update tfvars → terraform apply.

### Data Flow 3: Cloud Run to Cloud SQL via VPC Connector

```
[Cloud Run Service Starts]
    ↓
Reads DATABASE_URL from environment variables
  - Format: postgresql://user:password@PRIVATE_IP:5432/dbname
  - Password from Secret Manager
  - Private IP from Cloud SQL instance
    ↓
[VPC Connector Configuration]
  - vpc_access.connector = projects/.../locations/.../connectors/cloud-run-connector
  - vpc_access.egress = "PRIVATE_RANGES_ONLY"
    ↓
[Application Database Query]
  - App opens TCP connection to Cloud SQL private IP (10.x.x.x)
    ↓
[Cloud Run Routing]
  - Detects destination is private IP (10.x.x.x)
  - Routes through VPC Connector (not public internet)
    ↓
[VPC Connector]
  - Forwards traffic to VPC network
  - Uses service account IAM permissions
    ↓
[Cloud SQL Instance]
  - Receives connection on private IP
  - Validates service account has cloudsql.client role
  - Accepts connection
    ↓
[Query Execution]
  - Cloud SQL processes query
  - Returns result via VPC Connector
    ↓
[Cloud Run Receives Response]
  - Application processes result
  - Returns HTTP response to client
```

**Cost Implication:** VPC Connector runs continuously (~$40-60/month). Alternative: Cloud SQL public IP with Cloud SQL Proxy (cheaper but less secure).

### Data Flow 4: Terraform Resource Creation Order

```
[terraform init]
    ↓
Download google provider, configure GCS backend
    ↓
[terraform plan]
    ↓
Terraform analyzes dependencies and determines creation order:

1. Foundation Module
   - google_project_service (enable APIs)
   - google_artifact_registry_repository
   ↓
2. IAM Module
   - google_service_account (4 service accounts)
   ↓
3. Networking Module
   - google_compute_network (VPC)
   - google_compute_subnetwork (VPC connector subnet)
   - google_vpc_access_connector
   ↓
4. Secrets Module
   - google_secret_manager_secret (db_password, umls_api_key, etc.)
   - google_secret_manager_secret_version
   - google_secret_manager_secret_iam_member (grant service accounts access)
   ↓
5. Database Module
   - google_compute_global_address (private IP range)
   - google_service_networking_connection (VPC peering)
   - google_sql_database_instance (depends_on VPC peering)
   - google_sql_database
   - google_sql_user
   ↓
6. Storage Module
   - google_storage_bucket (GCS for PDFs)
   - google_storage_bucket_iam_member (grant api-service access)
   ↓
7. Cloud Run Services Module (repeated 4 times)
   - google_cloud_run_v2_service (depends on VPC connector, secrets, service accounts)
   - google_cloud_run_service_iam_member (allow public access or Cloud Run Invoker)
   ↓
[terraform apply]
    ↓
Resources created in dependency order
    ↓
[Outputs]
  - api_service_url: https://api-service-xxx-uc.a.run.app
  - hitl_ui_url: https://hitl-ui-xxx-uc.a.run.app
  - cloud_sql_connection_name: project:region:instance
```

**Critical Dependencies:**
- Cloud SQL requires VPC peering to be created first (explicit `depends_on`)
- Cloud Run requires VPC Connector, Service Accounts, Secrets to exist
- Secret IAM bindings require both secrets and service accounts to exist

## Integration Points

### New Components (Terraform Creates)

| Component | Purpose | Replaces/Enhances |
|-----------|---------|-------------------|
| **VPC Network** | Private network for Cloud SQL | NEW - Docker Compose has no equivalent |
| **VPC Serverless Connector** | Bridge between Cloud Run and VPC | NEW - Enables private IP access |
| **Cloud SQL Instance** | Managed PostgreSQL 16 database | REPLACES Docker Compose `db` service |
| **Artifact Registry Repository** | Container image storage | NEW - Local Docker images in dev |
| **Secret Manager Secrets** | Secure secret storage | REPLACES .env files in production |
| **Service Accounts** | IAM identity for Cloud Run services | NEW - No equivalent in local dev |
| **GCS Bucket** | PDF protocol storage | ENHANCES - Already used in local dev via GOOGLE_APPLICATION_CREDENTIALS |
| **Cloud Run Services (4)** | Serverless container runtime | REPLACES Docker Compose `api`, `extraction`, `grounding`, `ui` services |

### Modified Components (Integration Points)

| Existing Component | Integration Change | Why |
|--------------------|-------------------|-----|
| **Dockerfiles** | Build and push to Artifact Registry | Production images hosted centrally |
| **Database Migrations (Alembic)** | Run against Cloud SQL instead of local PostgreSQL | Same migrations, different target |
| **Environment Variables** | Read from Cloud Run env vars (injected by Terraform) | Replaces .env file reading |
| **DATABASE_URL** | Points to Cloud SQL private IP | Format: `postgresql://user:pass@10.x.x.x:5432/db` |
| **GCS_BUCKET_NAME** | Points to production GCS bucket | Terraform creates bucket, app uses same GCS client code |
| **UMLS_API_KEY** | Read from Secret Manager via env var | Same code, secret source changes |

### Services That Don't Change

| Service | Why No Change |
|---------|---------------|
| **MLflow** | Not deployed to GCP in initial milestone (local dev only) |
| **PubSub Emulator** | Local dev only; production will use Cloud Pub/Sub (future milestone) |
| **UMLS MCP Server** | Deployment not in scope (assume external/local for now) |

## Build Order and Dependencies

### Phase 1: Foundation Setup (Week 1)

**New Components:**
- GCS bucket for Terraform state (manual: `scripts/init-backend.sh`)
- `infra/terraform/backend.tf`, `provider.tf`, `variables.tf`, `outputs.tf`
- `modules/foundation/`: Enable GCP APIs, create Artifact Registry
- `scripts/build-and-push.sh`: Build and push Docker images

**Integration Points:**
- Existing Dockerfiles remain unchanged
- Build script references existing Dockerfiles

**Testing:**
```bash
cd infra/terraform
terraform init  # Configure GCS backend
terraform plan  # Verify foundation module
terraform apply # Enable APIs, create Artifact Registry

# Build and push images
../scripts/build-and-push.sh
# Verify images in Artifact Registry via GCP Console
```

**Dependencies:** None (foundational resources)

---

### Phase 2: Networking and IAM (Week 1-2)

**New Components:**
- `modules/networking/`: VPC, VPC Connector
- `modules/iam/`: Service accounts for 4 services

**Integration Points:**
- VPC Connector subnet range must not conflict with existing network ranges
- Service account emails will be used in Cloud Run services

**Testing:**
```bash
terraform plan  # Verify VPC and service accounts
terraform apply
# Verify VPC Connector is "Ready" in GCP Console (takes 2-3 minutes)
```

**Dependencies:** Foundation (APIs must be enabled)

---

### Phase 3: Secrets and Database (Week 2)

**New Components:**
- `modules/secrets/`: Secret Manager secrets and versions
- `modules/database/`: Cloud SQL PostgreSQL 16 with private IP
- `terraform.tfvars`: Developer creates from `terraform.tfvars.example`

**Integration Points:**
- Secrets replace .env file values (manual mapping from .env to tfvars)
- Cloud SQL replaces Docker Compose `db` service
- Database migrations (Alembic) target Cloud SQL

**Testing:**
```bash
# Create terraform.tfvars (gitignored)
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with production secrets

terraform plan  # Verify secrets and Cloud SQL
terraform apply

# Test database connection via Cloud SQL Proxy
gcloud sql connect clinical-trials-db --user=postgres
# Run Alembic migrations against Cloud SQL
cd ../../services/api-service
DATABASE_URL="postgresql://..." uv run alembic upgrade head
```

**Dependencies:**
- Networking (Cloud SQL requires VPC peering)
- IAM (Secret Manager IAM bindings require service accounts)

**Critical:** Cloud SQL instance creation takes 5-10 minutes. Use explicit `depends_on` for VPC peering.

---

### Phase 4: Storage (Week 2)

**New Components:**
- `modules/storage/`: GCS bucket for PDF protocols
- Bucket IAM bindings (api-service can read/write)

**Integration Points:**
- Existing GCS client code in api-service unchanged
- Update GCS_BUCKET_NAME in terraform.tfvars to point to production bucket

**Testing:**
```bash
terraform plan  # Verify GCS bucket
terraform apply

# Test upload via gsutil
echo "test" | gsutil cp - gs://clinical-trials-prod-pdfs/test.txt
gsutil cat gs://clinical-trials-prod-pdfs/test.txt
```

**Dependencies:** IAM (bucket IAM bindings require service accounts)

---

### Phase 5: Cloud Run Services (Week 3)

**New Components:**
- `modules/cloud-run-service/`: Reusable Cloud Run service module
- Root `main.tf`: Invoke cloud-run-service module 4 times

**Integration Points:**
- Cloud Run services reference Artifact Registry images (built in Phase 1)
- Env vars and secrets injected from terraform.tfvars and Secret Manager
- VPC Connector enables Cloud SQL private IP access
- Service accounts provide IAM permissions

**Testing:**
```bash
# Ensure images are built and pushed (from Phase 1)
# Update terraform.tfvars with image URLs

terraform plan  # Verify 4 Cloud Run services
terraform apply

# Test each service endpoint
curl https://api-service-xxx-uc.a.run.app/health
curl https://hitl-ui-xxx-uc.a.run.app  # Should serve React app
```

**Dependencies:**
- Artifact Registry (images must exist)
- VPC Connector (for Cloud SQL access)
- Secrets (for env vars)
- Service Accounts (for IAM)
- Cloud SQL (database must be running)

**Critical:** Cloud Run services will fail to start if:
- Image doesn't exist in Artifact Registry
- Secret version doesn't exist
- Service account lacks Secret Manager access
- Cloud SQL is unreachable (VPC Connector issues)

---

### Phase 6: End-to-End Testing (Week 3-4)

**Integration Tests:**
1. **Upload Protocol (api-service → GCS)**
   - POST /protocols/upload → generates signed URL
   - Upload PDF to GCS
   - Verify Protocol record in Cloud SQL

2. **Extraction Workflow (api-service → extraction-service)**
   - Trigger extraction workflow
   - extraction-service fetches PDF from GCS (via signed URL from api-service)
   - extraction-service calls Gemini API (via GOOGLE_APPLICATION_CREDENTIALS secret)
   - Verify CriteriaBatch in Cloud SQL

3. **Grounding Workflow (extraction-service → grounding-service)**
   - Trigger grounding workflow
   - grounding-service loads criteria from Cloud SQL
   - grounding-service calls MedGemma (Vertex AI)
   - Verify Entity records in Cloud SQL

4. **HITL Review (hitl-ui → api-service)**
   - Load HITL UI in browser
   - Verify criteria appear in review queue
   - Approve criteria
   - Verify status update in Cloud SQL

**Dependencies:** All previous phases complete

---

### Phase 7: CI/CD and Documentation (Week 4)

**New Components:**
- `.github/workflows/deploy.yml` or Cloud Build config
- `infra/terraform/README.md`: Deployment instructions
- `terraform.tfvars.example`: Template for production values

**Integration Points:**
- CI/CD builds images on git push
- CI/CD pushes to Artifact Registry
- CI/CD runs `terraform apply` with updated image tags
- Automated testing before deployment

**Testing:**
- Push code to GitHub/GitLab
- Verify CI/CD pipeline runs
- Verify new Cloud Run revision deployed

**Dependencies:** All previous phases (full infrastructure exists)

---

## Dependency Graph

```
Phase 1 (Foundation)
    ↓
Phase 2 (Networking + IAM)
    ↓
Phase 3 (Secrets + Database) ←┐
    ↓                          │
Phase 4 (Storage)              │
    ↓                          │
Phase 5 (Cloud Run) ───────────┘ (depends on all previous)
    ↓
Phase 6 (E2E Testing)
    ↓
Phase 7 (CI/CD)
```

**Critical Path:** 1 → 2 → 3 → 5 (must be sequential)
**Parallel Work:** Phase 4 (Storage) can be done in parallel with Phase 3 (both depend on Phase 2)

## Anti-Patterns

### Anti-Pattern 1: Hardcoding Secrets in terraform.tfvars Committed to Git

**What people do:** Store `terraform.tfvars` with production secrets in Git (not gitignored), or commit secrets directly in Terraform code.

**Why it's wrong:** Secrets exposed in Git history forever (even if later removed). Anyone with repo access can see production credentials. Violates security compliance (SOC2, HIPAA). Secret rotation requires Git commits.

**Do this instead:**
- Add `terraform.tfvars` to `.gitignore`
- Create `terraform.tfvars.example` template (committed, no secrets)
- Store secrets in Secret Manager, pass sensitive variables via environment variables (`TF_VAR_db_password`) or secure CI/CD secret stores
- Use `sensitive = true` in variable definitions to prevent Terraform from logging values

```hcl
# variables.tf
variable "db_password" {
  type      = string
  sensitive = true  # Terraform won't show value in logs
}

# .gitignore
terraform.tfvars
*.tfvars  # Never commit tfvars files
```

### Anti-Pattern 2: Using "latest" for Secret Versions in Production

**What people do:** Configure Cloud Run services to reference `version = "latest"` for Secret Manager secrets.

**Why it's wrong:** Secret updates don't propagate to running Cloud Run instances until restart. "Latest" creates uncertainty about which secret version is in use. Rollback becomes difficult (can't pin to previous version). Debugging issues requires checking secret history.

**Do this instead:** Pin secrets to specific versions in production. Use Terraform to manage secret versions. When rotating secrets, update Terraform with new version, then `terraform apply` triggers Cloud Run redeployment with new secret.

```hcl
# BAD: version = "latest"
resource "google_cloud_run_v2_service" "api" {
  template {
    containers {
      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = "db-password"
            version = "latest"  # ❌ Unpredictable
          }
        }
      }
    }
  }
}

# GOOD: Pin to version
resource "google_secret_manager_secret_version" "db_password_v1" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password
}

resource "google_cloud_run_v2_service" "api" {
  template {
    containers {
      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.id
            version = google_secret_manager_secret_version.db_password_v1.version  # ✓ Explicit
          }
        }
      }
    }
  }
}
```

### Anti-Pattern 3: Single Monolithic main.tf for All Resources

**What people do:** Put all Terraform resources (VPC, Cloud SQL, Cloud Run, IAM, Secrets) in a single `main.tf` file.

**Why it's wrong:** Difficult to navigate (hundreds of lines). Hard to test modules independently. Can't reuse code across environments. Changes to one resource risk affecting others. Review PRs is painful. Violates separation of concerns.

**Do this instead:** Use modules to group related resources. Each module has its own `main.tf`, `variables.tf`, `outputs.tf`. Root module orchestrates modules. Follow Google Cloud's best practice: "Group resources by their shared purpose."

```hcl
# BAD: infra/terraform/main.tf (500+ lines)
resource "google_compute_network" "vpc" { ... }
resource "google_vpc_access_connector" "connector" { ... }
resource "google_sql_database_instance" "db" { ... }
resource "google_cloud_run_v2_service" "api" { ... }
resource "google_cloud_run_v2_service" "extraction" { ... }
# ... (more resources)

# GOOD: infra/terraform/main.tf (orchestrator)
module "networking" {
  source = "./modules/networking"
  # ...
}

module "database" {
  source = "./modules/database"
  vpc_id = module.networking.vpc_id
  # ...
}

module "api_service" {
  source          = "./modules/cloud-run-service"
  service_name    = "api-service"
  vpc_connector   = module.networking.vpc_connector_id
  # ...
}
```

### Anti-Pattern 4: Missing depends_on for Cloud SQL Private IP

**What people do:** Create Cloud SQL instance with private IP without explicit `depends_on = [google_service_networking_connection.private_vpc_connection]`.

**Why it's wrong:** Cloud SQL instance creation may fail with "VPC peering not found" error. Terraform's implicit dependency detection doesn't catch this relationship. Race condition: Cloud SQL tries to allocate private IP before VPC peering is ready.

**Do this instead:** Always use explicit `depends_on` for Cloud SQL instance when using private IP. Wait for VPC peering to complete before creating instance.

```hcl
# BAD: Implicit dependencies (will fail)
resource "google_sql_database_instance" "postgres" {
  settings {
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }
  }
  # ❌ Missing depends_on - may fail
}

# GOOD: Explicit dependency
resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_address.name]
}

resource "google_sql_database_instance" "postgres" {
  settings {
    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
    }
  }

  depends_on = [google_service_networking_connection.private_vpc_connection]  # ✓ Explicit
}
```

### Anti-Pattern 5: Building Docker Images in Terraform

**What people do:** Use Terraform `null_resource` with `local-exec` provisioner to build and push Docker images during `terraform apply`.

**Why it's wrong:** Terraform is for infrastructure, not application builds. `local-exec` is fragile (requires Docker installed on Terraform runner). Terraform state becomes tied to image builds. Image builds don't benefit from Terraform's idempotency. Rebuilds on every `terraform apply` even if code unchanged.

**Do this instead:** Separate concerns: CI/CD builds images, Terraform deploys infrastructure. Use `scripts/build-and-push.sh` or CI/CD pipeline to build and push images. Update `terraform.tfvars` with new image tags. Run `terraform apply` to deploy Cloud Run services with new images.

```hcl
# BAD: Building images in Terraform
resource "null_resource" "build_api_service" {
  provisioner "local-exec" {
    command = "docker build -t ${var.image_url} . && docker push ${var.image_url}"
    working_dir = "${path.root}/../../services/api-service"
  }

  triggers = {
    always_run = timestamp()  # ❌ Runs on every apply
  }
}

# GOOD: Separate build script (scripts/build-and-push.sh)
# Then reference pre-built images in Terraform
module "api_service" {
  source = "./modules/cloud-run-service"
  image  = var.api_service_image  # ✓ Pre-built, passed via tfvars
}
```

## Sources

**Terraform Best Practices:**
- [Terraform Best Practices on Google Cloud: A Practical Guide](https://medium.com/@truonghongcuong68/terraform-best-practices-on-google-cloud-a-practical-guide-057f96b19489)
- [Best practices for Terraform operations - Google Cloud](https://docs.cloud.google.com/docs/terraform/best-practices/operations)
- [Best practices for general style and structure - Google Cloud](https://docs.cloud.google.com/docs/terraform/best-practices/general-style-structure)
- [Terraform GCP Provider: 5 Best Practices from Real Projects](https://controlmonkey.io/resource/terraform-gcp-provider-best-practices/)

**Cloud Run and Infrastructure:**
- [VPC with connectors - Cloud Run Documentation](https://docs.cloud.google.com/run/docs/configuring/vpc-connectors)
- [Connect from Cloud Run - Cloud SQL for MySQL](https://docs.cloud.google.com/sql/docs/mysql/connect-run)
- [Configure secrets for services - Cloud Run](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
- [Configure environment variables for services - Cloud Run](https://docs.cloud.google.com/run/docs/configuring/services/environment-variables)
- [Deploying to Cloud Run - Artifact Registry](https://cloud.google.com/artifact-registry/docs/integrate-cloud-run)

**VPC and Networking:**
- [GCP-CloudRun-VPC-Integration-Module](https://github.com/RuneDD/GCP-CloudRun-VPC-Integration-Module)
- [Building a Secure Serverless Microservice on GCP with VPC and Terraform](https://medium.com/@asifsource/building-a-secure-serverless-microservice-on-gcp-with-vpc-and-terraform-05a1231fb972)
- [A Complete Guide to GCP Serverless with Terraform](https://medium.com/@williamwarley/a-complete-guide-to-gcp-serverless-with-terraform-29a3486094f2)

**Secret Manager and Environment Variables:**
- [Securely using dotenv (.env) files with Google Cloud Run and Terraform](https://mikesparr.medium.com/securely-using-dotenv-env-files-with-google-cloud-run-and-terraform-e8b14ff04bff)
- [Environment Variable Management with Terraform and Google Cloud Secrets Manager](https://zentered.co/articles/environment-variable-managent-with-terraform/)

**Monorepo and Module Organization:**
- [Terraform Monorepo: Structure, Benefits & Best Practices](https://spacelift.io/blog/terraform-monorepo)
- [Terraform monorepo vs. multi-repo: The great debate](https://www.hashicorp.com/en/blog/terraform-mono-repo-vs-multi-repo-the-great-debate)
- [Managing Terraform Modules in a Monorepo](https://medium.com/@hello_9187/managing-terraform-modules-in-a-monorepo-e7e89d124d4a)

**Artifact Registry and CI/CD:**
- [Provision Artifact Registry resources with Terraform - Google Cloud](https://docs.cloud.google.com/artifact-registry/docs/repositories/terraform)
- [Integrating our Application CI/CD Pipelines and Terraform GitOps with Cloud Build](https://medium.com/google-cloud/integrating-our-application-ci-cd-pipelines-and-terraform-gitops-with-cloud-build-35e8d38b8468)
- [Deploying our Video Intelligence Cloud Run Application with CI/CD: Terraform and Cloud Build](https://medium.com/google-cloud/deploying-our-video-intelligence-cloud-run-appication-with-terraform-and-cloud-build-a1f4dac7ba6a)
- [GCP: Terraform automation for Cloud Build and Cloud Deploy](https://medium.com/@1545281333376/gcp-terraform-automation-for-cloud-build-and-cloud-deploy-58d3ba501a63)

**IAM and Security:**
- [Running Infrastructure-as-Code with the least privilege possible - Google Cloud Blog](https://cloud.google.com/blog/products/devops-sre/running-infrastructure-code-least-privilege-possible/)
- [Using Google Cloud Service Account impersonation in your Terraform code](https://cloud.google.com/blog/topics/developers-practitioners/using-google-cloud-service-account-impersonation-your-terraform-code)
- [Implementing IAM access control as code with HashiCorp Terraform](https://cloud.google.com/blog/topics/developers-practitioners/implementing-iam-access-control-code-hashicorp-terraform)

**Dependency Management:**
- [Best practices on dependency management - Terraform on Google Cloud](https://docs.cloud.google.com/docs/terraform/best-practices/dependency-management)

---

*Architecture research for: Terraform GCP Cloud Run Deployment Integration*
*Researched: 2026-02-12*
