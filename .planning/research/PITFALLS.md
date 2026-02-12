# Terraform GCP Cloud Run Deployment Pitfalls

**Domain:** Terraform-based GCP Cloud Run deployment for existing Docker Compose application
**Researched:** 2026-02-12
**Confidence:** HIGH

This research focuses on common mistakes when **adding** Terraform Cloud Run deployment to an existing Docker Compose-based application with 4 containerized services (api-service, extraction-service, grounding-service, hitl-ui) migrating from local PostgreSQL to Cloud SQL.

---

## Critical Pitfalls

### Pitfall 1: VPC Connector Region and Network Mismatch

**What goes wrong:**
Cloud Run services fail to connect to Cloud SQL with cryptic "connection refused" or timeout errors despite correct private IP configuration. The VPC connector exists but Cloud Run can't use it because it's in a different region or connected to a different VPC network than the Cloud SQL instance.

**Why it happens:**
Developers create VPC connectors in default regions (us-central1) while deploying Cloud Run services or Cloud SQL instances to other regions for cost/latency reasons. Terraform doesn't validate cross-resource region compatibility at plan time. The VPC connector won't appear in Cloud Run service region dropdown during deployment, but Terraform allows invalid references.

**How to avoid:**
- Use Terraform locals to define region once: `locals { region = "us-central1" }` and reference everywhere
- Add explicit validation in Terraform: `lifecycle { postcondition { condition = self.region == var.cloud_sql_region; error_message = "VPC connector must be in same region as Cloud SQL" } }`
- Ensure VPC connector, Cloud Run services, and Cloud SQL instance all use same `region` and `network` variables
- For multi-region deployments, create one VPC connector per region
- Document in variables.tf: "VPC connector must share same project and region as Cloud Run service"

**Warning signs:**
- Terraform apply succeeds but Cloud Run instances can't reach Cloud SQL
- `gcloud run services describe` shows no VPC connector attached despite Terraform configuration
- Cloud SQL connection errors only appear in Cloud Run logs, not during deployment
- Private IP connections work from Cloud Shell (same VPC) but fail from Cloud Run
- VPC connector shows "in use" but Cloud Run service shows "no egress configured"

**Phase to address:**
Phase 0 (Infrastructure Foundation) - Establish region/network variable pattern before any resource creation. Cannot retrofit easily after services deployed.

---

### Pitfall 2: Secret Manager Permissions Not Set Before Service Deployment

**What goes wrong:**
Cloud Run deployment fails with "Permission denied on secret" errors even though the secret exists and Terraform shows it created the IAM binding. The service account lacks Secret Manager Secret Accessor role at the moment Cloud Run attempts to mount secrets during initial deployment.

**Why it happens:**
Terraform's DAG doesn't guarantee IAM propagation timing. Creating `google_secret_manager_secret_iam_member` and `google_cloud_run_v2_service` in same apply causes race condition—IAM binding exists in Google's backend but isn't propagated to all Cloud Run service zones before deployment starts. IAM changes can take 60-120 seconds to fully propagate globally.

**How to avoid:**
- Use explicit `depends_on = [google_secret_manager_secret_iam_member.secret_access]` in Cloud Run service resource
- For critical secrets (database passwords, API keys), create IAM bindings in separate Terraform apply before service deployment
- Add retry logic to Cloud Run deployment: `lifecycle { create_before_destroy = false }` with manual retry on permission errors
- Grant Secret Manager Secret Accessor role to service account at project level for initial deployment, then narrow to specific secrets after validation
- Pin secrets to specific versions (not `latest`) in initial deployment to avoid fetch-on-startup timing issues

**Warning signs:**
- Intermittent deployment failures: sometimes succeeds, sometimes fails with permission errors
- `terraform apply` fails on first run but succeeds on second run without changes
- Deployment succeeds but container startup fails with "failed to fetch secret"
- Service account shows correct IAM bindings in console but Cloud Run deployment still fails
- Error logs show "The caller does not have permission" during service creation (not runtime)

**Phase to address:**
Phase 1 (Cloud Run Service Deployment) - Establish IAM-first pattern in initial service deployment. Add `time_sleep` resource if necessary: `resource "time_sleep" "wait_for_iam" { depends_on = [google_secret_manager_secret_iam_member.secret_access]; create_duration = "60s" }`

---

### Pitfall 3: Image Tag Instead of SHA256 Digest Breaking Terraform Change Detection

**What goes wrong:**
Updated Docker images pushed to Artifact Registry with same tag (e.g., `latest`, `v1.0`) don't trigger Cloud Run redeployment. Terraform shows "no changes" even though container image changed. Teams manually force redeployment or destroy/recreate services, losing traffic splitting, revision history, and zero-downtime deployment capabilities.

**Why it happens:**
Cloud Run resolves image tags to SHA256 digests on deployment and stores the digest in revision metadata. Terraform compares the tag string `us-docker.pkg.dev/project/repo/api:latest` in state vs. config—both identical—so no change detected. Docker images are mutable at tag level but immutable at digest level. Terraform can't query Artifact Registry for current digest without Docker daemon access (impossible in Terraform Cloud).

**How to avoid:**
- **Build-time digest capture**: Use `docker build --iidfile=digest.txt` and pass digest to Terraform via TF_VAR
- **CI/CD pattern**: In CI, after pushing image, extract digest with `gcloud artifacts docker images describe` and write to `terraform.tfvars`: `image_digest = "us-docker.pkg.dev/project/repo/api@sha256:abc123..."`
- **Terraform approach**: Use `image = var.image_digest` instead of `image = "${var.image_repo}:${var.image_tag}"`
- **Alternative tag strategy**: Use commit SHA as tag (`git-${GITHUB_SHA}`) for semantic versioning without digest complexity
- **Force replacement**: Add `replace_triggered_by = [terraform_data.image_version]` with version tracking

**Warning signs:**
- CI builds and pushes new image but `terraform plan` shows no changes
- Service serves old code despite "successful deployment" in CI logs
- Team uses `terraform taint` or `gcloud run deploy` to force updates
- Revision count doesn't increment after image rebuild
- `gcloud run revisions describe` shows old image digest despite new tag push

**Phase to address:**
Phase 1 (Cloud Run Service Deployment) - Establish digest-based deployment pattern before first production deployment. Retrofitting requires revision history loss.

---

### Pitfall 4: Cloud SQL Connection Pool Exhaustion from Serverless Scaling

**What goes wrong:**
Cloud Run scales to 100+ instances during traffic spike, each opens 5-10 PostgreSQL connections, exhausting Cloud SQL's 100-connection default limit. Database refuses new connections, API returns 500 errors, services crash. Cloud SQL CPU is low but connection count maxed. Increasing Cloud SQL machine type doesn't help because connection limit is reached, not CPU.

**Why it happens:**
Docker Compose uses single long-lived database connection per service. Cloud Run creates new container instances on every request during cold starts or autoscaling. Each instance initializes connection pool (default 10 connections in SQLAlchemy, 5 in asyncpg). With 80 concurrency, Cloud Run creates ~20 instances under moderate load. 20 instances × 10 connections = 200 connections needed, but Cloud SQL Micro instance supports max 25 concurrent connections.

**How to avoid:**
- **Right-size connection pools**: `pool_size=2, max_overflow=1` per Cloud Run instance (3 connections max per instance)
- **Set max_instances in Cloud Run**: Limit to `ceil(cloud_sql_max_connections / (pool_size + max_overflow))`. For Cloud SQL with 100 connections and 3 per instance: `max_instances = 30`
- **Use Cloud SQL Connection Pooling**: Enable Managed Connection Pooling (uses TCP port 6432, supports 10,000+ connections via PgBouncer)
- **Set concurrency properly**: If pool_size=3, set Cloud Run concurrency to 10-20 to reuse connections across requests in same instance
- **Connection lifecycle**: Use `pool_pre_ping=True` to validate connections before use, set `pool_recycle=3600` to prevent stale connections
- **Monitor connection count**: Alert when `cloudsql.googleapis.com/database/postgresql/num_backends > 80% of max_connections`

**Warning signs:**
- Cloud Run errors spike during traffic increases, recover slowly after traffic drops
- Cloud SQL logs show "too many connections for role" or "FATAL: remaining connection slots are reserved"
- Cloud SQL CPU <20% but connection errors occur
- Increasing Cloud Run max_instances makes problem worse (more instances = more connections)
- Connection errors appear randomly across all services simultaneously
- Database connection errors appear during cold starts, not during steady-state operation

**Phase to address:**
Phase 1 (Cloud Run Service Deployment) - Configure connection pooling in initial deployment. Cannot fix retroactively without service disruption and connection tuning.

---

### Pitfall 5: .env File Secrets Committed to Terraform State

**What goes wrong:**
API keys (Gemini, Vertex AI), OAuth credentials, and database passwords from .env files get converted to Terraform environment variables and stored in plaintext in `terraform.tfstate` file. State file committed to git, pushed to remote backend, or shared with team exposes production secrets. Secrets appear in `terraform plan` output logs in CI/CD. Secret rotation requires Terraform state file surgery.

**Why it happens:**
Teams migrate Docker Compose .env pattern directly to Terraform: `environment { name = "GEMINI_API_KEY"; value = var.gemini_api_key }` where `var.gemini_api_key` comes from `terraform.tfvars` (previously .env). Terraform stores all resource attributes in state, including environment variable values. Unlike Secret Manager references (stored as resource IDs), hardcoded values are plaintext in state.

**How to avoid:**
- **Never use Terraform variables for secrets**: Use Secret Manager for all sensitive values (API keys, passwords, OAuth credentials)
- **Cloud Run secret reference pattern**: `env { name = "GEMINI_API_KEY"; value_source { secret_key_ref { secret = google_secret_manager_secret.gemini_api_key.id; version = "latest" } } }`
- **Separate secret creation from Terraform**: Create secrets via `gcloud secrets create` or console, reference by ID in Terraform (avoids secret values in Terraform entirely)
- **Use mounted secrets for files**: OAuth credentials JSON → Secret Manager → mount as volume at `/secrets/oauth.json`
- **.env migration pattern**: Create Secret Manager secrets from .env once, delete .env, never commit secret values to any IaC
- **For non-sensitive config**: Use environment variables (API_BASE_URL, ENVIRONMENT=production, PORT=8000)

**Warning signs:**
- `terraform plan` output shows API keys or passwords in plaintext
- `grep -r "sk-" terraform.tfstate` finds API keys in state file
- Secret rotation requires `terraform apply` (should be external to Terraform)
- Git history contains `terraform.tfvars` with secret values
- CI logs show environment variables with credential values
- Team shares terraform.tfstate file via Slack or email

**Phase to address:**
Phase 0 (Infrastructure Foundation) - Establish Secret Manager pattern before any service deployment. Retrofitting requires secret rotation and state file cleanup.

---

### Pitfall 6: Missing Cloud SQL Private IP and Incorrect Host Configuration

**What goes wrong:**
Cloud Run connects to Cloud SQL via public IP despite VPC connector configuration, incurring egress charges and exposing database traffic to internet. Or connections fail entirely because DATABASE_URL uses `127.0.0.1` (Cloud SQL Auth Proxy pattern) but no proxy is configured in Cloud Run container.

**Why it happens:**
Docker Compose uses `db` hostname (Docker DNS) or `localhost` with Cloud SQL Proxy sidecar. Cloud Run has no sidecar support and no DNS for Cloud SQL. Teams copy DATABASE_URL from docker-compose.yml without adapting to Cloud Run's private IP or Cloud SQL connector patterns. Cloud SQL instances created without private IP configuration (default is public IP only).

**How to avoid:**
- **Enable private IP on Cloud SQL**: `ip_configuration { ipv4_enabled = false; private_network = google_compute_network.vpc.id; require_ssl = false }` (private IP only, no public IP)
- **Use Cloud SQL private IP as host**: `DATABASE_URL=postgresql://user:pass@10.1.2.3:5432/db` where 10.1.2.3 is Cloud SQL's private IP
- **Terraform data source for IP**: `data "google_sql_database_instance" "main" { name = "my-instance" }` then `locals { db_host = google_sql_database_instance.main.private_ip_address }`
- **Construct DATABASE_URL in Terraform**: Store only password in Secret Manager, build URL with private IP: `DATABASE_URL=postgresql://${var.db_user}:${secret}@${local.db_host}:5432/${var.db_name}`
- **Verify VPC connector egress**: Set `vpc_egress = "private-ranges-only"` to force private IP routing, reject public IP fallback
- **SSL configuration**: For private IP, `require_ssl = false` is safe (traffic stays in VPC). For public IP, always use SSL.

**Warning signs:**
- Cloud Run logs show connections to Cloud SQL public IP (34.x.x.x) instead of private IP (10.x.x.x)
- Database connection works without VPC connector (indicates public IP usage)
- GCP billing shows Cloud Run egress charges to Cloud SQL
- Connection attempts to 127.0.0.1 or localhost fail with "connection refused"
- Cloud SQL "Connections" dashboard shows connections from external IPs
- Services work in Cloud Shell but fail in Cloud Run (different network context)

**Phase to address:**
Phase 1 (Cloud Run Service Deployment) - Configure private IP during Cloud SQL creation. Cannot easily add private IP to existing instance without downtime.

---

### Pitfall 7: Terraform State Lock Conflicts in Multi-Service Deployment

**What goes wrong:**
Multiple services (api-service, extraction-service, grounding-service, hitl-ui) deployed in parallel via CI/CD all attempt to update same Terraform state, causing "Error acquiring state lock" failures. Deployments retry indefinitely, block each other, and eventually time out. Manual intervention required to release locks. CI pipeline shows all services "deploying" but none complete.

**Why it happens:**
Single Terraform state file for all Cloud Run services means any change requires exclusive write lock. CI/CD triggers parallel deployments for multiple services on push to main. Terraform acquires GCS state lock, begins deployment, other services wait for lock release. If deployment takes 5+ minutes (image build + Cloud Run rollout), other services time out waiting for lock.

**How to avoid:**
- **Separate state files per service**: Use workspaces or separate root modules: `terraform workspace new api-service` or separate directories `infra/api-service/`, `infra/extraction-service/`
- **Shared infrastructure separate from services**: Split into `infra/foundation/` (VPC, Cloud SQL, Secret Manager) and `infra/services/` (individual Cloud Run services)
- **State backend configuration**: Enable GCS object versioning for disaster recovery, use short lock timeout: `lock_timeout = "5m"`
- **CI/CD sequential deployment**: Deploy foundation first, then deploy services sequentially or use job dependencies in GitHub Actions
- **Terragrunt for dependency management**: Use terragrunt to define dependency graph and manage parallel execution safely
- **Remote state data sources**: Have service modules read foundation outputs via `data "terraform_remote_state" "foundation"` instead of same state file

**Warning signs:**
- CI deployments fail with "Error acquiring the state lock" from multiple jobs
- Terraform state file has `.tflock` file in GCS bucket that persists after deployment failure
- `terraform force-unlock` required regularly
- Deployments succeed when run sequentially but fail when run in parallel
- Pipeline logs show multiple jobs waiting for "Acquiring state lock..."
- One service deployment blocks unrelated service deployment

**Phase to address:**
Phase 0 (Infrastructure Foundation) - Design state file structure before first deployment. Splitting state files after creation requires state migration.

---

### Pitfall 8: Cold Start Latency Exceeding Client Timeout

**What goes wrong:**
First request after scale-to-zero takes 15-30 seconds, exceeding default API client 10-second timeout. Users see 504 Gateway Timeout errors. HITL UI shows loading spinner indefinitely. After cold start completes, subsequent requests succeed. Problem appears unpredictably when Cloud Run scales down during low traffic periods (nights, weekends).

**Why it happens:**
Python services (FastAPI + LangGraph) have heavy startup: import ML models, initialize UMLS MCP connection, establish database connection pool, load configuration. Cloud Run pulls container image (if not cached), starts container, runs application startup code. Default Cloud Run CPU allocation during startup is same as runtime (1 vCPU), insufficient for parallel initialization. Scale-to-zero saves costs but cold starts destroy user experience.

**How to avoid:**
- **Enable Startup CPU Boost**: `startup_cpu_boost = true` in Terraform (allocates 4 vCPUs during startup, reduces cold start time by 50%)
- **Set minimum instances**: `min_instance_count = 1` for user-facing services (api-service, hitl-ui) to keep one warm instance. Cost: ~$15/month for 1 instance with 512MB RAM.
- **Lazy initialization**: Defer model loading until first use: `@lru_cache def get_model()` instead of loading at module import time
- **Optimize container image**: Multi-stage builds, minimize layer count, use Python slim base image, pre-compile .pyc files
- **Increase client timeout**: Set API client timeout to 60 seconds for endpoints that may hit cold starts
- **Startup probe configuration**: Use startup probe with higher `initial_delay_seconds = 30` and `timeout_seconds = 10` to prevent premature healthcheck failures
- **Pre-warming strategy**: Schedule Cloud Scheduler to ping services every 10 minutes during business hours

**Warning signs:**
- First request after inactivity takes >10 seconds, subsequent requests <1 second
- Cloud Run logs show "Container startup time: 25.3s" messages
- 504 errors correlate with instance scaling from 0→1 in Cloud Run metrics
- Users report "app is slow on Monday mornings" (weekend scale-to-zero)
- Cloud Run metrics show instance count dropping to 0 during low traffic
- Startup latency varies widely: sometimes 5s, sometimes 30s (container image caching variability)

**Phase to address:**
Phase 2 (Performance Optimization) - Establish baseline latency requirements first, then optimize. Enable startup CPU boost immediately (low cost, high impact). Defer min_instance_count tuning until traffic patterns understood.

---

### Pitfall 9: Artifact Registry Authentication Missing in CI/CD

**What goes wrong:**
GitHub Actions or Cloud Build can't push Docker images to Artifact Registry with "denied: Permission denied" errors. Or push succeeds but Cloud Run deployment fails with "failed to pull image" because Cloud Run service account lacks Artifact Registry Reader role. Images pushed to wrong registry (GCR instead of Artifact Registry) or wrong region repository.

**Why it happens:**
Artifact Registry requires explicit authentication configuration unlike legacy GCR. `gcloud auth configure-docker` only configures *.gcr.io by default, not Artifact Registry hostnames. CI/CD service accounts need both push permissions (Artifact Registry Writer) and pull permissions (Artifact Registry Reader) on separate service accounts (CI SA vs. Cloud Run SA). Multi-region repositories require exact hostname match in Docker tag.

**How to avoid:**
- **Authenticate to Artifact Registry in CI**: `gcloud auth configure-docker us-docker.pkg.dev` with specific hostname
- **Use Workload Identity Federation**: Authenticate GitHub Actions to GCP without service account keys: `google-github-actions/auth@v2` with workload identity provider
- **CI service account IAM**: Grant `roles/artifactregistry.writer` to CI/CD service account for pushing images
- **Cloud Run service account IAM**: Grant `roles/artifactregistry.reader` to Cloud Run service account for pulling images
- **Consistent image naming**: Store in Terraform variable: `locals { image_repo = "us-docker.pkg.dev/${var.project_id}/cloud-run/${var.service_name}" }`
- **Verify registry in Terraform**: Use data source to validate repository exists: `data "google_artifact_registry_repository" "repo"`
- **Don't include ~/.config/gcloud/gce in image**: Exclude from Docker image, regenerates in Cloud Run and causes auth failures

**Warning signs:**
- Docker push fails with "denied: Permission 'artifactregistry.repositories.uploadArtifacts' denied"
- Cloud Run deployment fails with "failed to pull image" or "unauthorized to pull image"
- Images exist in Artifact Registry but Cloud Run can't access them
- `gcloud` commands work locally but fail in CI/CD
- Different behavior between Cloud Build (works) and GitHub Actions (fails)
- Images accidentally pushed to gcr.io instead of us-docker.pkg.dev

**Phase to address:**
Phase 0 (Infrastructure Foundation) - Set up Artifact Registry and IAM bindings before first image push. Establish CI/CD authentication pattern early.

---

### Pitfall 10: Ingress/Egress Configuration Blocking Internal Service Communication

**What goes wrong:**
Frontend service (hitl-ui) can't reach backend API (api-service) despite both deployed to Cloud Run in same project. Requests fail with "connection refused" or timeout. Setting ingress to "internal" on API service blocks legitimate traffic. Setting egress to "private-ranges-only" blocks external API calls (Gemini, Vertex AI).

**Why it happens:**
Ingress "internal" means traffic must originate from VPC network, but default Cloud Run egress is via internet (not VPC). Service-to-service calls from hitl-ui → api-service go through public internet, Cloud Run sees external origin, blocks at ingress. Setting "all" egress routes all traffic (including to Gemini API) through VPC, but Gemini API is external, so requests fail or incur VPC egress costs.

**How to avoid:**
- **For internal-only services (extraction-service, grounding-service)**: Set `ingress = "INGRESS_TRAFFIC_INTERNAL_ONLY"` AND configure callers with VPC connector or direct VPC egress
- **For API services called by UI**: Use `ingress = "INGRESS_TRAFFIC_ALL"` with authentication (IAM or API key) instead of network restrictions
- **For services calling external APIs**: Use `vpc_egress = "PRIVATE_RANGES_ONLY"` to route only RFC1918 traffic to VPC, send public traffic to internet directly
- **Configure caller egress**: For hitl-ui to reach internal api-service, set `network_interfaces { network = var.vpc; subnetwork = var.subnet }` (direct VPC egress)
- **Use Cloud Run service URLs**: Services can invoke each other via Cloud Run service URL with IAM authentication (no VPC required for simple case)
- **Document traffic flows**: Create matrix: which services call which, which are public vs internal, which need VPC egress

**Warning signs:**
- Service-to-service calls fail with "could not resolve host" or connection timeout
- External API calls (Gemini, Vertex AI) fail after adding VPC connector
- Ingress setting changes break existing functionality
- Requests work from Cloud Shell but fail from Cloud Run
- `curl https://api-service-xyz.run.app` works externally but fails from hitl-ui service
- Egress charges spike after VPC configuration change

**Phase to address:**
Phase 1 (Cloud Run Service Deployment) - Define ingress/egress requirements per service during initial architecture. Document which services are public vs internal, which call external APIs.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Use image tags (:latest) instead of digests (@sha256:...) | Simpler CI/CD, familiar pattern from Docker Compose | Terraform can't detect image updates, manual redeployment required, no rollback to previous image | Never for production—defeats IaC immutability |
| Store secrets as Terraform variables instead of Secret Manager | Faster migration from .env files, less GCP configuration | Secrets in state file, version control risk, manual rotation, security violation | Only for non-sensitive config (API URLs, feature flags) |
| Single Terraform state file for all services | Simpler initial setup, fewer state files to manage | State lock contention, slow deployments, blast radius (one error blocks all), hard to split later | Acceptable for <3 services or solo developer |
| Public IP on Cloud SQL with VPC for "flexibility" | Easier debugging, can connect from anywhere, no VPC complexity | $200-400/month egress costs at scale, security risk, audit failures | Never for production—always use private IP only |
| Skip VPC connector, use public Cloud SQL | Faster setup, no VPC/networking knowledge required | No private connectivity, egress costs, can't use internal-only ingress, security weakness | Only for proof-of-concept demos |
| Set max_instances to 1000 without connection pooling limits | Prevents traffic-based failures, Cloud Run can scale infinitely | Database connection exhaustion, cascading failures, high costs during attacks/traffic spikes | Never—always set max_instances = DB_max_connections / pool_size |
| Use Cloud Run default CPU allocation (no startup CPU boost) | No configuration needed, simplest Terraform | 15-30 second cold starts, user timeouts, poor UX, retry storms | Only for non-user-facing batch jobs |
| Mount all secrets as environment variables instead of volumes | Simpler Terraform, matches Docker Compose pattern | Secrets cached in instance, rotation requires redeployment, exposed in /proc | Acceptable if secrets never rotate (API keys with long lifetime) |
| Deploy all services in same `terraform apply` | Atomic deployment, simpler CI/CD | Long deployment times, one service failure rolls back all, state lock contention | Never for >2 services—always separate service deployments |
| Store Terraform state in local file (no GCS backend) | No GCS setup, works immediately, free | No collaboration, no locking, state loss risk, can't use CI/CD | Only for solo experiments, never for shared projects |

---

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Cloud SQL connection | Using localhost or 127.0.0.1 from Docker Compose | Use Cloud SQL private IP address (10.x.x.x) as DATABASE_HOST, construct connection string in Terraform |
| Secret Manager secrets | Storing secret value in Terraform variable | Reference secret by ID only: `value_source { secret_key_ref { secret = "projects/.../secrets/..." } }`, create secrets outside Terraform |
| Gemini/Vertex AI APIs | Hardcoding API keys in environment variables | Store in Secret Manager, mount as env var from secret reference, never in Terraform state |
| Artifact Registry | Using gcr.io image path from old tutorials | Use Artifact Registry path: `us-docker.pkg.dev/project/repo/image`, authenticate with `gcloud auth configure-docker us-docker.pkg.dev` |
| GCS for PDFs | Using Cloud Run service account with default permissions | Grant `roles/storage.objectViewer` to Cloud Run service account, use signed URLs for uploads, set bucket lifecycle policies |
| VPC connector | Creating connector without checking subnet CIDR conflicts | Reserve /28 subnet for connector (16 IPs), separate from Cloud SQL IP range, document in Terraform: `cidr_range = "10.8.0.0/28"` |
| UMLS MCP server | Connecting to external MCP server without firewall rules | Configure VPC firewall rules to allow egress to MCP server IP/port, or deploy MCP server in same VPC |
| OAuth credentials | Storing credentials.json in Terraform or git | Store in Secret Manager, mount as volume: `/secrets/oauth/credentials.json`, read in application code |
| PostgreSQL connection pooling | Using default SQLAlchemy pool_size=10 | Set pool_size=2, max_overflow=1 for Cloud Run, add pool_pre_ping=True for stale connection detection |
| Cloud Run health checks | No health check endpoint, using default / | Create `/health` endpoint returning 200, configure liveness_probe with path="/health", use startup probe for slow-starting services |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| No connection pool limits + high max_instances | Database "too many connections" errors during traffic spikes | Set max_instances = ceil(DB_max_connections / (pool_size + max_overflow)), for 100 DB connections and pool=3: max_instances=33 | Cloud Run scales beyond ~30 instances (depends on DB connection limit) |
| Synchronous PDF processing in API request handler | API timeouts, 504 errors, poor UX | Move to async with Pub/Sub + extraction-service worker, return 202 Accepted immediately, poll for results | PDFs >10 pages or OCR required (~30% of protocols) |
| No container image layer caching | 10-15 minute CI builds, slow deployments | Use multi-stage Dockerfile, leverage BuildKit cache, export cache to Artifact Registry: `--cache-from=us-docker.pkg.dev/.../cache` | More than 3 Python dependencies or frequent rebuilds |
| Scale-to-zero for user-facing services | 15-30 second cold starts, user timeouts, poor UX | Set min_instance_count=1 for api-service and hitl-ui ($15/month/service), enable startup_cpu_boost=true | First request after inactivity (nights/weekends) |
| Single Cloud SQL instance for all services | Connection pool exhaustion, database becomes bottleneck | Use Cloud SQL connection pooler (port 6432) for 10,000+ connections, or separate read replicas for read-heavy services | >50 Cloud Run instances total across all services |
| No request timeout configuration | Stuck requests consume instances, degraded performance | Set timeout=60 in Cloud Run, implement request timeouts in client, add circuit breakers for external APIs | Long-running requests (Gemini API, extraction jobs) |
| Serving static files from Cloud Run | High egress costs, slow serving, Cloud Run instances wasted on static content | Serve from GCS bucket with CDN (Cloud CDN or Cloudflare), only use Cloud Run for dynamic API | hitl-ui serving Vite build output (should be GCS + Cloud CDN) |

---

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Public IP on Cloud SQL instance | Database exposed to internet, brute force attacks, audit failures, egress costs | Disable public IP: `ip_configuration { ipv4_enabled = false; private_network = vpc.id }`, only use private IP (10.x.x.x) |
| API keys in Terraform variables or .tfvars files | Secrets in git history, Terraform state file, CI logs, shared with team | Always use Secret Manager, reference by ID only in Terraform, never store secret values in IaC |
| Cloud Run service allows unauthenticated invocations | Public internet can call internal services, data exposure, abuse | Set `ingress = "INGRESS_TRAFFIC_INTERNAL_ONLY"` for internal services, require IAM authentication for APIs, use API gateway for public endpoints |
| Overly permissive service account IAM | Service account can access unrelated resources, blast radius on compromise | Use separate service accounts per service with minimum permissions, never use project-level roles, document required roles in Terraform |
| Secrets mounted as environment variables without version pinning | `latest` version may change unexpectedly, breaking services | Pin secrets to specific versions: `version = "1"`, update version explicitly in Terraform, test before promoting |
| GCS bucket with public access for protocol PDFs | PHI/PII exposure, regulatory violations, unauthorized access | Set `uniform_bucket_level_access = true`, use IAM conditions, generate signed URLs for time-limited access, never use `allUsers` |
| No VPC Service Controls for sensitive APIs | Data exfiltration risk, compliance violations | Create VPC Service Control perimeter around project, restrict Vertex AI, Cloud SQL, Secret Manager to VPC only |
| Cloud Run service account has Secret Manager Admin | Service can read/write all secrets, privilege escalation risk | Grant `roles/secretmanager.secretAccessor` only, scope to specific secrets: `member = "serviceAccount:${sa}"; secret = google_secret_manager_secret.api_key.id` |

---

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No loading states during cold starts | Users see blank screen or timeout errors, assume app is broken | Show "Warming up service..." message, implement retry with exponential backoff, set min_instances=1 for user-facing services |
| HTTP 500 errors without user-friendly messages | "Internal Server Error" confuses users, can't self-diagnose | Implement error handling middleware, return specific error messages, log errors with correlation IDs for debugging |
| API timeout during PDF extraction blocks UI | UI freezes for 30+ seconds, users refresh/retry causing duplicate jobs | Use async pattern: submit job returns immediately with job_id, poll for status with /jobs/{id}, show progress bar |
| No visual feedback for long-running operations | Users don't know if extraction is working or stuck | WebSocket or SSE for real-time updates, show "Processing page 3 of 15..." progress, estimate time remaining |
| Cold start delays without explanation | Random 15-second delays feel like bugs | Detect cold start in client (first request after 5min), show "Starting service..." message, pre-warm on user login |
| Cryptic error messages from external APIs | "Gemini API error: 429" means nothing to clinical researchers | Translate API errors to domain language: "Rate limit exceeded. Please wait 1 minute and try again.", hide technical details unless debugging |
| No retry logic for transient failures | Random failures require manual refresh, poor UX | Implement automatic retry with exponential backoff for 5xx errors, show "Retrying..." indicator, alert on repeated failures |
| Large protocol uploads with no progress indication | Users don't know if 50MB PDF is uploading or stuck | Use signed URL upload to GCS with progress bar, chunk uploads, validate file size client-side before upload |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Cloud Run service deployed:** Often missing IAM bindings for Secret Manager, service account permissions, health check endpoint—verify secrets accessible, `/health` returns 200, SA has minimum required roles
- [ ] **VPC connector created:** Often missing subnet IP range reservation, region mismatch with Cloud Run—verify connector region matches Cloud Run and Cloud SQL, subnet doesn't conflict with other ranges
- [ ] **Cloud SQL instance created:** Often missing private IP configuration, connection pooling setup—verify `ipv4_enabled = false`, private IP allocated, connection limit documented
- [ ] **Secret Manager secrets created:** Often missing IAM bindings for service account, version pinning—verify service account has `secretAccessor` role, secrets pinned to version (not `latest`)
- [ ] **Artifact Registry repository created:** Often missing IAM bindings for CI/CD push, Cloud Run pull—verify CI SA has `writer` role, Cloud Run SA has `reader` role
- [ ] **Docker image built and pushed:** Often using image tag instead of digest, breaking Terraform change detection—verify image reference uses `@sha256:...` digest in Terraform
- [ ] **Database migrations automated:** Often missing in Dockerfile CMD or Cloud Build step—verify Alembic migrations run before app starts: `alembic upgrade head && uvicorn ...`
- [ ] **Connection pooling configured:** Often using default pool_size=10, missing max_instances limit—verify pool_size ≤ 3, max_instances set based on DB connection limit
- [ ] **Health checks configured:** Often missing startup probe for slow services—verify liveness probe (restarts unhealthy), startup probe (delays liveness during startup), readiness probe (controls traffic routing)
- [ ] **Terraform state backend configured:** Often using local state file, no locking—verify GCS backend configured, versioning enabled, workspace or separate state per service
- [ ] **IAM permissions set:** Often missing required roles or overly permissive—verify service account has exactly required roles (Cloud SQL Client, Secret Manager Secret Accessor, Artifact Registry Reader), no project-level editor/owner
- [ ] **Environment variables vs secrets separated:** Often all variables in Secret Manager or all secrets in env vars—verify sensitive values (API keys, passwords) in Secret Manager, non-sensitive config (URLs, ports) in environment variables

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| VPC connector region mismatch | MEDIUM | Create new VPC connector in correct region; update Cloud Run service Terraform with new connector ID; apply changes; delete old connector; may cause brief connection interruption |
| Secrets in Terraform state | HIGH | Rotate all exposed secrets immediately; create Secret Manager secrets with new values; update Terraform to use secret references; remove old variables; sanitize state file history if committed to git |
| Image tag instead of digest | LOW | Update CI/CD to capture digest after build: `docker push && docker inspect --format='{{index .RepoDigests 0}}'`; update Terraform to use digest variable; apply; future deploys will detect changes |
| Connection pool exhaustion | LOW | Calculate correct max_instances: `DB_connections / pool_size`; update Terraform `max_instances`; apply; add monitoring alert for connection count >80% of limit |
| Cold start latency | MEDIUM | Enable `startup_cpu_boost = true` (immediate, no code change); optimize Dockerfile with multi-stage build (rebuild required); set `min_instance_count = 1` for user-facing services (+$15/mo) |
| State lock conflicts | MEDIUM | Split state files per service (create separate Terraform directories); migrate state: `terraform state pull > temp.tfstate`, initialize new backend, `terraform state push temp.tfstate`; update CI/CD to deploy sequentially |
| Missing private IP on Cloud SQL | HIGH (possible downtime) | Create new Cloud SQL instance with private IP; migrate data with `pg_dump` \| `pg_restore`; update DATABASE_URL secret; redeploy services; verify connectivity; delete old instance; 1-2 hour maintenance window required |
| IAM permission missing | LOW | Add required IAM binding in Terraform: `google_secret_manager_secret_iam_member`; apply; wait 60 seconds for propagation; redeploy Cloud Run service if startup failed |
| Ingress blocking internal traffic | LOW | Change ingress to `INGRESS_TRAFFIC_ALL`; add authentication instead: Cloud Run IAM or API key validation; redeploy; verify service-to-service calls work; document authentication in README |
| Artifact Registry auth failure | LOW | Run `gcloud auth configure-docker us-docker.pkg.dev` with correct hostname; verify service account has `roles/artifactregistry.reader`; may need to delete/recreate service account key if using JSON key auth |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| VPC connector region mismatch | Phase 0: Infrastructure Foundation | Manual test: All resources in same region, VPC connector visible in Cloud Run service dropdown, `gcloud compute networks vpc-access connectors list --region=us-central1` |
| Secret Manager permissions | Phase 0: Infrastructure Foundation | Automated test: Terraform apply creates IAM bindings before services, `gcloud secrets get-iam-policy $SECRET` shows service account has accessor role |
| Image tag vs digest | Phase 0: CI/CD Pipeline Setup | Automated test: CI captures digest after build, Terraform plan detects image changes after rebuild, revision count increments after image push |
| Connection pool exhaustion | Phase 1: Cloud Run Service Deployment | Load test: Generate 100 concurrent requests, verify Cloud Run scales without DB connection errors, max_instances honored |
| .env secrets in Terraform state | Phase 0: Infrastructure Foundation | Automated test: `grep -r "sk-\|postgres:" terraform.tfstate` returns no matches, all API keys in Secret Manager |
| Cloud SQL private IP missing | Phase 0: Infrastructure Foundation | Manual test: `gcloud sql instances describe $INSTANCE \| grep privateIpAddress`, verify ipv4_enabled=false, connection from Cloud Run succeeds |
| Terraform state lock conflicts | Phase 0: Infrastructure Foundation | Automated test: Parallel Terraform applies succeed without lock errors, separate state files per service, CI deploys services independently |
| Cold start latency | Phase 2: Performance Optimization | Load test: Measure p95 latency for first request after 10min idle <5 seconds with startup_cpu_boost, <2 seconds with min_instances=1 |
| Artifact Registry auth failure | Phase 0: CI/CD Pipeline Setup | Automated test: CI pushes image successfully, Cloud Run deployment pulls image without auth errors, service account has reader role |
| Ingress/egress misconfiguration | Phase 1: Cloud Run Service Deployment | Manual test: Service-to-service calls succeed with internal ingress + VPC egress, external API calls (Gemini) succeed with private-ranges-only egress |

---

## Sources

### Terraform GCP Cloud Run Documentation
- [Terraform google_cloud_run_v2_service Documentation](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_run_v2_service)
- [Terraform google_vpc_access_connector Documentation](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/vpc_access_connector)
- [Cloud Run VPC Connector Terraform Example](https://registry.terraform.io/modules/GoogleCloudPlatform/cloud-run/google/latest/examples/cloud_run_vpc_connector)

### Cloud Run to Cloud SQL Connectivity
- [Connect from Cloud Run to Cloud SQL (MySQL)](https://docs.cloud.google.com/sql/docs/mysql/connect-run)
- [Connect from Cloud Run to Cloud SQL (PostgreSQL)](https://docs.cloud.google.com/sql/docs/postgres/connect-run)
- [Connecting to Private CloudSQL from Cloud Run (Codelab)](https://codelabs.developers.google.com/connecting-to-private-cloudsql-from-cloud-run)
- [Cloud SQL with Private IP Only: Good, Bad, and Ugly](https://medium.com/google-cloud/cloud-sql-with-private-ip-only-the-good-the-bad-and-the-ugly-de4ac23ce98a)
- [PostgreSQL Connection Management Best Practices](https://docs.cloud.google.com/sql/docs/postgres/manage-connections)
- [Managed Connection Pooling for Cloud SQL PostgreSQL](https://docs.cloud.google.com/sql/docs/postgres/managed-connection-pooling)

### Secret Manager Integration
- [Configure Secrets for Cloud Run Services](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
- [Secret Manager Access Control with IAM](https://docs.cloud.google.com/secret-manager/docs/access-control)
- [Cloud Run and Secret Manager Integration](https://medium.com/google-cloud/cloud-run-and-secret-manager-3c5d43a72e87)
- [Securely Using .env Files with Cloud Run and Terraform](https://mikesparr.medium.com/securely-using-dotenv-env-files-with-google-cloud-run-and-terraform-e8b14ff04bff)
- [Cloud Run Hot Reload Secret Manager Secrets](https://medium.com/google-cloud/cloud-run-hot-reload-your-secret-manager-secrets-ff2c502df666)

### Terraform State Management
- [Store Terraform State in Cloud Storage](https://cloud.google.com/docs/terraform/resource-management/store-state)
- [Terraform Backend Type: GCS](https://developer.hashicorp.com/terraform/language/backend/gcs)
- [Remote State Management Best Practices (2026)](https://oneuptime.com/blog/post/2026-01-25-terraform-remote-state-management/view)
- [Configuring Remote Backends for Terraform (2026)](https://oneuptime.com/blog/post/2026-02-09-terraform-state-remote-backends/view)

### Artifact Registry and Image Management
- [Deploying to Cloud Run from Artifact Registry](https://cloud.google.com/artifact-registry/docs/integrate-cloud-run)
- [Artifact Registry Access Control with IAM](https://cloud.google.com/artifact-registry/docs/access-control)
- [Deploying Container Images to Cloud Run](https://docs.cloud.google.com/run/docs/deploying)
- [Cloud Run Deployment Not Updating with Image Changes (GitHub Issue)](https://github.com/terraform-providers/terraform-provider-google/issues/6706)
- [Immutable Container Image Tags Best Practices](https://www.proactiveops.io/archive/immutable-container-image-tags/)

### Cloud Run Performance and Optimization
- [Cloud Run General Development Tips](https://docs.cloud.google.com/run/docs/tips/general)
- [Startup CPU Boost for Cloud Run](https://cloud.google.com/blog/products/serverless/announcing-startup-cpu-boost-for-cloud-run--cloud-functions)
- [3 Ways to Optimize Cloud Run Response Times](https://cloud.google.com/blog/topics/developers-practitioners/3-ways-optimize-cloud-run-response-times)
- [Mitigate Cloud Run Cold Startup Strategies](https://omermahgoub.medium.com/mitigate-cloud-run-cold-startup-strategies-to-improve-response-time-cad5a6aea327)
- [Advanced FastAPI Performance Tuning on Cloud Run](https://davidmuraya.com/blog/fastapi-performance-tuning-on-google-cloud-run/)

### Networking and VPC Configuration
- [Cloud Run Private Networking](https://docs.cloud.google.com/run/docs/securing/private-networking)
- [Restrict Network Ingress for Cloud Run](https://docs.cloud.google.com/run/docs/securing/ingress)
- [Configure Cloud Run Direct VPC Egress (Codelab)](https://codelabs.developers.google.com/codelabs/how-to-configure-cloud-run-service-direct-vpc-egress)
- [Direct VPC Egress with VPC Network](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc)

### Cloud Run Service Configuration
- [Configure Memory Limits for Cloud Run Services](https://docs.cloud.google.com/run/docs/configuring/services/memory-limits)
- [Configure CPU Limits for Cloud Run Services](https://docs.cloud.google.com/run/docs/configuring/services/cpu)
- [Cloud Run Concurrency Configuration](https://docs.cloud.google.com/run/docs/about-concurrency)
- [Cloud Run Quotas and Limits](https://docs.cloud.google.com/run/quotas)
- [Configure Container Health Checks](https://docs.cloud.google.com/run/docs/configuring/healthchecks)
- [Cloud Run Health Checks Overview](https://cloud.google.com/blog/products/serverless/cloud-run-healthchecks/)

### Docker Build Optimization
- [Best Practices for Speeding Up Builds in Cloud Build](https://docs.cloud.google.com/build/docs/optimize-builds/speeding-up-builds)
- [Docker Layer Caching Optimization (2026)](https://oneuptime.com/blog/post/2026-01-16-docker-optimize-build-times/view)
- [Faster Docker Image Builds with Layer Caching](https://depot.dev/blog/docker-layer-caching-in-google-cloud-build)
- [Container Image Caching Strategies in Kubernetes CI (2026)](https://oneuptime.com/blog/post/2026-02-09-container-image-caching-ci/view)

### Docker Compose to Cloud Run Migration
- [Migrating from Docker Compose to Terraform](https://medium.com/continuous-insights/migrating-from-docker-compose-to-terraform-automating-your-container-stack-conversion-052dbc0f949d)
- [Configure Environment Variables for Cloud Run Services](https://docs.cloud.google.com/run/docs/configuring/services/environment-variables)
- [Mastering Cloud Run Environment Variables](https://ahmet.im/blog/mastering-cloud-run-environment-variables/)

---

*Terraform GCP Cloud Run deployment pitfalls research for: Clinical Trial Criteria Extraction System*
*Researched: 2026-02-12*
*Confidence: HIGH*
