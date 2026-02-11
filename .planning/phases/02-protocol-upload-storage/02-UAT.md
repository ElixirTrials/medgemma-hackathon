---
status: complete
phase: 02-protocol-upload-storage
source: 02-01-SUMMARY.md, 02-02-SUMMARY.md
started: 2026-02-11T10:00:00Z
updated: 2026-02-11T10:15:00Z
method: playwright-automated
---

## Current Test

[testing complete]

## Tests

### 1. Navigate to Protocols from Dashboard
expected: Open http://localhost:3000/demo-app/ in browser. Dashboard shows a "Protocols" card. Clicking "View Protocols" navigates to /demo-app/protocols.
result: pass

### 2. Empty Protocol List
expected: The /demo-app/protocols page shows an empty state message (no protocols yet) and an "Upload Protocol" button.
result: issue
reported: "Empty state message is generic ('No protocols uploaded yet') regardless of which status filter is active. Filtering by 'Extracted' shows 'No protocols uploaded yet' instead of a filter-aware message like 'No extracted protocols found'."
severity: minor

### 3. Open Upload Dialog
expected: Clicking the "Upload Protocol" button opens a dialog with a drag-and-drop zone for PDF files.
result: pass

### 4. Upload Rejects Non-PDF
expected: Attempting to upload a non-PDF file (e.g., a .txt or .png) shows a validation error and does not proceed with the upload.
result: pass

### 5. Upload a PDF Successfully
expected: Selecting or dragging a valid PDF file triggers the upload flow. A loading state is shown during upload, and upon completion the dialog closes (or shows success).
result: pass

### 6. Protocol List Shows Uploaded Protocol
expected: After upload, the protocol appears in the list with a status badge (e.g., "uploaded"), a quality score indicator (progress bar with percentage), and a relative time (e.g., "just now").
result: issue
reported: "Protocol appears in list with status badge and relative time, but quality score always shows '--' and pages always shows '--'. The 3-step upload flow (POST /upload -> PUT /mock-upload -> POST /confirm-upload) sends empty body to confirm-upload, so quality scoring is never triggered. All protocols have null quality_score and null page_count in the API response."
severity: major

### 7. Protocol Detail Page
expected: Clicking a protocol row navigates to /demo-app/protocols/:id showing quality metrics (score, text extractability, page count, encoding type), file URI with copy button, and a back navigation link.
result: issue
reported: "Detail page loads correctly with file URI, copy button, back navigation, and status badge. However: (1) All quality fields show 'Not available' because quality scoring never runs in the browser upload flow. (2) Minor inconsistency: Encoding Type shows 'Not Available' (capital A) due to CSS capitalize class on the fallback text, while all other fields show 'Not available' (lowercase a)."
severity: major

## Summary

total: 7
passed: 4
issues: 3
pending: 0
skipped: 0

## Gaps

- truth: "Empty state message should reflect the active status filter"
  status: failed
  reason: "User reported: Empty state message is generic ('No protocols uploaded yet') regardless of which status filter is active. Filtering by 'Extracted' shows 'No protocols uploaded yet' instead of a filter-aware message."
  severity: minor
  test: 2
  root_cause: "ProtocolList.tsx line 141 uses hardcoded empty state message regardless of statusFilter state"
  artifacts:
    - path: "apps/hitl-ui/src/screens/ProtocolList.tsx"
      issue: "Line 141: hardcoded 'No protocols uploaded yet' message ignores active filter"
  missing:
    - "Conditional empty state message based on statusFilter value"
  debug_session: ""

- truth: "Quality score and page count should be populated after upload in local dev"
  status: failed
  reason: "User reported: Quality score always shows '--' and pages always shows '--'. The browser upload flow sends empty body to confirm-upload, so quality scoring is never triggered."
  severity: major
  test: 6
  root_cause: "useProtocols.ts line 101-104 sends empty JSON body to confirm-upload. The backend only runs quality scoring when pdf_bytes_base64 is provided (protocols.py line 183). In the browser flow, the file is uploaded directly to GCS/mock via PUT, and the confirm step doesn't include the file bytes."
  artifacts:
    - path: "apps/hitl-ui/src/hooks/useProtocols.ts"
      issue: "Line 100-104: confirm-upload called with empty body, no PDF bytes sent"
    - path: "services/api-service/src/api_service/protocols.py"
      issue: "Line 183: quality scoring only runs when pdf_bytes_base64 is provided"
  missing:
    - "Frontend should read file as base64 and include in confirm-upload request, OR backend should read from local storage/GCS to compute quality"
  debug_session: ""

- truth: "Encoding Type fallback text should be consistent with other fields"
  status: failed
  reason: "User reported: Encoding Type shows 'Not Available' (capital A) due to CSS capitalize class, while other fields show 'Not available' (lowercase a)"
  severity: cosmetic
  test: 7
  root_cause: "ProtocolDetail.tsx line 189 wraps encoding type value in <span className='capitalize'>, which also affects the 'Not available' fallback text"
  artifacts:
    - path: "apps/hitl-ui/src/screens/ProtocolDetail.tsx"
      issue: "Line 189: CSS capitalize class applied to fallback text"
  missing:
    - "Only apply capitalize when encodingType has a value, not on the fallback"
  debug_session: ""
