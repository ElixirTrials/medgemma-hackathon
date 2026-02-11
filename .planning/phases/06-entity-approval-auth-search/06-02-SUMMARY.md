---
phase: 06-entity-approval-auth-search
plan: 02
subsystem: hitl-ui
tags: [frontend, auth, entity-approval, search, oauth, jwt, react]
dependency-graph:
  requires:
    - Google OAuth backend endpoints (/auth/login, /auth/callback)
    - JWT token authentication on API endpoints
    - Entity approval endpoints (/entities/*)
    - Full-text search endpoint (/criteria/search)
  provides:
    - Login page with Google OAuth redirect
    - Auth state management with localStorage persistence
    - Entity review UI with SNOMED/UMLS display
    - Search UI with filters and pagination
  affects:
    - All API hooks now include Authorization headers
    - Dashboard has search entry point
    - ReviewPage has Entities tab for batch entity review
tech-stack:
  added:
    - Zustand store for auth state
    - Radix Tabs for criteria/entities tab view
    - Debounced search input (300ms)
  patterns:
    - Auth token injection via fetchApi in all hooks
    - Entity grouping by criteria_id for display
    - SNOMED badge with medical-themed styling
    - UMLS link to external browser
    - Search result cards with relevance ranking
key-files:
  created:
    - apps/hitl-ui/src/stores/authStore.ts
    - apps/hitl-ui/src/hooks/useAuth.ts
    - apps/hitl-ui/src/hooks/useEntities.ts
    - apps/hitl-ui/src/hooks/useSearch.ts
    - apps/hitl-ui/src/components/EntityCard.tsx
    - apps/hitl-ui/src/screens/EntityList.tsx
    - apps/hitl-ui/src/screens/LoginPage.tsx
    - apps/hitl-ui/src/screens/SearchPage.tsx
  modified:
    - apps/hitl-ui/src/hooks/useReviews.ts (auth headers)
    - apps/hitl-ui/src/hooks/useProtocols.ts (auth headers)
    - apps/hitl-ui/src/screens/ReviewPage.tsx (Entities tab)
    - apps/hitl-ui/src/screens/Dashboard.tsx (search entry point)
    - apps/hitl-ui/src/App.tsx (routes + auth header)
decisions:
  - Use Zustand store with localStorage for auth state persistence across page refreshes
  - Keep fetchApi duplicated in each hook file (matching existing pattern in useReviews/useProtocols)
  - Use Radix Tabs for criteria/entities toggle in ReviewPage (already in dependencies)
  - Debounce search input with 300ms delay to avoid excessive API calls
  - Group entities by criteria_id in both EntityList and ReviewPage Entities tab
  - Use SNOMED badge with blue medical theme (blue-100 bg, blue-800 text)
  - Make UMLS CUI a clickable link to https://uts.nlm.nih.gov/cts/umls/concept/{cui}
  - Show grounding confidence with same 3-tier badge as criteria confidence
  - Search results show protocol title as link, relevance rank, and review status
  - Add search shortcut on Dashboard as new card
metrics:
  duration_minutes: 7
  tasks_completed: 2
  files_created: 8
  files_modified: 6
  commits: 2
  completed_date: 2026-02-11
---

# Phase 6 Plan 2: Frontend UI for Auth, Entity Approval, and Search Summary

**One-liner:** Login page, auth state with JWT persistence, entity review UI with SNOMED badges and UMLS links, and search page with filters and relevance ranking

## What Was Built

### Task 1: Auth state management, entity hooks, and entity approval UI

**Commit:** cc99da4

- **authStore.ts**: Zustand store managing JWT token and user info with localStorage persistence
  - `setAuth()` saves token/user to localStorage
  - `logout()` removes from localStorage
  - `isAuthenticated()` checks token presence
  - `getAuthHeaders()` utility returns Authorization header
  - `initiateLogin()` redirects to Google OAuth endpoint
- **useAuth.ts**: Hook wrapping authStore, exports login/logout/token/user/isAuthenticated
- **Updated fetchApi in useReviews.ts and useEntities.ts**: Inject Authorization header from authStore into all API requests
- **useEntities.ts**: Entity API hooks following useReviews pattern
  - `useEntityListByCriteria(criteriaId)` - GET /entities/criteria/{criteriaId}
  - `useEntityListByBatch(batchId)` - GET /entities/batch/{batchId}
  - `useEntityAction()` - POST /entities/{entityId}/action (approve/reject/modify)
  - EntityResponse interface with UMLS CUI, SNOMED code, preferred term, grounding confidence/method
- **EntityCard.tsx**: Entity card component following CriterionCard pattern
  - Entity type badge (color-coded: Condition=blue, Medication=purple, Procedure=green, Lab_Value=orange, Demographic=gray, Biomarker=teal)
  - SNOMED badge showing code + preferred term (blue medical theme)
  - UMLS CUI badge as external link to UMLS browser (opens in new tab)
  - Grounding confidence badge with 3-tier color system (>=0.85 green, >=0.7 yellow, <0.7 red)
  - Grounding method shown as small text
  - Review actions: Approve (green), Reject (red), Modify (blue) buttons
  - Modify mode: editable fields for umls_cui, snomed_code, preferred_term
  - Review status badge (approved=green, rejected=red, modified=yellow, null=gray pending)
  - Collapsible context window section
- **EntityList.tsx**: Standalone entity list screen
  - Takes batchId from route params
  - Groups entities by criteria_id
  - Summary stats at top: total, approved, pending, rejected counts
  - Each group shows criterion ID as header, EntityCard components for its entities
- **LoginPage.tsx**: Simple login page
  - App title and description
  - "Sign in with Google" button with Google logo SVG
  - Redirects to Dashboard if already authenticated
- **Updated ReviewPage.tsx**: Added Entities tab alongside Criteria view
  - Used Radix Tabs to toggle between "Criteria" and "Entities" views
  - Entities tab shows grouped entities for the batch using EntityCard
  - Criteria tab retains existing criteria review functionality
- **Updated App.tsx**: Added routes and auth header
  - `/login` -> LoginPage
  - `/entities/:batchId` -> EntityList
  - `/search` -> SearchPage
  - Navigation header when authenticated showing user info and logout button

### Task 2: Search UI with filters and results display

**Commit:** a9d3216

- **useSearch.ts**: Search API hook following existing hook patterns
  - SearchResult interface with protocol context (protocol_id, protocol_title), criteria type, confidence, review status, relevance rank
  - SearchResponse interface with pagination (items, total, page, page_size, pages, query)
  - `useCriteriaSearch(query, filters, page, pageSize)` - GET /criteria/search?q=...&filters
  - Enabled only when query >= 2 chars
  - Includes auth headers via same pattern as useEntities
  - Filters: protocol_id, criteria_type, review_status
- **Updated useProtocols.ts**: Added auth header injection (same pattern as other hooks)
- **SearchPage.tsx**: Full search UI with filters and pagination
  - Search bar with debounced input (300ms delay)
  - Filter bar with protocol dropdown (populated from useProtocolList), criteria type dropdown (inclusion/exclusion), review status dropdown (approved/rejected/modified/pending)
  - "Clear Filters" button when filters active
  - Empty state: "Search across all criteria. Try terms like 'diabetes', 'age', 'blood pressure'."
  - No results state: "No criteria match '{query}'. Try different search terms."
  - Loading state: spinner
  - Results list showing:
    - Protocol title as link to /protocols/{id}
    - Criteria type badge (inclusion=blue, exclusion=orange)
    - Confidence indicator (3-tier badge)
    - Review status badge
    - Criteria text
    - Relevance rank (Rank #N)
    - Link to review page: "View in Review →"
  - Pagination controls: Previous/Next buttons with page indicator
- **Updated Dashboard.tsx**: Added "Search" card with "Search Criteria" button navigating to /search
- **Updated App.tsx**: Added `/search` route

## Deviations from Plan

None - plan executed exactly as written.

## Key Integration Points

- **Auth flow:** authStore reads token from localStorage on init → login() redirects to Google OAuth → token stored in localStorage → all API hooks include Authorization header via fetchApi
- **Entity review:** EntityList and ReviewPage Entities tab both group entities by criteria_id and use EntityCard for display
- **SNOMED/UMLS display:** SNOMED badge shows code + preferred term, UMLS CUI is clickable link to external browser
- **Search integration:** Search results link to protocol detail page and review batch page for seamless navigation

## Verification Results

All verification checks passed:

- `npx biome check` passes on all new and modified files (after formatting fixes)
- `npx tsc --noEmit` passes with no TypeScript errors
- All routes accessible in App.tsx
- All new files follow existing patterns (CriterionCard → EntityCard, useReviews → useEntities/useSearch)

## Next Steps

1. Test OAuth callback flow with real Google OAuth credentials
2. Verify JWT token refresh/expiration handling
3. Test entity approval actions with backend API
4. Test search with PostgreSQL full-text search (GIN index)
5. Verify search filters work correctly (protocol, type, status)
6. Add auth guard to redirect unauthenticated users to /login (optional, backend auth is primary security)
7. Consider adding "My Reviews" or user-specific activity views
8. Add keyboard shortcuts for search (e.g., Cmd+K to open search)

## Self-Check: PASSED

All created files verified:

- `apps/hitl-ui/src/stores/authStore.ts` exists
- `apps/hitl-ui/src/hooks/useAuth.ts` exists
- `apps/hitl-ui/src/hooks/useEntities.ts` exists
- `apps/hitl-ui/src/hooks/useSearch.ts` exists
- `apps/hitl-ui/src/components/EntityCard.tsx` exists
- `apps/hitl-ui/src/screens/EntityList.tsx` exists
- `apps/hitl-ui/src/screens/LoginPage.tsx` exists
- `apps/hitl-ui/src/screens/SearchPage.tsx` exists

All commits verified:

- Commit cc99da4 exists (Task 1)
- Commit a9d3216 exists (Task 2)
