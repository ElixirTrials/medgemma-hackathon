# Project Research Summary

**Project:** Clinical Trial Criteria Extraction System - v1.2 GCP Cloud Run Deployment
**Domain:** Infrastructure deployment (Terraform-based containerized microservices deployment to GCP Cloud Run)
**Researched:** 2026-02-12
**Confidence:** HIGH

## Executive Summary

This milestone adds production deployment infrastructure to an existing 4-service containerized application (api-service, extraction-service, grounding-service, hitl-ui) that currently runs via Docker Compose. The recommended approach is Terraform-managed GCP Cloud Run with Cloud SQL PostgreSQL, VPC-based private networking, and Secret Manager for credentials. All existing Dockerfiles work without modification—the deployment layer wraps existing containers with production infrastructure.

The key architectural decision is using VPC Serverless Connectors to enable Cloud Run (serverless) to communicate with Cloud SQL via private IP, eliminating public database exposure while maintaining security compliance. Infrastructure is organized as reusable Terraform modules (foundation, networking, database, secrets, cloud-run-service) with a single root orchestrator, keeping state management simple for the 50-protocol pilot scale. Container images are built separately from Terraform (via CI/CD scripts), then referenced by digest in Terraform to enable proper change detection.

The primary risk is connection pool exhaustion: Cloud Run's auto-scaling can spawn 100+ instances during traffic spikes, each opening database connections, overwhelming Cloud SQL's connection limits. Prevention requires strict connection pool sizing (2-3 connections per instance) and Cloud Run max_instances limits calculated from database capacity. Secondary risks include VPC connector region mismatches (causes silent connection failures), Secret Manager IAM propagation delays (causes intermittent deployment failures), and cold start latency (15-30 second delays frustrate users). All are preventable with explicit Terraform dependencies, startup CPU boost configuration, and minimum instance settings.

## Key Findings

### Recommended Stack

**Infrastructure Layer (Terraform 1.6+, Google Provider 7.19.0):** Use Terraform modules to manage GCP resources with GCS-backed state for team collaboration. Google Provider 7.19.0 adds critical write-only attributes for secrets (prevents DATABASE_URL from appearing in state files) and enhanced Cloud Run v2 support. All infrastructure is declarative IaC, with manual pre-requisites limited to GCS state bucket creation and API enablement.

**Core technologies:**
- **Terraform 1.6+ with hashicorp/google ~> 7.0** — Infrastructure as Code with native monorepo support; version 7.0+ required for Secret Manager security improvements and Cloud Run v2 features
- **Cloud Run Gen 2** — Serverless container hosting with autoscaling (0→N instances); Gen 2 required for VPC direct egress, startup probes, and private Cloud SQL integration
- **Cloud SQL PostgreSQL 16 (private IP)** — Managed database replacing Docker Compose postgres; private IP via VPC peering prevents public exposure, matches local dev version
- **VPC Serverless Connector** — Bridge between Cloud Run and VPC for private Cloud SQL access; required for secure internal networking without public database IPs
- **Artifact Registry** — Container image storage for Cloud Run deployment; GCP-native with IAM integration, vulnerability scanning, and fast image pulls
- **Secret Manager** — Secure secret storage replacing .env files; provides versioning, audit logs, IAM-controlled access, and rotation without code changes

### Expected Features

**Must have (table stakes):**
- Container Registry Integration (Artifact Registry) — Cloud Run requires hosted images; existing Dockerfiles build and push to registry
- Multi-Service Deployment — Deploy 4 services (api, extraction, grounding, ui) with consistent configuration via reusable Terraform modules
- Secret Management (Secret Manager) — Production security baseline; store DATABASE_URL, UMLS_API_KEY, OAuth credentials with IAM access control
- Cloud SQL Connection — Database connectivity via private IP through VPC connector; Cloud Run service accounts need cloudsql.client IAM role
- Health Checks — HTTP startup probes on /health endpoints prevent premature traffic routing; critical for LangGraph services with slow initialization
- IAM Service Accounts — Dedicated service account per service with least privilege (Cloud SQL Client, Secret Manager Accessor); never use default compute SA
- Remote State (GCS Backend) — Team collaboration and state locking; GCS bucket with versioning for Terraform state recovery
- Basic Autoscaling — Cloud Run defaults (scale to zero, autoscale up) with max_instances=10 limit to prevent cost surprises and connection exhaustion

**Should have (competitive):**
- Terraform Modules for Reusability — DRY principle via single cloud-run-service module reused 4 times with different parameters
- VPC Connector (Private Networking) — Secure internal communication for Cloud SQL private IP; required for SOC2/HIPAA compliance
- Startup Probes (Custom Timing) — LangGraph services may need longer initial_delay_seconds (30s) due to model initialization overhead
- Cost Optimization (Min Instances) — Set min_instances=1 for api-service and hitl-ui (~$15/month/service) to reduce cold start latency below 5 seconds

**Defer (v2+):**
- Traffic Splitting / Blue-Green — Gradual rollouts useful after pilot validation; Cloud Run native support but adds rollout complexity
- Custom Domain with SSL — Professional URLs only needed if external users access pilot UI; auto-managed SSL certs simplify setup
- Terraform Workspaces — Separate dev/staging/prod environments; add when pilot expands beyond single environment
- Multi-Region Deployment — High availability across regions; doubles complexity and costs, defer until pilot proves value beyond 50 protocols

### Architecture Approach

**Infrastructure organized as modular Terraform with clear dependency graph:** Foundation module (APIs, Artifact Registry) → Networking + IAM modules (VPC, service accounts) → Secrets + Database modules (Secret Manager, Cloud SQL with private IP) → Storage module (GCS bucket) → Cloud Run Services module (4 services with VPC connector, secrets, IAM). Root main.tf orchestrates modules with explicit dependency management for Cloud SQL VPC peering and Secret Manager IAM bindings.

**Major components:**
1. **Foundation Module** — Enables GCP APIs (Cloud Run, Cloud SQL, Secret Manager, VPC Access) and creates Artifact Registry repository for container images
2. **Networking Module** — Creates VPC network, VPC Serverless Connector (10.8.0.0/28 subnet), and firewall rules for Cloud Run to Cloud SQL private communication
3. **Secrets Module** — Creates Secret Manager secrets and versions for DATABASE_URL, UMLS_API_KEY, OAuth credentials; grants service accounts secretAccessor role
4. **Database Module** — Creates Cloud SQL PostgreSQL 16 with private IP only (no public IP), VPC peering, automated backups, and connection pooling configuration
5. **Cloud Run Services Module** — Reusable module invoked 4 times deploying api-service, extraction-service, grounding-service, hitl-ui with VPC connector, secrets, IAM bindings
6. **IAM Module** — Creates dedicated service accounts per service with least privilege roles (cloudsql.client, secretmanager.secretAccessor, storage.objectViewer)

### Critical Pitfalls

1. **VPC Connector Region Mismatch** — Cloud Run, VPC connector, and Cloud SQL must all be in same region; Terraform doesn't validate at plan time, causing silent connection failures. Use Terraform locals to define region once and reference everywhere. Add explicit validation: `lifecycle { postcondition { condition = self.region == var.cloud_sql_region } }`.

2. **Secret Manager IAM Propagation Race** — IAM bindings take 60-120 seconds to propagate globally; Cloud Run deployment may fail with "Permission denied on secret" even though Terraform created the binding. Use explicit `depends_on = [google_secret_manager_secret_iam_member.secret_access]` and consider `time_sleep` resource for initial deployment.

3. **Connection Pool Exhaustion** — Cloud Run scales to 100+ instances during traffic spikes; each opens 5-10 database connections, overwhelming Cloud SQL's 100-connection limit. Configure pool_size=2, max_overflow=1 per instance, and set max_instances = ceil(cloud_sql_max_connections / (pool_size + max_overflow)). For 100 DB connections and pool=3: max_instances=33.

4. **Image Tag vs Digest** — Using image tags (:latest, :v1.0) prevents Terraform from detecting container updates; Cloud Run resolves tags to digests on deployment, so Terraform sees no change. Use CI/CD to capture image digest after push (`docker push && docker inspect --format='{{index .RepoDigests 0}}'`) and pass to Terraform: `image = var.image_digest` (format: `us-docker.pkg.dev/project/repo/api@sha256:abc123`).

5. **Secrets in Terraform State** — Storing secrets as Terraform variables puts plaintext credentials in terraform.tfstate file, exposing them in git history and CI logs. Always use Secret Manager with Cloud Run secret references: `value_source { secret_key_ref { secret = google_secret_manager_secret.api_key.id } }`, never `value = var.api_key`.

## Implications for Roadmap

Based on research, suggested phase structure for v1.2 (phases 13-19):

### Phase 13: Infrastructure Foundation (Week 1)
**Rationale:** Establish GCP project foundation, API enablement, and Artifact Registry before any resource dependencies. This phase has zero dependencies and enables all subsequent work. Region/network variable patterns must be established here to prevent VPC connector region mismatches (Pitfall 1).

**Delivers:** GCS state bucket (manual), Terraform backend config, provider setup, Foundation module (API enablement, Artifact Registry repository), IAM module (4 service accounts with predefined roles).

**Avoids:** VPC connector region mismatch (use Terraform locals for region), secrets in state (establish Secret Manager pattern), state lock conflicts (single state sufficient for pilot).

**Research flag:** Skip research-phase—well-documented GCP/Terraform patterns with official provider docs.

---

### Phase 14: Networking and Database (Week 1-2)
**Rationale:** VPC and Cloud SQL must exist before Cloud Run services can deploy. Cloud SQL private IP requires VPC peering with explicit depends_on (Pitfall 6). Networking and database are tightly coupled due to VPC peering dependency; grouping prevents mid-phase integration issues.

**Delivers:** Networking module (VPC, /28 VPC connector subnet, VPC Serverless Connector), Database module (Cloud SQL PostgreSQL 16 with private IP, VPC peering, automated backups), connection pool configuration documented in module README.

**Implements:** VPC-based private networking architecture with Cloud SQL connection via VPC connector (standard pattern from ARCHITECTURE.md).

**Avoids:** Missing private IP configuration (Pitfall 6), connection pool exhaustion prevention starts here with max_connections documentation.

**Research flag:** Skip research-phase—standard Cloud SQL + VPC connector pattern with official Google Cloud docs.

---

### Phase 15: Secret Management (Week 2)
**Rationale:** Secrets must exist and have IAM bindings before Cloud Run deployment (Pitfall 2). Separate phase allows validation of Secret Manager setup and IAM propagation timing without Cloud Run deployment complexity. Establishes pattern for manual secret value creation outside Terraform (via gcloud or console).

**Delivers:** Secrets module (google_secret_manager_secret resources for DATABASE_URL, UMLS_API_KEY, OAuth credentials), IAM bindings (service accounts get secretmanager.secretAccessor role), terraform.tfvars.example template documenting secret structure.

**Addresses:** Secret management table stakes feature; replaces .env files with production-grade secret storage.

**Avoids:** Secrets in Terraform state (Pitfall 5—secrets created as placeholders, values added via gcloud), IAM propagation race (explicit depends_on patterns established).

**Research flag:** Skip research-phase—Secret Manager integration well-documented in Cloud Run docs.

---

### Phase 16: Container Build Pipeline (Week 2)
**Rationale:** Images must exist in Artifact Registry before Cloud Run deployment. Separate from Terraform to avoid building images during terraform apply (Anti-Pattern 5 from PITFALLS.md). Establishes digest-based deployment pattern to prevent image tag change detection issues (Pitfall 3).

**Delivers:** scripts/build-and-push.sh (builds 4 images, pushes to Artifact Registry, captures digests), CI/CD workflow (GitHub Actions or Cloud Build config for automated builds on push), terraform.tfvars pattern for image digest variables.

**Uses:** Artifact Registry from Phase 13 foundation; existing Dockerfiles from services/* and apps/hitl-ui/* without modification.

**Avoids:** Image tag vs digest issue (Pitfall 3—CI captures SHA256 digests and passes to Terraform), Artifact Registry auth failure (Pitfall 9—workload identity federation setup).

**Research flag:** Needs research-phase—CI/CD integration with Artifact Registry and digest capture requires pipeline-specific patterns (GitHub Actions vs Cloud Build differ significantly).

---

### Phase 17: Cloud Run Services Deployment (Week 3)
**Rationale:** All dependencies now exist (VPC connector, Cloud SQL, secrets, service accounts, container images). This phase is the integration point for all previous work. Connection pool sizing and max_instances configuration happens here to prevent connection exhaustion (Pitfall 4).

**Delivers:** Cloud Run Services module (reusable module with env vars, secrets, VPC connector, IAM), root main.tf invoking module 4 times (api-service, extraction-service, grounding-service, hitl-ui), connection pool configuration in database connection strings, max_instances limits based on Cloud SQL capacity.

**Implements:** Multi-service deployment with VPC private networking, secret mounting, least-privilege IAM, startup probes for LangGraph services.

**Avoids:** Connection pool exhaustion (Pitfall 4—pool_size=2, max_instances=33 for 100 DB connections), Secret Manager IAM propagation race (explicit depends_on from Phase 15), cold start latency (startup_cpu_boost=true, consider min_instances=1 for user-facing).

**Research flag:** Skip research-phase—Cloud Run service configuration well-documented, patterns established in ARCHITECTURE.md.

---

### Phase 18: End-to-End Integration Testing (Week 3)
**Rationale:** Validate full deployment before considering complete. Integration testing catches VPC connector connectivity issues, secret access problems, database connection failures, and ingress/egress misconfigurations that unit tests miss.

**Delivers:** Integration test suite (upload protocol → extraction workflow → grounding workflow → HITL review), load testing for connection pool limits (verify max_instances honored, no DB connection errors at 100 concurrent requests), cold start latency benchmarks, deployment verification checklist.

**Addresses:** Health checks table stakes feature; validates startup probes work for slow-starting LangGraph services.

**Avoids:** Cold start latency exceeding timeouts (Pitfall 8—measure and optimize before production), ingress/egress misconfigurations (Pitfall 10—verify service-to-service calls and external API access).

**Research flag:** Skip research-phase—testing patterns standard, tools documented in official Cloud Run docs.

---

### Phase 19: Documentation and Handoff (Week 4)
**Rationale:** Deployment infrastructure needs operational documentation for team handoff. Terraform configurations are self-documenting but operational procedures (secret rotation, scaling adjustments, cost monitoring) require explicit documentation.

**Delivers:** infra/terraform/README.md (deployment instructions, troubleshooting guide), terraform.tfvars.example (template for production values with comments), runbook for common operations (secret rotation, database scaling, Cloud Run revision rollback), cost monitoring dashboard setup.

**Uses:** All components from previous phases; documents patterns established throughout milestone.

**Research flag:** Skip research-phase—documentation is synthesis of established patterns, no new technical research needed.

---

### Phase Ordering Rationale

- **Foundation first (13) enables all other work:** APIs, Artifact Registry, service accounts have no dependencies and are prerequisites for everything else
- **Networking + Database together (14) due to tight coupling:** Cloud SQL private IP requires VPC peering; splitting into separate phases adds coordination overhead for no benefit
- **Secrets before Cloud Run (15 before 17) prevents IAM race conditions:** Allows explicit depends_on and time for IAM propagation before services attempt secret access
- **Container build before Cloud Run (16 before 17) avoids Terraform complexity:** Separates concerns (Docker build vs infrastructure deployment), establishes digest-based change detection pattern
- **Cloud Run deployment (17) is integration milestone:** All dependencies exist; this phase validates architecture decisions from research
- **Testing before documentation (18 before 19) validates completeness:** Can't document what doesn't work; integration testing catches issues before handoff

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 16 (Container Build Pipeline):** CI/CD integration patterns differ between GitHub Actions and Cloud Build; digest capture and Workload Identity Federation setup requires pipeline-specific research

Phases with standard patterns (skip research-phase):
- **Phase 13 (Foundation):** GCP project setup and Terraform basics well-documented in official HashiCorp and Google Cloud docs
- **Phase 14 (Networking + Database):** Cloud SQL private IP and VPC connector patterns standard, covered thoroughly in Google Cloud SQL docs
- **Phase 15 (Secret Management):** Secret Manager integration with Cloud Run documented in official Google Cloud Run guides
- **Phase 17 (Cloud Run Services):** Cloud Run v2 service configuration well-documented, reusable module pattern established in research
- **Phase 18 (Integration Testing):** Standard testing approaches, tools documented in Cloud Run and load testing guides
- **Phase 19 (Documentation):** Synthesis of established patterns, no new technical domain

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Terraform provider version 7.19.0 verified from GitHub releases (Feb 2025); all GCP services documented in official Google Cloud docs updated Feb 2026 |
| Features | HIGH | Feature requirements derived from official Cloud Run, Cloud SQL, Secret Manager documentation; table stakes vs differentiators validated against real-world Cloud Run migration articles |
| Architecture | HIGH | VPC connector + Cloud SQL private IP pattern standard for production deployments; Terraform module structure validated from HashiCorp and Google best practices docs (2026) |
| Pitfalls | HIGH | All 10 critical pitfalls sourced from official Google Cloud troubleshooting docs, GitHub issues, and recent (2024-2026) Medium articles on production Cloud Run deployments |

**Overall confidence:** HIGH

### Gaps to Address

- **Connection pool sizing for specific workload:** Research provides general guidance (pool_size=2-3), but exact values depend on per-service query patterns. During Phase 17, monitor actual connection usage with Cloud SQL metrics and tune pool_size based on real traffic.

- **CI/CD pipeline choice (GitHub Actions vs Cloud Build):** Research covered both but didn't make specific recommendation. During Phase 16, choose based on existing team tooling: GitHub Actions if already using GitHub, Cloud Build if wanting tighter GCP integration. Both patterns validated in research.

- **Cold start latency targets for pilot:** Research identifies cold start as issue (15-30s) and mitigations (startup CPU boost, min_instances), but acceptable latency depends on user requirements. During Phase 18, establish baseline latency SLO (e.g., p95 < 5s) and tune configuration to meet target.

- **Exact Cloud SQL instance tier:** Research recommends db-f1-micro for pilot (1 vCPU, 3.75GB RAM, ~$50/month) but actual tier depends on concurrent user load. During Phase 14, start with db-f1-micro and document scaling path to db-n1-standard-1 if CPU >70% sustained.

## Sources

### Primary (HIGH confidence)
- [Terraform Provider Google Releases (GitHub)](https://github.com/hashicorp/terraform-provider-google/releases) — Version 7.19.0 verified Feb 2025
- [Google Cloud Run Documentation](https://cloud.google.com/run/docs) — All Cloud Run patterns current as of Feb 2026
- [Cloud SQL Connection from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run) — Private IP and VPC connector patterns
- [Terraform GCP Provider - Cloud Run V2 Service](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_run_v2_service) — Resource reference
- [Cloud Run VPC Connectors Documentation](https://docs.cloud.google.com/run/docs/configuring/vpc-connectors) — VPC egress configuration
- [Secret Manager with Cloud Run](https://docs.cloud.google.com/run/docs/configuring/services/secrets) — Secret mounting patterns
- [Terraform Best Practices on Google Cloud (Official)](https://docs.cloud.google.com/docs/terraform/best-practices/operations) — Google's Terraform guidance

### Secondary (MEDIUM confidence)
- [Best Practices for Terraform on GCP (Medium, Jan 2024)](https://medium.com/@truonghongcuong68/terraform-best-practices-on-google-cloud-a-practical-guide-057f96b19489) — Module organization patterns
- [Securely Using .env Files with Cloud Run and Terraform (Medium, 2023)](https://mikesparr.medium.com/securely-using-dotenv-env-files-with-google-cloud-run-and-terraform-e8b14ff04bff) — Secret migration patterns
- [Cloud SQL with Private IP Only (Medium, 2024)](https://medium.com/google-cloud/cloud-sql-with-private-ip-only-the-good-the-bad-and-the-ugly-de4ac23ce98a) — VPC peering gotchas
- [Terraform Monorepo Best Practices (Spacelift, 2026)](https://spacelift.io/blog/terraform-monorepo) — State management patterns
- [3 Ways to Optimize Cloud Run Response Times (Google Cloud Blog, 2025)](https://cloud.google.com/blog/topics/developers-practitioners/3-ways-optimize-cloud-run-response-times) — Cold start optimization

### Tertiary (LOW confidence)
- [Mitigate Cloud Run Cold Startup Strategies (Medium, 2024)](https://omermahgoub.medium.com/mitigate-cloud-run-cold-startup-strategies-to-improve-response-time-cad5a6aea327) — Startup CPU boost practical results (needs validation with actual workload)
- [Docker Layer Caching in Cloud Build (Depot.dev, 2024)](https://depot.dev/blog/docker-layer-caching-in-google-cloud-build) — Build optimization techniques (effectiveness varies by codebase)

---
*Research completed: 2026-02-12*
*Ready for roadmap: yes*
