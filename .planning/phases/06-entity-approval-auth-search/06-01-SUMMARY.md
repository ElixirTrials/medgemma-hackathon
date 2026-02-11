---
phase: 06-entity-approval-auth-search
plan: 01
subsystem: api-service
tags: [auth, entity-approval, search, jwt, oauth, postgres-fts]
dependency-graph:
  requires:
    - User model with email uniqueness
    - JWT secret key (env var)
    - Google OAuth credentials (env vars)
    - PostgreSQL for GIN index (optional, SQLite fallback)
  provides:
    - Google OAuth authentication flow
    - JWT-based auth dependency for all endpoints
    - Entity approval API (list, approve/reject/modify)
    - Full-text search over criteria with filters
  affects:
    - All existing API endpoints now require auth
    - Test fixtures now override get_current_user
tech-stack:
  added:
    - authlib (OAuth client)
    - PyJWT (JWT encoding/decoding)
    - itsdangerous (session middleware)
    - starlette.middleware.sessions (OAuth state)
  patterns:
    - Router-level auth via dependencies=[Depends(get_current_user)]
    - JWT Bearer token validation in Header dependency
    - PostgreSQL full-text search with SQLite fallback
    - GIN index migration with dialect check
key-files:
  created:
    - services/api-service/src/api_service/auth.py
    - services/api-service/src/api_service/entities.py
    - services/api-service/src/api_service/search.py
    - services/api-service/alembic/versions/6bba3f92fdc1_add_user_model.py
    - services/api-service/alembic/versions/47530bf7f47c_add_gin_index_for_fulltext_search.py
    - services/api-service/tests/test_auth_required.py
  modified:
    - libs/shared/src/shared/models.py (added User model)
    - services/api-service/src/api_service/dependencies.py (added get_current_user)
    - services/api-service/src/api_service/main.py (mounted routers with auth)
    - services/api-service/tests/conftest.py (added auth overrides)
    - pyproject.toml (added auth dependencies)
    - services/api-service/pyproject.toml (added auth dependencies)
decisions:
  - Use router-level auth dependencies to protect all endpoints in protocols/reviews/entities/search routers
  - Keep /health, /ready, /, /auth/login, /auth/callback as public (no auth required)
  - Use FastAPI Header(...) dependency for JWT extraction (returns 422 if missing, 401 if invalid)
  - Override get_current_user in test_client fixture so existing tests pass without modification
  - Use PostgreSQL full-text search with GIN index, fall back to LIKE for SQLite dev
  - Entity approval follows criteria review pattern (Review + AuditLog records)
metrics:
  duration_minutes: 9
  tasks_completed: 2
  files_created: 8
  files_modified: 6
  commits: 2
  completed_date: 2026-02-11
---

# Phase 6 Plan 1: Backend API for Authentication, Entity Approval, and Search Summary

**One-liner:** Google OAuth with JWT protection on all API endpoints, entity approval workflow with SNOMED/CUI fields, and PostgreSQL full-text search over criteria

## What Was Built

### Task 1: User Model, OAuth Auth Flow, JWT Auth Dependency

**Commit:** 4257b74

- Added User model to `shared/models.py` with email unique constraint and index
- Added authlib, PyJWT, itsdangerous dependencies to root and api-service pyproject.toml
- Generated Alembic migration for User table with unique email index
- Created `auth.py` router with three endpoints:
  - `GET /auth/login` - redirects to Google OAuth authorization
  - `GET /auth/callback` - exchanges code for token, creates/updates User, issues JWT
  - `GET /auth/me` - returns current user info from JWT
- Added `get_current_user` dependency in `dependencies.py` that validates JWT Bearer tokens
- Mounted auth router (public) and protected protocols/reviews routers with `dependencies=[Depends(get_current_user)]`
- Added SessionMiddleware for OAuth state management (required for authlib OAuth flow)
- Updated test fixtures:
  - `test_client` now overrides both `get_db` and `get_current_user`
  - Added `auth_headers` fixture for JWT token generation
  - Added `unauthenticated_client` fixture for testing auth enforcement
- Created `test_auth_required.py` to verify auth behavior (422 without header, 401 with invalid header)
- All existing tests pass with auth override

### Task 2: Entity Approval Endpoints and Full-Text Search

**Commit:** 1b89744

- Created `entities.py` router with three endpoints:
  - `GET /entities/criteria/{criteria_id}` - list entities for a criterion, sorted by span_start (reading order)
  - `GET /entities/batch/{batch_id}` - list entities for all criteria in a batch (joins Entity -> Criteria)
  - `POST /entities/{entity_id}/action` - approve/reject/modify entity, creates Review + AuditLog records
- Entity approval matches criteria review pattern (before/after values, audit logging)
- Entity responses include UMLS CUI, SNOMED code, preferred term, grounding confidence/method
- Created `search.py` router with one endpoint:
  - `GET /criteria/search` - full-text search with filters (protocol_id, criteria_type, review_status) and pagination
  - Uses PostgreSQL `to_tsvector('english', text)` and `plainto_tsquery('english', query)` for ranking
  - Returns results with protocol context (protocol_id, protocol_title) via joins
  - Falls back to LIKE search for SQLite dev environments (logs warning)
- Created manual Alembic migration for GIN index on `to_tsvector('english', criteria.text)`
  - Migration checks dialect and only creates index on PostgreSQL
  - SQLite environments skip the index (no-op upgrade/downgrade)
- Mounted entities and search routers in main.py with auth dependency
- All existing tests pass

## Deviations from Plan

None - plan executed exactly as written.

## Key Integration Points

- **Auth Flow:** `/auth/login` -> Google OAuth -> `/auth/callback` -> JWT issued -> all other endpoints require JWT Bearer token
- **Test Override:** `test_client` fixture overrides `get_current_user` so all existing tests automatically pass auth checks
- **Entity Approval:** Follows same Review + AuditLog pattern as criteria review for consistency
- **Search Fallback:** PostgreSQL full-text search with SQLite LIKE fallback ensures dev environments work without PostgreSQL

## Verification Results

All verification checks passed:

- `uv run ruff check` passes on all new and modified files
- `uv run python -c "from shared.models import User; print(User.__tablename__)"` outputs "user"
- `uv run python -c "from api_service.auth import router; print(router.prefix)"` outputs "/auth"
- `uv run python -c "from api_service.entities import router; print(router.prefix)"` outputs "/entities"
- `uv run python -c "from api_service.search import router; print(router.prefix)"` outputs "/criteria"
- `uv run pytest services/api-service/tests/test_protocol_api.py` - 11 passed
- `uv run pytest services/api-service/tests/test_review_api.py` - 15 passed
- `uv run pytest services/api-service/tests/test_auth_required.py` - 3 passed
- Auth enforcement verified: requests without Authorization header get 422, invalid headers get 401

## Next Steps

1. Set environment variables for deployment:
   - `JWT_SECRET_KEY` (required in production, fallback "dev-secret-key-change-in-production" for local)
   - `SESSION_SECRET` (required for OAuth state, fallback "dev-session-secret" for local)
   - `GOOGLE_CLIENT_ID` (required for OAuth)
   - `GOOGLE_CLIENT_SECRET` (required for OAuth)
2. Run Alembic migrations: `uv run alembic upgrade head` (creates User table and GIN index)
3. Configure OAuth callback URL in Google Cloud Console to match deployed domain
4. Update frontend to implement OAuth login flow and include JWT Bearer token in API requests
5. Add entity approval UI to review and modify UMLS CUI/SNOMED codes
6. Add search UI with filters and result highlighting

## Self-Check: PASSED

All created files verified:

- `services/api-service/src/api_service/auth.py` exists
- `services/api-service/src/api_service/entities.py` exists
- `services/api-service/src/api_service/search.py` exists
- `services/api-service/alembic/versions/6bba3f92fdc1_add_user_model.py` exists
- `services/api-service/alembic/versions/47530bf7f47c_add_gin_index_for_fulltext_search.py` exists
- `services/api-service/tests/test_auth_required.py` exists

All commits verified:

- Commit 4257b74 exists (Task 1)
- Commit 1b89744 exists (Task 2)
