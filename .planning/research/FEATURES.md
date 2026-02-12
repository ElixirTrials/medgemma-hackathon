# Feature Research: Terraform GCP Cloud Run Deployment

**Domain:** Infrastructure deployment for containerized microservices on GCP Cloud Run
**Researched:** 2026-02-12
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = deployment feels incomplete or unprofessional.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Container Registry Integration | Cloud Run requires container images | LOW | Artifact Registry is the standard; existing Dockerfiles already built |
| Environment Variable Configuration | Every deployment needs runtime config | LOW | Terraform `env` blocks; separate from secrets |
| Secret Management (Secret Manager) | Credentials/API keys must be secure | MEDIUM | Secret Manager integration; never use env vars for secrets |
| Cloud SQL Connection | Database connectivity is fundamental | MEDIUM | Unix socket pattern with `/cloudsql/CONNECTION_NAME`; automatic with Cloud Run |
| Health Checks | Service reliability and readiness detection | LOW | Startup probes prevent premature traffic; liveness probes for ongoing health |
| IAM Service Accounts | Least privilege security | MEDIUM | Dedicated service accounts per service; never use default compute SA |
| CI/CD Integration | Automated deployments from GitHub Actions | MEDIUM | Build → Push to Artifact Registry → Terraform apply |
| Remote State (GCS Backend) | Team collaboration, state locking | LOW | GCS bucket with versioning; automatic state locking |
| Multi-Service Deployment | 4 services (API, extraction, grounding, UI) | LOW | Multiple `google_cloud_run_v2_service` resources in same config |
| Basic Autoscaling | Scale to zero, scale up on demand | LOW | Cloud Run default behavior; configure max instances |

### Differentiators (Competitive Advantage)

Features that set the deployment apart. Not required, but valuable for specific use cases.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Terraform Modules for Reusability | DRY principle, consistency across services | LOW | Single module for Cloud Run service; parameters for name, image, env vars |
| VPC Connector (Private Networking) | Secure internal communication, Cloud SQL private IP | MEDIUM | Required if using Cloud SQL private IP; overkill for pilot with public SQL |
| Traffic Splitting / Blue-Green | Gradual rollouts, canary deployments | MEDIUM | Cloud Run native; useful after pilot validation |
| Custom Domain with SSL | Professional URLs, custom branding | LOW | Auto-managed SSL certs; only if pilot has external users |
| Cost Optimization (Min Instances) | Predictable cold start latency | LOW | Set min_instances=1 for critical services; costs ~$10/month per service |
| Startup Probes (Custom Timing) | Fine-tuned health checks for slow-starting services | LOW | LangGraph services may need longer initial_delay_seconds |
| GCS Bucket Terraform Provisioning | Manage existing GCS bucket via IaC | LOW | Protocol storage bucket already exists; add to Terraform for consistency |
| Database Migration in CI/CD | Alembic migrations run pre-deployment | MEDIUM | Already in Dockerfile CMD; ensure idempotent in Cloud Run |
| Structured Logging (Cloud Logging) | Centralized observability | LOW | Automatic with Cloud Run; configure log levels via env vars |
| Terraform Workspaces | Separate dev/staging/prod environments | MEDIUM | Alternative to separate .tfvars files; useful post-pilot |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems for a small pilot.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Multi-Region Deployment | "High availability" mindset | Doubles complexity, costs; pilot doesn't need HA | Single region (us-central1); add multi-region post-validation |
| Complex VPC with Private Service Connect | Security best practice in enterprise | Overkill for pilot; adds networking complexity | Use Cloud SQL public IP with authorized networks; SSL enforced |
| Terraform Cloud/Enterprise | Centralized state, policy enforcement | Monthly cost, learning curve; GCS backend sufficient | GCS backend with state locking; free, simple |
| Over-Granular IAM Policies | Principle of least privilege | Time-consuming for pilot; premature optimization | Start with predefined roles (Cloud Run Admin, Secret Manager Accessor); refine later |
| Load Balancer in Front of Cloud Run | "Production-ready" architecture | Cloud Run has built-in LB; external LB adds cost/complexity | Use Cloud Run's native load balancer; only add external LB for multi-service routing |
| Separate Terraform State per Service | Isolation, independent deployments | State management overhead; harder to manage service dependencies | Single Terraform config for all services; modularize with locals/modules |
| Auto-Scaling to Hundreds of Instances | "Handle viral traffic" | Pilot won't have viral traffic; risk of surprise costs | Set max_instances=10 per service; monitor and adjust |
| Custom VPC for Cloud Run | Network isolation | Cloud Run uses Google-managed VPC by default; custom VPC only needed for VPC connector | Use default Cloud Run networking; add VPC connector only if private Cloud SQL needed |

## Feature Dependencies

```
[Remote State (GCS Backend)]
    └──enables──> [CI/CD Terraform Apply]

[Container Registry (Artifact Registry)]
    └──requires──> [Multi-Service Deployment]
                       └──depends on──> [Existing Dockerfiles]

[Secret Manager]
    └──requires──> [IAM Service Accounts]
                       └──grants──> [Secret Manager Secret Accessor role]

[Cloud SQL Connection]
    └──optionally requires──> [VPC Connector] (if using private IP)
    └──requires──> [IAM Service Accounts]
                       └──grants──> [Cloud SQL Client role]

[Health Checks]
    └──enhances──> [Autoscaling] (prevents premature scaling)

[CI/CD Integration]
    └──requires──> [Remote State (GCS Backend)]
    └──requires──> [Container Registry]
    └──triggers──> [Multi-Service Deployment]

[Terraform Modules]
    └──enhances──> [Multi-Service Deployment] (DRY, consistency)

[Traffic Splitting]
    └──conflicts with──> [Simple Deployment] (adds rollout complexity)
```

### Dependency Notes

- **Cloud SQL Connection requires IAM Service Accounts:** Cloud Run service identity needs `roles/cloudsql.client` to connect via Unix socket.
- **Secret Manager requires IAM Service Accounts:** Service accounts need `roles/secretmanager.secretAccessor` on specific secrets.
- **VPC Connector optional for Cloud SQL:** Public IP with SSL is simpler for pilot; private IP requires VPC connector and adds complexity.
- **Health Checks enhance Autoscaling:** Startup probes prevent Cloud Run from routing traffic before service is ready; critical for LangGraph services with slow initialization.
- **CI/CD requires Remote State:** GitHub Actions Terraform apply needs access to GCS backend for state locking.
- **Terraform Modules reduce boilerplate:** Single module for Cloud Run services; reused 4 times with different parameters.

## MVP Definition (Pilot Deployment)

### Launch With (v1 - Initial Pilot)

Minimum viable deployment for ~50 protocols, single team.

- [x] **Container Registry Integration** — Use Artifact Registry (already set up); build images in CI/CD
- [x] **Multi-Service Deployment** — Deploy 4 services (api-service, extraction-service, grounding-service, hitl-ui) to Cloud Run
- [x] **Environment Variable Configuration** — Non-sensitive config via Terraform `env` blocks (DATABASE_URL, CORS_ORIGINS, etc.)
- [x] **Secret Management** — Store sensitive values (POSTGRES_PASSWORD, GOOGLE_APPLICATION_CREDENTIALS, UMLS_API_KEY) in Secret Manager
- [x] **Cloud SQL Connection** — PostgreSQL 16 on Cloud SQL; connect via public IP + authorized networks + SSL (simpler than VPC)
- [x] **IAM Service Accounts** — Dedicated service account per service with least privilege (Cloud SQL Client, Secret Manager Accessor)
- [x] **Basic Health Checks** — HTTP startup probes on `/health` endpoint; configure initial_delay_seconds for LangGraph services
- [x] **Remote State (GCS Backend)** — GCS bucket with versioning for Terraform state; automatic state locking
- [x] **Basic Autoscaling** — Cloud Run defaults (scale to zero, autoscale up); set max_instances=10 per service to prevent cost surprises
- [x] **CI/CD Integration** — GitHub Actions workflow: build Docker images → push to Artifact Registry → Terraform apply
- [x] **Terraform Modules** — Reusable module for Cloud Run service; reduces duplication across 4 services

### Add After Validation (v1.x - Post-Pilot)

Features to add once core deployment is working and pilot shows traction.

- [ ] **Traffic Splitting** — Blue-green deployments for gradual rollouts; add when pilot moves to production
- [ ] **Custom Domain with SSL** — Map custom domain to hitl-ui; only needed if external users access UI
- [ ] **VPC Connector** — Private IP for Cloud SQL; add if security review requires private networking
- [ ] **Cost Optimization (Min Instances)** — Set min_instances=1 for API service to reduce cold starts; monitor cost vs latency
- [ ] **Terraform Workspaces** — Separate dev/staging/prod environments; add when pilot expands to multiple environments
- [ ] **Structured Logging** — Configure Cloud Logging filters, alerting; add when pilot needs operational monitoring
- [ ] **Database Migration Automation** — Separate Alembic migration step in CI/CD; ensure migrations run before deployment
- [ ] **GCS Bucket Terraform Provisioning** — Manage protocol storage bucket via Terraform; currently manual setup

### Future Consideration (v2+ - Production Scale)

Features to defer until pilot proves value and scales beyond 50 protocols.

- [ ] **Multi-Region Deployment** — High availability across regions; only needed at larger scale
- [ ] **Complex IAM Policies** — Custom roles with granular permissions; start with predefined roles
- [ ] **Load Balancer for Multi-Service Routing** — External Application Load Balancer; only if complex routing needed
- [ ] **Private Service Connect** — Advanced VPC networking; enterprise security requirement
- [ ] **Monitoring & Alerting** — Cloud Monitoring dashboards, PagerDuty integration; add when on-call needed
- [ ] **Backup & Disaster Recovery** — Automated Cloud SQL backups, point-in-time recovery; configure retention policies
- [ ] **Cost Allocation Tags** — Label resources for cost tracking; useful when multiple teams/projects

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority | Rationale |
|---------|------------|---------------------|----------|-----------|
| Container Registry Integration | HIGH | LOW | P1 | Required for Cloud Run deployment |
| Multi-Service Deployment | HIGH | LOW | P1 | Core requirement for 4 services |
| Environment Variable Configuration | HIGH | LOW | P1 | Essential for runtime config |
| Secret Management | HIGH | MEDIUM | P1 | Security baseline; never commit secrets |
| Cloud SQL Connection | HIGH | MEDIUM | P1 | Database is fundamental |
| IAM Service Accounts | HIGH | MEDIUM | P1 | Security best practice |
| Health Checks | HIGH | LOW | P1 | Prevents broken deployments |
| Remote State (GCS Backend) | HIGH | LOW | P1 | Required for team collaboration |
| Basic Autoscaling | HIGH | LOW | P1 | Cloud Run default; just configure limits |
| CI/CD Integration | HIGH | MEDIUM | P1 | Automation is essential |
| Terraform Modules | MEDIUM | LOW | P1 | DRY principle; reduces errors |
| Traffic Splitting | MEDIUM | MEDIUM | P2 | Useful post-pilot for safe rollouts |
| Custom Domain with SSL | MEDIUM | LOW | P2 | Nice to have for branding |
| VPC Connector | LOW | MEDIUM | P2 | Only if private Cloud SQL required |
| Cost Optimization (Min Instances) | MEDIUM | LOW | P2 | Trade-off: cost vs cold start latency |
| Startup Probes (Custom Timing) | MEDIUM | LOW | P2 | May need for LangGraph services |
| GCS Bucket Terraform Provisioning | LOW | LOW | P2 | Consistency, not urgent |
| Database Migration Automation | MEDIUM | MEDIUM | P2 | Currently works in Dockerfile |
| Structured Logging | MEDIUM | LOW | P2 | Cloud Run has basic logging already |
| Terraform Workspaces | LOW | MEDIUM | P3 | Defer until multi-environment needed |
| Multi-Region Deployment | LOW | HIGH | P3 | Overkill for pilot |
| Complex IAM Policies | LOW | HIGH | P3 | Premature optimization |
| Load Balancer for Routing | LOW | HIGH | P3 | Cloud Run LB sufficient |
| Private Service Connect | LOW | HIGH | P3 | Enterprise-only requirement |
| Monitoring & Alerting | MEDIUM | MEDIUM | P3 | Add when operational maturity needed |
| Backup & Disaster Recovery | MEDIUM | MEDIUM | P3 | Cloud SQL has default backups |
| Cost Allocation Tags | LOW | LOW | P3 | Useful for multi-team, not pilot |

**Priority key:**
- P1: Must have for initial deployment (launch blockers)
- P2: Should have, add when possible (post-launch enhancements)
- P3: Nice to have, future consideration (defer until validated)

## Deployment Pattern Analysis

### Standard Terraform Cloud Run Pattern (Recommended for Pilot)

**What:** Single Terraform configuration managing all 4 Cloud Run services, Cloud SQL instance, Secret Manager secrets, IAM bindings, and Artifact Registry repository.

**Why:** Simplifies dependency management, ensures consistent deployment, easier to reason about service relationships.

**Structure:**
```
infra/terraform/
├── main.tf                 # Provider, backend config
├── variables.tf            # Input variables (project_id, region, image_tags)
├── outputs.tf              # Service URLs, connection strings
├── modules/
│   └── cloud-run-service/  # Reusable module
│       ├── main.tf         # google_cloud_run_v2_service resource
│       ├── variables.tf    # Service-specific inputs
│       └── outputs.tf      # Service URL, service name
├── services.tf             # Calls module 4 times (api, extraction, grounding, ui)
├── database.tf             # Cloud SQL instance
├── secrets.tf              # Secret Manager secrets
├── iam.tf                  # Service account + bindings
└── backend.tf              # GCS backend configuration
```

**Dependencies captured in code:**
- Cloud SQL instance created before Cloud Run services (implicit)
- Secrets created before IAM bindings (implicit)
- Service accounts created before Cloud Run services (explicit `depends_on`)

### .env to Terraform Variable Mapping

**Pattern:** Environment variables in `.env.example` map to Terraform inputs and Secret Manager secrets.

| `.env.example` Variable | Terraform Mapping | Storage |
|------------------------|-------------------|---------|
| `POSTGRES_USER` | `var.db_user` | Cloud SQL instance config |
| `POSTGRES_PASSWORD` | `google_secret_manager_secret` | Secret Manager (never in code) |
| `POSTGRES_DB` | `var.db_name` | Cloud SQL database name |
| `DATABASE_URL` | Constructed in Terraform | Environment variable (public connection string) |
| `GCS_BUCKET_NAME` | `var.gcs_bucket_name` | Environment variable |
| `GOOGLE_APPLICATION_CREDENTIALS` | Service account key JSON | Secret Manager (mounted as volume) |
| `UMLS_API_KEY` | `google_secret_manager_secret` | Secret Manager |
| `CORS_ORIGINS` | `var.cors_origins` | Environment variable |
| `VITE_API_BASE_URL` | Cloud Run service URL (output) | Environment variable for UI |

**Conversion pattern:**
1. **Non-sensitive config** → Terraform variables → Cloud Run `env` blocks
2. **Sensitive secrets** → Secret Manager → Cloud Run `secret` references
3. **Inter-service URLs** → Terraform outputs → Cloud Run `env` blocks

### Secret Management Best Practices

**Avoid:**
- Environment variables for sensitive data (visible to Viewer role)
- Hardcoded secrets in Terraform files
- Service account keys in repositories

**Use:**
- Secret Manager for all sensitive values
- Terraform to create secret placeholders (not populate values)
- `gcloud secrets versions add` to populate secrets outside Terraform
- Pin secret versions in Terraform (avoid `latest` for reproducibility)

**Example Terraform pattern:**
```hcl
# Create secret placeholder
resource "google_secret_manager_secret" "postgres_password" {
  secret_id = "postgres-password"
  replication {
    auto {}
  }
}

# Reference in Cloud Run (version pinned)
resource "google_cloud_run_v2_service" "api" {
  template {
    containers {
      env {
        name = "POSTGRES_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.postgres_password.secret_id
            version = "1"  # Pin version for reproducibility
          }
        }
      }
    }
  }
}
```

### Cloud SQL Connection Patterns

**Two options:**

1. **Public IP + Authorized Networks (Recommended for Pilot)**
   - Simpler configuration
   - No VPC connector needed
   - SSL enforced by default
   - Authorize Cloud Run's egress IP ranges (dynamic, use `0.0.0.0/0` with SSL)
   - Connection string: `postgresql://USER:PASS@PUBLIC_IP:5432/DB?sslmode=require`

2. **Private IP + VPC Connector (Production)**
   - More secure (no public exposure)
   - Requires VPC connector setup (/28 subnet)
   - Higher complexity, additional cost ($10/month for connector)
   - Connection string: `postgresql://USER:PASS@PRIVATE_IP:5432/DB`

**Cloud Run Unix Socket Pattern (Alternative):**
- Cloud Run can connect via Unix socket using Cloud SQL Proxy sidecar
- Connection string: `postgresql://USER:PASS@/cloudsql/PROJECT:REGION:INSTANCE/DB`
- Requires `roles/cloudsql.client` IAM role on service account
- Zero networking configuration

**Recommendation for pilot:** Unix socket pattern (simplest, most secure, no VPC needed).

### Container Build & Deploy Flow

**CI/CD Pipeline:**

1. **Trigger:** Push to `main` branch or manual workflow dispatch
2. **Build:** GitHub Actions builds Docker images using existing Dockerfiles
3. **Tag:** Images tagged with git commit SHA (e.g., `gcr.io/PROJECT/api-service:abc123`)
4. **Push:** Images pushed to Artifact Registry
5. **Terraform:** Update `terraform.tfvars` with new image tags
6. **Apply:** `terraform apply` updates Cloud Run services with new images
7. **Verify:** Health checks confirm services are running

**Terraform variable pattern:**
```hcl
# terraform.tfvars (updated by CI/CD)
image_tags = {
  api        = "sha-abc123"
  extraction = "sha-abc123"
  grounding  = "sha-abc123"
  ui         = "sha-def456"
}

# services.tf
module "api_service" {
  source = "./modules/cloud-run-service"
  image  = "gcr.io/${var.project_id}/api-service:${var.image_tags.api}"
  # ...
}
```

**Alternative (simpler for pilot):** Use `latest` tag during pilot, pin SHAs post-validation.

## Anti-Pattern: Over-Engineering for a Pilot

### Common Mistakes

1. **Multi-environment from day one**
   - Problem: Terraform workspaces, separate state files, complex variable management
   - Pilot impact: Delays deployment by weeks, adds no value for 50 protocols
   - Alternative: Single environment, add staging/prod after validation

2. **Microservice-per-database**
   - Problem: Separate Cloud SQL instance per service
   - Pilot impact: 4x database cost (~$200/month vs ~$50/month), 4x management overhead
   - Alternative: Single PostgreSQL instance with schemas/databases; isolate post-pilot

3. **Perfect IAM from day one**
   - Problem: Custom roles with minimal permissions, complex policy bindings
   - Pilot impact: Hours of IAM debugging, premature optimization
   - Alternative: Predefined roles (Cloud Run Admin, Secret Manager Accessor), refine later

4. **Infrastructure testing**
   - Problem: Terratest, Kitchen-Terraform, complex validation pipelines
   - Pilot impact: Testing infrastructure takes longer than building it
   - Alternative: Manual smoke tests, `terraform validate`, add automated tests at scale

5. **GitOps with complex branching**
   - Problem: Separate branches for dev/staging/prod, PR-based deployments
   - Pilot impact: Process overhead for single-person team
   - Alternative: Direct deploys from `main`, add GitOps when team grows

### Right-Sizing Principles for Pilot

- **Start simple, add complexity when needed** (not when anticipated)
- **Optimize for deployment speed, not theoretical scale** (50 protocols, not 5 million)
- **Defer security hardening until post-validation** (use good defaults, not perfect isolation)
- **Single region, single environment, shared database** (simplicity over resilience)
- **Terraform for reproducibility, not for every resource** (GCS bucket can be manual)

## Expected Terraform Configuration Complexity

### Lines of Code Estimate

| File | Lines | Purpose |
|------|-------|---------|
| `main.tf` | 20 | Provider, backend |
| `variables.tf` | 50 | Input variables with descriptions |
| `outputs.tf` | 30 | Service URLs, connection info |
| `services.tf` | 80 | 4 Cloud Run services using module |
| `database.tf` | 40 | Cloud SQL instance + database |
| `secrets.tf` | 60 | Secret Manager secrets (4-5 secrets) |
| `iam.tf` | 80 | Service accounts + IAM bindings |
| `modules/cloud-run-service/main.tf` | 100 | Reusable service module |
| `modules/cloud-run-service/variables.tf` | 40 | Module inputs |
| `modules/cloud-run-service/outputs.tf` | 10 | Module outputs |
| **Total** | **~510 lines** | Complete deployment infrastructure |

**Complexity level:** MEDIUM (comparable to a Django app with 3-4 models).

### Time Estimate (First Deployment)

- Terraform setup (backend, provider): 1 hour
- Cloud Run module development: 2 hours
- Multi-service configuration: 2 hours
- Cloud SQL + secrets setup: 2 hours
- IAM configuration: 2 hours
- CI/CD integration: 3 hours
- Testing + debugging: 4 hours
- **Total:** ~16 hours (2 days) for experienced Terraform user

**For team with limited Terraform experience:** Add 8 hours for learning curve (total: 3 days).

## Sources

### Official Documentation (HIGH Confidence)

- [Cloud Run documentation](https://cloud.google.com/run/docs) - General Cloud Run concepts
- [Terraform GCP Provider - Cloud Run V2 Service](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_run_v2_service) - Terraform resource reference
- [Cloud SQL Connection from Cloud Run](https://cloud.google.com/sql/docs/postgres/connect-run) - Database connectivity patterns
- [Secret Manager with Cloud Run](https://docs.cloud.google.com/run/docs/configuring/services/secrets) - Secret management best practices
- [Cloud Run Environment Variables](https://docs.cloud.google.com/run/docs/configuring/services/environment-variables) - Configuration patterns
- [Cloud Run Health Checks](https://docs.cloud.google.com/run/docs/configuring/healthchecks) - Startup and liveness probes
- [Terraform GCS Backend](https://developer.hashicorp.com/terraform/language/backend/gcs) - Remote state configuration

### Best Practices & Patterns (MEDIUM Confidence)

- [Best practices for Terraform operations on GCP](https://docs.cloud.google.com/docs/terraform/best-practices/operations) - Google's official Terraform guidance
- [Terraform Best Practices on Google Cloud](https://medium.com/@truonghongcuong68/terraform-best-practices-on-google-cloud-a-practical-guide-057f96b19489) - Practical implementation patterns
- [Securely using dotenv files with Cloud Run and Terraform](https://mikesparr.medium.com/securely-using-dotenv-env-files-with-google-cloud-run-and-terraform-e8b14ff04bff) - .env migration patterns
- [IAM Best Practices for Service Accounts](https://cloud.google.com/iam/docs/best-practices-service-accounts) - Least privilege principles
- [Terraform Modules: Reusability Best Practices](https://scalr.com/learning-center/mastering-terraform-modules-a-practical-guide-to-reusability-and-efficiency/) - DRY patterns

### Cost Optimization (MEDIUM Confidence)

- [Google Cloud Run Pricing and Cost Optimization](https://www.prosperops.com/blog/google-cloud-run-pricing-and-cost-optimization/) - Right-sizing strategies
- [Cloud Run Pricing 2025](https://cloudchipr.com/blog/cloud-run-pricing) - Pricing breakdown
- [Minimize Costs on Cloud Run](https://df-mokhtari.medium.com/how-to-minimize-costs-when-deplyoing-a-full-stack-application-to-google-cloud-run-9-effective-tips-46f06bb433fb) - Practical optimization tips

### CI/CD Integration (MEDIUM Confidence)

- [Streamlining CI/CD for Cloud Run with GitHub Actions and Terraform](https://medium.com/@pawansenapati1999/streamlining-ci-cd-for-cloud-run-with-github-actions-and-terraform-c628092b86e0) - End-to-end pipeline example
- [Google Cloud Run CI/CD: Terraform Cloud & GitHub Actions](https://mkdev.me/posts/google-cloud-run-with-ci-cd-via-terraform-cloud-and-github-actions) - Alternative patterns

### Anti-Patterns & Pitfalls (MEDIUM Confidence)

- [9 Platform Engineering Anti-Patterns](https://jellyfish.co/library/platform-engineering/anti-patterns/) - Over-engineering traps
- [Cloud Native Engineering Anti-Patterns](https://www.coforge.com/what-we-know/blog/cloud-native-engineering-anti-patterns) - Common mistakes
- [10 Cloud Antipatterns](https://en.paradigmadigital.com/dev/10-cloud-antipatterns/) - What to avoid

---

*Feature research for: Terraform GCP Cloud Run Deployment Infrastructure*
*Researched: 2026-02-12*
*Context: Adding deployment to existing 4-service containerized application (Clinical Trial Criteria Extraction System)*
