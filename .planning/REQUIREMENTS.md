# Requirements: GCP Cloud Run Deployment

**Defined:** 2026-02-12
**Core Value:** Operators can deploy the entire Clinical Trial Criteria Extraction System to GCP Cloud Run using Terraform, with all configuration documented in .env.example and terraform.tfvars.example

## v1.2 Requirements

Requirements for GCP Cloud Run deployment milestone. Each maps to roadmap phases.

### Terraform Infrastructure

- [ ] **TF-01**: Operator can run `terraform init && terraform apply` from `infra/terraform/` to provision all GCP resources
- [ ] **TF-02**: Terraform state is stored in a GCS backend with automatic locking
- [ ] **TF-03**: Terraform uses reusable modules for Cloud Run services (DRY pattern for 4 services)

### Cloud Run Deployment

- [ ] **CR-01**: All 4 services (api-service, extraction-service, grounding-service, hitl-ui) deploy to Cloud Run Gen 2 using existing Dockerfiles
- [ ] **CR-02**: Cloud Run services have health check startup probes configured on `/health` endpoints
- [ ] **CR-03**: Cloud Run autoscaling is configured with max_instances limit to prevent cost surprises and connection exhaustion

### Database & Networking

- [ ] **DB-01**: Cloud SQL PostgreSQL 16 instance is provisioned with private IP only (no public exposure)
- [ ] **DB-02**: VPC Serverless Connector enables Cloud Run to Cloud SQL private communication

### Security & Secrets

- [ ] **SEC-01**: Secret Manager stores all sensitive values (DATABASE_URL, UMLS_API_KEY, OAuth credentials) — never in Terraform state or .env files
- [ ] **SEC-02**: Dedicated IAM service accounts per Cloud Run service with least-privilege roles

### Container Registry

- [ ] **REG-01**: Artifact Registry repository is provisioned for container image storage
- [ ] **REG-02**: A build-and-push script builds all 4 Docker images and pushes to Artifact Registry

### Configuration & Documentation

- [ ] **CFG-01**: `.env.example` documents every variable needed for deployment with descriptions
- [ ] **CFG-02**: `terraform.tfvars.example` provides a template for all Terraform input variables
- [ ] **CFG-03**: `infra/terraform/README.md` documents deployment prerequisites, steps, and troubleshooting

## v1.1 Requirements (Paused)

Phases 11-12 (Component Deep Dives, Implementation Status & Code Tour) remain unplanned. See .planning/MILESTONES.md for details.

## v1.0 Requirements (Archived)

All 22 v1.0 requirements shipped. See .planning/MILESTONES.md for details.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-region deployment | Over-engineered for 50-protocol pilot |
| Custom domain with SSL | Not needed for internal pilot |
| Traffic splitting / blue-green | Add post-pilot when rollout safety matters |
| Terraform workspaces (multi-env) | Single environment sufficient for pilot |
| Cloud Build CI/CD pipeline | Manual deploys via terraform apply sufficient for pilot |
| VPC Service Controls | Enterprise security feature, defer to production |
| Cloud CDN for static assets | Cloud Run serves hitl-ui directly for pilot |
| MLflow Cloud Run deployment | Keep as local dev tool for now |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| TF-01 | Phase 13 | Pending |
| TF-02 | Phase 13 | Pending |
| TF-03 | Phase 15 | Pending |
| CR-01 | Phase 15 | Pending |
| CR-02 | Phase 15 | Pending |
| CR-03 | Phase 15 | Pending |
| DB-01 | Phase 14 | Pending |
| DB-02 | Phase 14 | Pending |
| SEC-01 | Phase 14 | Pending |
| SEC-02 | Phase 13 | Pending |
| REG-01 | Phase 13 | Pending |
| REG-02 | Phase 14 | Pending |
| CFG-01 | Phase 15 | Pending |
| CFG-02 | Phase 15 | Pending |
| CFG-03 | Phase 15 | Pending |

**Coverage:**
- v1.2 requirements: 15 total
- Mapped to phases: 15
- Unmapped: 0

---
*Requirements defined: 2026-02-12*
*Last updated: 2026-02-12 after roadmap creation*
