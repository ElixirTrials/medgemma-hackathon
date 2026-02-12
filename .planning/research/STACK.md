# Technology Stack

**Project:** Clinical Trial Protocol Criteria Extraction System
**Researched:** 2026-02-12
**Confidence:** HIGH

## Infrastructure & Deployment Stack

This document covers **deployment infrastructure additions** for Terraform-based GCP Cloud Run deployment. Application stack (FastAPI, LangGraph, React) is documented separately and remains unchanged.

### Terraform & Providers

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Terraform | >=1.6.0 | Infrastructure as Code | **GA STABLE**: Version 1.6+ required for google-sql module compatibility. Supports native monorepo patterns (critical for multi-service deployment). HCL syntax stable, wide GCP community adoption. |
| hashicorp/google | ~> 7.0 | GCP resource management | **LATEST GA (v7.19.0, Feb 2025)**: Adds write-only attributes for secrets (prevents DATABASE_URL in state files), enhanced Cloud Run v2 support, automatic resource labeling. Version 7.0+ recommended over 6.x for Secret Manager security improvements. |
| hashicorp/google-beta | ~> 7.0 | Beta GCP features | **PARALLEL WITH GOOGLE PROVIDER**: Required for Cloud Run v2 advanced features (startup probes, VPC egress settings). Must match google provider major version. |
| hashicorp/null | ~> 3.2 | Docker build/push orchestration | **STANDARD FOR CONTAINER BUILDS**: Used with local-exec to build and push Docker images to Artifact Registry during terraform apply. Triggers on content SHA256 changes to avoid unnecessary rebuilds. |

**Confidence:** HIGH - Version 7.19.0 verified from official GitHub releases (Feb 2025). Write-only attributes critical for preventing secret leakage in state files.

### GCP Services

| Service | Terraform Resource | Purpose | Why Needed |
|---------|-------------------|---------|------------|
| Cloud Run (Gen 2) | google_cloud_run_v2_service | Container hosting | **SERVERLESS DEPLOYMENT**: Runs api-service, extraction-service, grounding-service, hitl-ui containers. Gen 2 required for VPC direct egress, startup probes, and better Cloud SQL integration. Autoscales 0→N instances based on traffic. |
| Cloud SQL (PostgreSQL 16) | google_sql_database_instance | Production database | **MANAGED POSTGRESQL**: Replaces Docker Compose postgres. Requires private IP (VPC peering) for security. Automatic backups, HA configuration optional. PostgreSQL 16 matches local dev version. |
| Artifact Registry | google_artifact_registry_repository | Container image storage | **DOCKER IMAGE REGISTRY**: Replaces reliance on external registries. Format: us-central1-docker.pkg.dev/PROJECT_ID/REPO_NAME/IMAGE:TAG. Required for Cloud Run deployments within GCP. Supports vulnerability scanning. |
| Secret Manager | google_secret_manager_secret | Secure secret storage | **REPLACES .ENV FILES**: Stores DATABASE_URL, UMLS_API_KEY, OAuth client secrets, Vertex AI keys. Cloud Run mounts as environment variables or files. Versioned, auditable. Critical for production security. |
| VPC & Serverless VPC Connector | google_vpc_access_connector | Private networking | **CLOUD SQL PRIVATE ACCESS**: Allows Cloud Run (serverless) to communicate with Cloud SQL via private IP. Avoids public internet for database traffic. Connector must be in same region as Cloud Run services. |
| IAM Service Accounts | google_service_account | Least-privilege identities | **SECURITY BOUNDARY**: Each service gets dedicated service account (api-sa, extraction-sa, etc.). Grant minimal roles: secretmanager.secretAccessor, cloudsql.client. Prevents default Compute Editor role (excessive permissions). |
| Cloud Storage (GCS) | Already configured | PDF storage | **NO CHANGE NEEDED**: App already uses GCS bucket for protocol PDFs. Terraform will grant service account storage.objectViewer/objectCreator roles. Bucket creation assumed pre-existing. |

**Confidence:** HIGH - All services verified from official Google Cloud documentation (updated Feb 2026). Cloud Run Gen 2 required for VPC direct egress and Cloud SQL Auth Proxy integration.

### Terraform Module Structure (Monorepo)

| Directory | Purpose | Pattern |
|-----------|---------|---------|
| infra/terraform/ | Terraform root modules | Organized by environment: infra/terraform/dev/, infra/terraform/prod/. Each env has separate state, tfvars. |
| infra/terraform/modules/ | Reusable modules | Shared modules: cloud-run-service/, cloud-sql/, vpc-connector/. Versioned via Git tags if extracted to separate repo. For pilot, inline modules sufficient. |
| infra/terraform/common/ | Shared config | backend.tf (GCS state), providers.tf (google provider versions), variables.tf (common vars like project_id, region). |
| infra/terraform/dev/main.tf | Dev environment | Instantiates modules with dev-specific values (min_instances=0, max_instances=10, cpu=1, memory=512Mi). Links to shared backend. |
| infra/terraform/prod/main.tf | Prod environment (future) | Production overrides (min_instances=1, deletion_protection=true, HA database). Separate GCS state bucket prevents cross-env corruption. |

**Pattern:** Terraform native monorepo support (v1.6+) allows modules in same repo. Use relative paths (source = "../../modules/cloud-run-service"). Tag releases with module/VERSION for reproducibility (e.g., cloud-run-service/v1.0.0).

**Confidence:** MEDIUM-HIGH - Monorepo patterns verified from Spacelift and HashiCorp blog (2026). For 50-protocol pilot, simple structure sufficient; extract modules if scaling to multi-region.

### GCP Configuration Patterns

#### Secret Manager Integration

**Pattern:** Store secrets in Secret Manager, mount as env vars in Cloud Run.

```hcl
resource "google_secret_manager_secret" "database_url" {
  secret_id = "database-url"
  replication { automatic = true }
}

resource "google_cloud_run_v2_service" "api" {
  template {
    containers {
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.id
            version = "latest"  # Pin to specific version in prod
          }
        }
      }
    }
  }
}
```

**Why NOT .env files:** Secret Manager provides versioning, audit logs (who accessed when), automatic rotation, and integration with Cloud Run. .env files in containers leak secrets in image layers.

**Confidence:** HIGH - Official Google Cloud Run documentation (Feb 2026) recommends Secret Manager over environment variables for sensitive data.

#### Cloud SQL Private IP with VPC Connector

**Pattern:** Cloud SQL uses private IP, Cloud Run connects via Serverless VPC Connector.

```hcl
# 1. Allocate private IP range for Cloud SQL
resource "google_compute_global_address" "private_ip" {
  name          = "cloudsql-private-ip"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

# 2. Create VPC peering for Cloud SQL
resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip.name]
}

# 3. Cloud SQL instance with private IP
resource "google_sql_database_instance" "main" {
  settings {
    ip_configuration {
      ipv4_enabled    = false  # Disable public IP
      private_network = google_compute_network.vpc.id
    }
  }
  depends_on = [google_service_networking_connection.private_vpc_connection]
}

# 4. VPC Connector for Cloud Run → Cloud SQL
resource "google_vpc_access_connector" "connector" {
  name          = "cloudsql-connector"
  region        = var.region
  network       = google_compute_network.vpc.name
  ip_cidr_range = "10.8.0.0/28"  # /28 = 16 IPs (minimum)
}

# 5. Cloud Run uses connector
resource "google_cloud_run_v2_service" "api" {
  template {
    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"  # Route only private IPs via VPC
    }
  }
}
```

**Alternative:** Cloud SQL Proxy sidecar (deprecated for Cloud Run Gen 2). Use VPC Direct Egress instead.

**Confidence:** HIGH - Private IP pattern standard for production Cloud SQL (Google Cloud docs, Jan 2026). VPC Connector required for serverless → private Cloud SQL.

#### Cloud Run Autoscaling Configuration

**Recommended settings for pilot (50 protocols):**

```hcl
resource "google_cloud_run_v2_service" "api" {
  template {
    scaling {
      min_instance_count = 0  # Scale to zero when idle (cost savings)
      max_instance_count = 10  # Prevent runaway costs
    }

    containers {
      resources {
        limits = {
          cpu    = "1"      # 1 vCPU sufficient for FastAPI
          memory = "512Mi"  # Start small, increase if OOMKilled
        }
        cpu_idle = true  # Allocate CPU only during request processing
      }

      # Concurrency: requests per instance
      # Default 80 for CPU >= 1. Lower for CPU-heavy workloads.
      # max_instance_request_concurrency = 80  # Default, omit unless tuning
    }

    # Health checks
    startup_probe {
      http_get {
        path = "/health"
        port = 8000
      }
      initial_delay_seconds = 10
      timeout_seconds       = 5
      period_seconds        = 10
      failure_threshold     = 3
    }
  }
}
```

**For extraction/grounding services (LangGraph agents):**
- min_instance_count = 1 (avoid cold starts during extraction)
- cpu = "2", memory = "1Gi" (LLM calls CPU/memory intensive)
- max_instance_request_concurrency = 10 (limit concurrent agents)

**Confidence:** HIGH - Autoscaling parameters from official Cloud Run documentation (Feb 2026). Startup probes prevent premature traffic routing.

#### IAM Least Privilege

**Pattern:** Dedicated service account per Cloud Run service with minimal roles.

```hcl
# API service account
resource "google_service_account" "api" {
  account_id   = "api-service"
  display_name = "API Service Account"
}

# Grant only required roles
resource "google_project_iam_member" "api_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_storage_bucket_iam_member" "api_gcs_access" {
  bucket = var.gcs_bucket_name
  role   = "roles/storage.objectViewer"  # Read PDFs
  member = "serviceAccount:${google_service_account.api.email}"
}

# Cloud Run service uses this account
resource "google_cloud_run_v2_service" "api" {
  template {
    service_account = google_service_account.api.email
  }
}
```

**AVOID:** Default Compute Engine service account (has Editor role = read/write on ALL project resources).

**Confidence:** HIGH - Least privilege pattern from Google IAM best practices (Feb 2026). Default service account security risk documented in Cloud Run security guides.

### Terraform State Management

**Backend configuration (GCS):**

```hcl
# infra/terraform/common/backend.tf
terraform {
  backend "gcs" {
    bucket  = "PROJECT_ID-tfstate"  # Create manually before first apply
    prefix  = "env/dev"             # Separate state per environment
    # State locking automatic via GCS generation numbers
  }
}
```

**Best practices:**
1. **Separate state per environment:** dev/tfstate, prod/tfstate (prevents accidental prod changes)
2. **Enable bucket versioning:** Recover from accidental deletions/corruption
3. **Encrypt with KMS:** Customer-managed encryption keys for sensitive state
4. **IAM restrictions:** Only CI/CD pipeline + ops team can write to state bucket

**Confidence:** HIGH - GCS backend standard for GCP Terraform (official HashiCorp docs). State locking via object versioning prevents concurrent applies.

### Container Build & Push Strategy

**Pattern:** Build Docker images locally, push to Artifact Registry via Terraform null_resource.

```hcl
# 1. Create Artifact Registry repository
resource "google_artifact_registry_repository" "main" {
  location      = var.region
  repository_id = "app-images"
  format        = "DOCKER"
}

# 2. Build and push image on Dockerfile changes
resource "null_resource" "build_api_image" {
  triggers = {
    dockerfile_hash = filesha256("${path.module}/../../services/api-service/Dockerfile")
    source_hash     = sha256(join("", [for f in fileset("${path.module}/../../services/api-service", "**") : filesha256("${path.module}/../../services/api-service/${f}")]))
  }

  provisioner "local-exec" {
    command = <<-EOT
      gcloud auth configure-docker ${var.region}-docker.pkg.dev
      docker build -t ${var.region}-docker.pkg.dev/${var.project_id}/app-images/api-service:${var.image_tag} \
        -f services/api-service/Dockerfile .
      docker push ${var.region}-docker.pkg.dev/${var.project_id}/app-images/api-service:${var.image_tag}
    EOT
    working_dir = "${path.module}/../.."
  }
}

# 3. Cloud Run service references pushed image
resource "google_cloud_run_v2_service" "api" {
  template {
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/app-images/api-service:${var.image_tag}"
    }
  }
  depends_on = [null_resource.build_api_image]
}
```

**Alternative:** Cloud Build for CI/CD (future enhancement). For pilot, null_resource sufficient for manual deploys.

**Confidence:** MEDIUM-HIGH - null_resource pattern verified from Medium articles (Oct 2024) and HashiCorp docs. SHA256 triggers ensure rebuilds only when source changes. For production CI/CD, migrate to Cloud Build with automated triggers.

## Installation

### Prerequisites

```bash
# Install Terraform
brew install terraform  # macOS
# OR download from https://developer.hashicorp.com/terraform/install

# Verify version
terraform version  # Should be >= 1.6.0

# Install gcloud CLI (for Docker auth)
brew install --cask google-cloud-sdk  # macOS

# Authenticate
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

### Terraform Initialization

```bash
cd infra/terraform/dev

# Initialize providers and backend
terraform init

# Validate configuration
terraform validate

# Plan changes
terraform plan -var-file=dev.tfvars

# Apply (creates all resources)
terraform apply -var-file=dev.tfvars
```

### Manual Pre-requisites

**Before first terraform apply:**

1. **Create GCS state bucket:**
   ```bash
   gsutil mb -p PROJECT_ID -l us-central1 gs://PROJECT_ID-tfstate
   gsutil versioning set on gs://PROJECT_ID-tfstate
   ```

2. **Enable required APIs:**
   ```bash
   gcloud services enable \
     run.googleapis.com \
     sqladmin.googleapis.com \
     artifactregistry.googleapis.com \
     secretmanager.googleapis.com \
     vpcaccess.googleapis.com \
     servicenetworking.googleapis.com \
     compute.googleapis.com
   ```

3. **Create Secret Manager secrets** (Terraform manages versions, but secrets must exist):
   ```bash
   echo -n "postgresql://user:pass@/db?host=/cloudsql/PROJECT:REGION:INSTANCE" | \
     gcloud secrets create database-url --data-file=-

   echo -n "YOUR_UMLS_KEY" | \
     gcloud secrets create umls-api-key --data-file=-
   ```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Cloud Run Gen 2 | Cloud Run Gen 1 | NEVER for new deployments. Gen 1 lacks VPC direct egress, startup probes, and will be deprecated. |
| Terraform | Google Cloud CLI (gcloud) | If team lacks Terraform expertise or deploying single service (not multi-service monorepo). Loses IaC benefits. |
| Cloud SQL | Cloud Run + AlloyDB | If requiring PostgreSQL 15+ features or >10TB database. Pilot needs <100GB, Cloud SQL sufficient. |
| Artifact Registry | Docker Hub / GCR | Docker Hub has rate limits, GCR deprecated. Artifact Registry integrates with Cloud Run, vulnerability scanning included. |
| Secret Manager | .env in container image | NEVER in production. .env files leak secrets in image layers, no audit trail, no rotation. |
| VPC Connector | Public Cloud SQL IP | NEVER in production. Public IP exposes database to internet (even with Cloud SQL Proxy). VPC private IP required for security. |
| null_resource (build) | Cloud Build | If implementing full CI/CD pipeline (e.g., auto-deploy on git push). For pilot, null_resource simpler for manual deploys. |
| Monorepo modules | Separate module repos | If modules reused across 10+ projects or by multiple teams. For single product, monorepo reduces overhead. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Cloud Run Gen 1 | **DEPRECATED PATH**: Lacks VPC direct egress (requires Cloud SQL Proxy sidecar), no startup probes, fewer autoscaling options. Gen 2 GA since 2022. | Cloud Run Gen 2 (google_cloud_run_v2_service) |
| Compute Engine VMs | **OVER-ENGINEERED**: Requires manual scaling, health checks, load balancer setup. Cloud Run auto-scales 0→N, handles HTTPS, zero ops overhead for pilot. | Cloud Run (serverless) |
| GKE Autopilot | **OVER-ENGINEERED**: Kubernetes overkill for 4 microservices. Adds complexity (YAML, ingress, service mesh). Cloud Run sufficient for 50-protocol pilot. | Cloud Run |
| Cloud SQL public IP | **SECURITY RISK**: Exposes database to internet (even with authorized networks). Private IP + VPC connector encrypts traffic within Google network. | Cloud SQL private IP + VPC peering |
| Default Compute service account | **EXCESSIVE PERMISSIONS**: Has Editor role (read/write on all resources). Violates least privilege. Create security vulnerabilities. | Dedicated service accounts per Cloud Run service with minimal roles |
| Hard-coded secrets in Terraform | **SECRET LEAKAGE**: Secrets in .tf files committed to Git. Terraform state file stores in plaintext. Use Secret Manager + write-only attributes. | Secret Manager with google_secret_manager_secret, mount in Cloud Run |
| Terraform provider google < 6.0 | **MISSING SECURITY FEATURES**: Versions <6.0 lack write-only attributes (passwords in state files), automatic labeling, Cloud Run v2 improvements. | hashicorp/google >= 7.0 |
| Single Terraform state for all envs | **BLAST RADIUS**: Dev terraform apply can accidentally destroy prod. Separate states isolate environments. | Separate GCS state buckets per environment (dev-tfstate, prod-tfstate) |

## Stack Patterns by Deployment Stage

**Pilot (50 protocols, current requirement):**
- Cloud Run Gen 2 with autoscaling (min=0, max=10)
- Cloud SQL single instance (no HA), db-f1-micro (1 vCPU, 3.75GB RAM)
- VPC connector with /28 range (16 IPs)
- Secret Manager for all secrets
- Artifact Registry in single region (us-central1)
- Manual deploys via terraform apply (no CI/CD)

**Production (500+ protocols, future):**
- Cloud Run min_instances=1 (avoid cold starts)
- Cloud SQL HA configuration (automatic failover), db-n1-standard-2 (2 vCPU, 7.5GB RAM)
- VPC connector with /27 range (32 IPs, supports higher throughput)
- Cloud Build CI/CD pipeline (auto-deploy on main branch merge)
- Multi-region Artifact Registry for DR
- Cloud Armor for DDoS protection (if public-facing)

**Multi-region (global deployment):**
- Cloud Run multi-region deployment (load balance via Cloud Load Balancer)
- Cloud SQL cross-region read replicas
- Global Artifact Registry
- Cloud CDN for static assets (HITL UI)

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| terraform@1.6.0 | hashicorp/google@7.x | Terraform 1.6+ required for google-sql module. Tested with 1.7.0. |
| hashicorp/google@7.19.0 | hashicorp/google-beta@7.19.0 | Beta provider must match major.minor version of google provider. Use ~> 7.0 constraint for both. |
| Cloud Run Gen 2 | google provider >= 5.0 | Gen 1 resources deprecated. Use google_cloud_run_v2_service, not google_cloud_run_service. |
| Cloud SQL PostgreSQL 16 | Local dev PostgreSQL 16 | Match versions to avoid migration issues. Cloud SQL supports 12, 13, 14, 15, 16 (latest). |
| null_resource | Terraform >= 0.12 | Part of hashicorp/null provider. Use triggers with filesha256() for content-based builds. |

## Architecture Integration Notes

### Existing Docker Containers → Cloud Run

All existing Dockerfiles work without modification:
- **services/api-service/Dockerfile**: Runs on Cloud Run, port 8000 auto-detected
- **services/extraction-service/Dockerfile**: Runs on Cloud Run, port 8001
- **services/grounding-service/Dockerfile**: Runs on Cloud Run, port 8002
- **apps/hitl-ui/Dockerfile**: Nginx serves React build, Cloud Run detects port 3000

**Changes needed:**
1. Update VITE_API_BASE_URL to Cloud Run service URL (not localhost:8000)
2. Configure CORS_ORIGINS in api-service to allow Cloud Run UI URL
3. Set DATABASE_URL to Cloud SQL connection string (via Secret Manager)

### Database Migration Flow

1. **Local dev** (unchanged): PostgreSQL via Docker Compose
2. **Cloud deployment**: Cloud SQL PostgreSQL 16
3. **Migration path**:
   ```bash
   # Dump local schema (after alembic migrations)
   pg_dump -h localhost -U postgres -d clinical_trials --schema-only > schema.sql

   # Import to Cloud SQL
   gcloud sql import sql INSTANCE_NAME gs://BUCKET/schema.sql --database=clinical_trials

   # Run Alembic migrations in Cloud Run api-service startup
   # (already configured in Dockerfile CMD)
   ```

### Environment Variable Mapping

| Docker Compose (.env) | Cloud Run (Secret Manager) | Terraform Resource |
|-----------------------|---------------------------|-------------------|
| DATABASE_URL | database-url | google_secret_manager_secret.database_url |
| UMLS_API_KEY | umls-api-key | google_secret_manager_secret.umls_api_key |
| GCS_BUCKET_NAME | gcs-bucket-name (config, not secret) | google_cloud_run_v2_service env var |
| VERTEX_AI_PROJECT | Inferred from Cloud Run metadata | N/A (use default project) |
| GOOGLE_APPLICATION_CREDENTIALS | N/A (Cloud Run uses service account) | google_service_account.api |

### MLflow Deployment

**Options:**
1. **Cloud Run MLflow container** (recommended for pilot): Deploy mlflow:v2.16.2 to Cloud Run with Cloud SQL backend
2. **Vertex AI Experiments** (production): Migrate to managed MLflow on Vertex AI (no container management)

For pilot, deploy MLflow as 5th Cloud Run service with persistent Cloud SQL storage.

## Sources

**Terraform Providers:**
- [Terraform Provider Google Releases](https://github.com/hashicorp/terraform-provider-google/releases) - Version 7.19.0 verified (Feb 2025)
- [Terraform Provider for Google Cloud 7.0 GA](https://www.hashicorp.com/en/blog/terraform-provider-for-google-cloud-7-0-is-now-ga) - Write-only attributes, security improvements
- [Google Provider Versions Documentation](https://registry.terraform.io/providers/hashicorp/google/latest/docs/guides/provider_versions) - Version constraints

**Cloud Run:**
- [Cloud Run VPC Connectors](https://docs.cloud.google.com/run/docs/configuring/vpc-connectors) - Official docs (Feb 2026)
- [Cloud Run Health Checks](https://cloud.google.com/run/docs/configuring/healthchecks) - Startup probe configuration (Feb 2026)
- [Cloud Run Autoscaling](https://docs.cloud.google.com/run/docs/about-instance-autoscaling) - Min/max instances, concurrency
- [Cloud Run CPU/Memory Configuration](https://docs.cloud.google.com/run/docs/configuring/services/memory-limits) - Resource limits best practices

**Cloud SQL:**
- [Cloud SQL Private IP Configuration](https://cloud.google.com/sql/docs/postgres/configure-private-ip) - VPC peering setup (Jan 2026)
- [Connect Cloud Run to Cloud SQL](https://docs.cloud.google.com/sql/docs/mysql/connect-run) - Integration patterns
- [Terraform Cloud SQL Module](https://registry.terraform.io/modules/GoogleCloudPlatform/sql-db/google/latest) - Official module (v20.2.0)

**Secret Manager:**
- [Cloud Run Secret Manager Integration](https://cloud.google.com/run/docs/configuring/services/secrets) - Mounting secrets (Feb 2026)
- [Secret Manager Best Practices](https://docs.cloud.google.com/secret-manager/docs) - Security patterns

**IAM & Security:**
- [Service Account Best Practices](https://docs.cloud.google.com/iam/docs/best-practices-service-accounts) - Least privilege patterns
- [Cloud Run IAM Roles](https://docs.cloud.google.com/run/docs/reference/iam/roles) - Role reference
- [Implementing Least Privilege in Cloud Run](https://www.skills.google/focuses/30843?parent=catalog) - Security training

**Artifact Registry:**
- [Provision Artifact Registry with Terraform](https://docs.cloud.google.com/artifact-registry/docs/repositories/terraform) - Official docs
- [Terraform Artifact Registry Module](https://registry.terraform.io/modules/GoogleCloudPlatform/artifact-registry/google/latest) - v0.8.2 (Jan 2026)
- [Automating Docker Builds and Push to Artifact Registry with Terraform](https://medium.com/@jonay.sosag/automate-docker-builds-and-push-to-google-artifact-registry-with-terraform-including-args-e3f0872da2a2) - null_resource pattern

**Terraform State & Structure:**
- [Terraform Backend GCS](https://developer.hashicorp.com/terraform/language/backend/gcs) - Official backend docs
- [Terraform State Management](https://dasroot.net/posts/2026/02/terraform-state-management-remote-state-locking/) - Best practices (Feb 2026)
- [Terraform Monorepo Best Practices](https://spacelift.io/blog/terraform-monorepo) - Module organization
- [Terraform Native Monorepo Support](https://www.hashicorp.com/en/blog/terraform-adds-native-monorepo-support-stack-component-configurations-and-more) - New features

**CI/CD (Future):**
- [Managing Infrastructure as Code with Terraform and Cloud Build](https://cloud.google.com/docs/terraform/resource-management/managing-infrastructure-as-code) - GitOps patterns
- [Cloud Build with Terraform](https://docs.cloud.google.com/build/docs/terraform) - Automation setup

---
*Infrastructure stack research for: Clinical Trial Protocol Criteria Extraction System - Cloud Deployment*
*Researched: 2026-02-12*
*Confidence: HIGH (Terraform provider versions verified from GitHub, GCP service docs current as of Feb 2026)*
