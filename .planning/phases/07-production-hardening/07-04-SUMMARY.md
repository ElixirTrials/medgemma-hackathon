---
phase: 07-production-hardening
plan: 04
subsystem: frontend-error-display
tags: [frontend, error-ui, retry, status-badges, protocol-failures]
completed: 2026-02-12
duration_minutes: 2

dependency_graph:
  requires: [07-01]
  provides: [failure-status-badges, error-reason-display, retry-button-ui]
  affects: [protocol-list-ui, protocol-detail-ui, protocol-hooks]

tech_stack:
  added:
    - useRetryProtocol mutation hook
    - STATUS_LABELS mapping for human-readable status names
    - RetryButton component with loading states
    - Error alert component in ProtocolDetail
  patterns:
    - Distinct visual indicators for failure states (red/orange/dark-red color coding)
    - User-friendly error messaging with categorized reasons
    - Inline retry action with optimistic UI updates

key_files:
  created: []
  modified:
    - apps/hitl-ui/src/hooks/useProtocols.ts
    - apps/hitl-ui/src/screens/ProtocolList.tsx
    - apps/hitl-ui/src/screens/ProtocolDetail.tsx

decisions:
  - desc: "Human-readable STATUS_LABELS map for underscore-separated status values"
    rationale: "Improves UX by showing 'Extraction Failed' instead of 'extraction_failed' in UI"
  - desc: "Retry button positioned in error alert for contextual action"
    rationale: "Places retry action next to error message for clearer user flow"
  - desc: "Processing banner for uploaded/extracting states without circuit breaker detection"
    rationale: "Simple progress indicator; circuit breaker status shown via backend error_reason field"
  - desc: "Biome auto-formatting applied to match project style"
    rationale: "Ensures consistent code formatting across frontend codebase"

metrics:
  tasks_completed: 2
  files_modified: 3
  files_created: 0
  commits: 2
---

# Phase 07 Plan 04: Frontend Failure Status Display & Retry UI Summary

Protocol list shows distinct failure status badges (red/orange/dark-red), detail page displays categorized error reasons, and retry extraction button triggers backend retry endpoint.

## Overview

This plan completes the frontend portion of Phase 7 production hardening by providing researchers with clear visual feedback on protocol failures and actionable retry capabilities. The Protocol interface now supports 9 status values (uploaded, extracting, extraction_failed, grounding, grounding_failed, pending_review, complete, dead_letter, archived) with an error_reason field for user-facing error messages. Failure statuses are distinguished by distinct color badges: red for extraction failures, orange for grounding failures, and dark red for dead-letter protocols. The ProtocolDetail screen shows categorized error reasons in an error alert box with a "Retry Extraction" button that calls the POST /protocols/{id}/retry endpoint and refreshes the protocol list.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Update Protocol type, add retry hook, and update status badges | b20ea8a | useProtocols.ts, ProtocolList.tsx |
| 2 | Add error reason display and retry button to ProtocolDetail | ce2ce04 | useProtocols.ts, ProtocolDetail.tsx |

## What Changed

### Updated Protocol Interface and Retry Hook (Task 1)

**apps/hitl-ui/src/hooks/useProtocols.ts:**
- Updated `Protocol` interface status type to include all 9 statuses:
  - `uploaded`, `extracting`, `extraction_failed`, `grounding`, `grounding_failed`, `pending_review`, `complete`, `dead_letter`, `archived`
- Added `error_reason: string | null` field to Protocol interface
- Created `useRetryProtocol()` mutation hook:
  - Calls `POST /protocols/${protocolId}/retry`
  - Invalidates protocol queries on success for automatic list refresh
  - Returns mutation state (isPending, isError, etc.) for UI feedback

**apps/hitl-ui/src/screens/ProtocolList.tsx:**
- Updated `STATUS_OPTIONS` array to include all new failure statuses
- Expanded `STATUS_COLORS` map with distinct colors:
  - `extraction_failed`: red (`bg-red-100 text-red-800`)
  - `grounding_failed`: orange (`bg-orange-100 text-orange-800`)
  - `dead_letter`: dark red (`bg-red-200 text-red-900`)
  - `archived`: gray (`bg-gray-100 text-gray-500`)
  - Kept legacy statuses (`extracted`, `reviewed`) for backward compatibility
- Added `STATUS_LABELS` map for human-readable display:
  - `extraction_failed` → "Extraction Failed"
  - `grounding_failed` → "Grounding Failed"
  - `pending_review` → "Pending Review"
  - `dead_letter` → "Dead Letter"
- Updated `StatusBadge` component to use `STATUS_LABELS[status]` instead of raw status value
- Updated filter chips to show human-readable labels (`STATUS_LABELS[opt]` instead of capitalized raw value)

### Error Display and Retry UI (Task 2)

**apps/hitl-ui/src/screens/ProtocolDetail.tsx:**
- Imported `useRetryProtocol` hook from useProtocols
- Added `STATUS_COLORS` and `STATUS_LABELS` maps matching ProtocolList for consistency
- Updated `StatusBadge` component to use human-readable labels
- Created `RetryButton` component:
  - Calls `retryMutation.mutate(protocolId)` on click
  - Shows loading spinner with "Retrying..." text while pending
  - Styled with red theme (`border-red-300 text-red-700 hover:bg-red-100`)
  - Disabled during mutation to prevent duplicate requests
- Added error alert section displayed for failed protocols:
  - Condition: `protocol.status === 'extraction_failed' || 'grounding_failed' || 'dead_letter'`
  - Shows categorized error title:
    - "Processing Failed (Retries Exhausted)" for dead_letter
    - "Extraction Failed" for extraction_failed
    - "Grounding Failed" for grounding_failed
  - Displays `protocol.error_reason` with fallback: "An unknown error occurred during processing."
  - Shows 7-day archival warning for dead_letter status: "This protocol will be archived after 7 days."
  - Includes `RetryButton` positioned in top-right corner of alert
- Added processing-in-progress banner for uploaded/extracting statuses:
  - Blue info box: "Processing in progress. This typically takes 2-5 minutes."
  - Positioned above error alerts and quality warnings

## Deviations from Plan

None - plan executed exactly as written. All verification checks passed.

## Verification Results

1. `npx tsc --noEmit` passes: PASSED
2. `npx biome check src/` passes: PASSED (auto-fixed formatting issues)
3. Protocol status type includes all 9 values + error_reason: PASSED
4. useRetryProtocol hook calls POST /protocols/{id}/retry: PASSED
5. ProtocolList shows distinct color badges for all failure statuses: PASSED
6. ProtocolDetail shows error reason alert for failed protocols: PASSED
7. Retry Extraction button calls mutation and refreshes queries: PASSED

## Success Criteria

- [x] Protocol interface has 9 status values and error_reason field
- [x] Status badges have distinct colors: red for extraction_failed, orange for grounding_failed, dark red for dead_letter
- [x] Human-readable labels shown instead of raw underscore values
- [x] useRetryProtocol mutation hook calls POST /protocols/{id}/retry
- [x] ProtocolDetail shows categorized error reason in error alert
- [x] "Retry Extraction" button appears on extraction_failed, grounding_failed, dead_letter protocols
- [x] Dead-letter protocols show 7-day archival warning
- [x] TypeScript compiles cleanly

## Technical Details

### Status Badge Color Coding

**Failure States (High Visibility):**
- `extraction_failed`: Red (`bg-red-100 text-red-800`) - Extraction pipeline failure
- `grounding_failed`: Orange (`bg-orange-100 text-orange-800`) - Grounding pipeline failure
- `dead_letter`: Dark Red (`bg-red-200 text-red-900`) - Max retries exhausted

**Processing States (Yellow/Blue):**
- `uploaded`: Blue (`bg-blue-100 text-blue-800`) - Awaiting extraction
- `extracting`: Yellow (`bg-yellow-100 text-yellow-800`) - Extraction in progress
- `grounding`: Cyan (`bg-cyan-100 text-cyan-800`) - Grounding in progress

**Success States (Green/Purple):**
- `pending_review`: Indigo (`bg-indigo-100 text-indigo-800`) - Awaiting human review
- `complete`: Green (`bg-green-100 text-green-800`) - Fully processed and approved

**Inactive States (Gray):**
- `archived`: Gray (`bg-gray-100 text-gray-500`) - Dead-letter protocol archived after 7 days

### Retry Button Behavior

**Component:** `RetryButton({ protocolId })`

**Visual States:**
- Default: "Retry Extraction" button with red outline
- Pending: Spinner icon + "Retrying..." text, button disabled

**Action:**
1. User clicks "Retry Extraction"
2. `retryMutation.mutate(protocolId)` calls POST /protocols/{id}/retry
3. Backend resets protocol.status to "uploaded" and clears error_reason
4. Backend creates new PROTOCOL_UPLOADED event to re-trigger pipeline
5. `onSuccess` callback invalidates protocol queries
6. React Query refetches protocol list and detail automatically
7. UI updates to show "Uploaded" or "Extracting" status

**Error Handling:**
- Mutation errors shown via toast/alert (not implemented in this plan)
- Button re-enables on error for user to retry again

### Error Alert Structure

```tsx
<div className="rounded-lg border border-red-200 bg-red-50 p-4 mb-6">
    <div className="flex items-start justify-between">
        <div>
            <h3 className="text-sm font-semibold text-red-800">
                [Categorized Error Title]
            </h3>
            <p className="mt-1 text-sm text-red-700">
                {protocol.error_reason ?? 'An unknown error occurred during processing.'}
            </p>
            {protocol.status === 'dead_letter' && (
                <p className="mt-1 text-xs text-red-600">
                    This protocol will be archived after 7 days.
                </p>
            )}
        </div>
        <RetryButton protocolId={protocol.id} />
    </div>
</div>
```

**Contextual Error Titles:**
- `extraction_failed` → "Extraction Failed"
- `grounding_failed` → "Grounding Failed"
- `dead_letter` → "Processing Failed (Retries Exhausted)"

**Error Reason Examples (from backend):**
- "PDF text quality too low" (extraction failure)
- "AI service unavailable" (extraction or grounding failure)
- "Maximum retries exceeded" (dead-letter)
- "UMLS API rate limit exceeded" (grounding failure)

### Human-Readable Labels

**STATUS_LABELS Map:**
```typescript
const STATUS_LABELS: Record<string, string> = {
    uploaded: 'Uploaded',
    extracting: 'Extracting',
    extraction_failed: 'Extraction Failed',
    grounding: 'Grounding',
    grounding_failed: 'Grounding Failed',
    pending_review: 'Pending Review',
    complete: 'Complete',
    dead_letter: 'Dead Letter',
    archived: 'Archived',
    extracted: 'Extracted',
    reviewed: 'Reviewed',
};
```

**Usage:**
- Status badges: `{STATUS_LABELS[status] ?? status}`
- Filter chips: `{opt === 'All' ? 'All' : (STATUS_LABELS[opt] ?? opt)}`
- Fallback to raw status value if label not defined (defensive)

## Key Decisions

1. **Human-readable labels instead of raw status values**
   - Implemented via `STATUS_LABELS` map shared between ProtocolList and ProtocolDetail
   - Improves UX: "Extraction Failed" is clearer than "extraction_failed"
   - Consistent with backend capitalization style (Phase 7 Plan 01 decision)
   - Alternative (rejected): Transform at render time with `.replace('_', ' ')` - less maintainable

2. **Retry button positioned in error alert**
   - Placed in top-right corner of error alert box for contextual action
   - User sees error message and action button together (no scrolling required)
   - Consistent with "alert with action" UI pattern (used in GitHub, Sentry, etc.)
   - Alternative (rejected): Separate action button below info grid - disconnected from error context

3. **Processing banner without circuit breaker detection**
   - Simple "Processing in progress. This typically takes 2-5 minutes." message
   - Backend handles circuit breaker detection and sets error_reason accordingly
   - Frontend shows specific error reason when protocol transitions to failed state
   - Alternative (rejected): Poll circuit breaker status from frontend - unnecessary complexity

4. **Biome auto-formatting applied**
   - Used `npx biome check --write` to fix formatting issues
   - Ensures consistent code style across project (multiline string formatting, function call layout)
   - Matches existing frontend codebase conventions
   - Required for CI/CD pipeline (pre-commit hooks)

## Self-Check: PASSED

**Modified files verified:**
- [FOUND] apps/hitl-ui/src/hooks/useProtocols.ts
- [FOUND] apps/hitl-ui/src/screens/ProtocolList.tsx
- [FOUND] apps/hitl-ui/src/screens/ProtocolDetail.tsx

**Commits verified:**
- [FOUND] b20ea8a: feat(07-04): update protocol status type, add retry hook, and status badges
- [FOUND] ce2ce04: feat(07-04): add error reason display and retry button to ProtocolDetail

**TypeScript compilation:**
- [PASSED] `npx tsc --noEmit` - no errors

**Biome linting:**
- [PASSED] `npx biome check src/` - no errors

## Next Steps

Plan 07-04 complete. Frontend now displays protocol failures with actionable retry UI.

**Integration with Phase 7 Plans:**
- 07-01: Backend protocol status enum and error_reason field (complete)
- 07-02: Circuit breakers and retry decorators for external services (partial - retry decorators pending)
- 07-03: Backend retry endpoint and error categorization (assumed complete based on plan dependencies)
- 07-04: Frontend failure status display and retry UI (complete)

**Recommendations for Phase 7 completion:**
- Complete 07-02 retry decorator application (pending todo from STATE.md)
- Add toast notifications for retry success/failure (nice-to-have UX improvement)
- Consider adding protocol status filter persistence to localStorage (user preference)
- Add "View Technical Details" collapsible section in error alert for debug metadata (admin feature)

**User Experience Flow:**
1. Researcher uploads protocol → sees "Uploaded" blue badge
2. Extraction starts → badge changes to "Extracting" yellow
3. Extraction fails → badge turns red "Extraction Failed", detail page shows error reason
4. Researcher clicks "Retry Extraction" → button shows spinner, protocol resets to "Uploaded"
5. Retry succeeds → protocol proceeds through pipeline to "Complete" green badge
6. Retry fails 3 times → protocol marked "Dead Letter" dark red, 7-day archival warning shown
