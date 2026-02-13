---
phase: quick-3
plan: 01
subsystem: extraction-service
tags: [gemini, file-api, pdf, developer-api]
dependency_graph:
  requires: []
  provides: [gemini-file-api-extraction]
  affects: [extraction-service, verify-extraction-script]
tech_stack:
  added: [google-genai-sdk]
  removed: [langchain-google-genai, base64-pdf-encoding]
  patterns: [file-api-upload, temp-file-cleanup, structured-output]
key_files:
  created: []
  modified:
    - services/extraction-service/src/extraction_service/nodes/extract.py
    - services/extraction-service/scripts/verify_extraction.py
    - .env.example
decisions:
  - Use google.genai.Client Developer API instead of Vertex AI for simpler PDF handling
  - File API upload eliminates 20MB base64 size limit
  - Temp file pattern for File API upload with cleanup in finally blocks
  - Preserve retry decorator and circuit breaker resilience patterns
metrics:
  duration_minutes: 1
  tasks_completed: 2
  files_modified: 3
  commits: 2
  completed_at: 2026-02-13
---

# Phase quick-3 Plan 01: Switch PDF Extraction to Gemini File API Summary

**One-liner:** PDF extraction now uses google.genai.Client with File API upload, eliminating base64 size limits and simplifying the integration.

## What Was Built

Migrated the extraction service from LangChain + Vertex AI + base64 inline data to google.genai.Client + File API for PDF handling.

### Task 1: Rewrite extract.py to use google.genai.Client + File API
**Status:** Complete
**Commit:** 9923b7c

Replaced the entire LangChain-based extraction flow with the Google GenAI SDK:

**Removed:**
- `base64` encoding and size warnings
- `langchain_core.messages` (SystemMessage, HumanMessage)
- `langchain_google_genai.ChatGoogleGenerativeAI`
- Vertex AI configuration (project, location params)
- 20MB base64 size limit concerns

**Added:**
- `google.genai.Client` instantiation with GOOGLE_API_KEY
- `tempfile.NamedTemporaryFile` for temp PDF storage
- `client.files.upload()` for File API upload
- `client.aio.models.generate_content()` with structured output
- Cleanup logic in finally blocks (temp file + uploaded file)

**Preserved:**
- `_truncate()` and `_format_validation_error()` helper functions
- `render_prompts()` from inference.factory
- `@gemini_breaker` circuit breaker
- `@retry` decorator with exponential backoff
- `ExtractionResult` Pydantic schema via `response_schema` parameter

### Task 2: Update verify_extraction.py and .env.example
**Status:** Complete
**Commit:** d65042f

Updated the verification script and environment documentation:

**verify_extraction.py:**
- Replaced LangChain imports with `google.genai` and `google.genai.types`
- Added temp file creation and File API upload
- Mirrored extract.py's File API pattern
- Added cleanup for temp file and uploaded file in finally block
- Preserved all analysis and reporting logic

**.env.example:**
- Added `GOOGLE_API_KEY` with clear documentation
- Included link to https://aistudio.google.com/apikey for key generation
- Placed after GEMINI_MODEL_NAME for logical grouping

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

All verification checks passed:

1. No langchain imports in extract.py: **PASSED**
2. File API upload present: **PASSED** (`client.files.upload(file=tmp_path)`)
3. Structured output configured: **PASSED** (`response_schema=ExtractionResult`)
4. GOOGLE_API_KEY documented in .env.example: **PASSED**
5. genai.Client instantiation present: **PASSED**

## Key Technical Decisions

### 1. File API Upload Pattern
**Decision:** Use temp file + synchronous upload + async generate_content
**Rationale:** File API requires a file path (not bytes), so temp file is necessary. Synchronous upload is acceptable since it's a single blocking call before async generation.

### 2. Cleanup Strategy
**Decision:** Separate try/except blocks in finally for temp file and uploaded file cleanup
**Rationale:** Ensures both cleanups are attempted even if one fails, preventing cleanup errors from masking the real exception.

### 3. Developer API vs Vertex AI
**Decision:** Switch to Developer API (google.genai.Client)
**Rationale:** Simpler authentication (API key vs service account), File API support is native, and eliminates project/location configuration complexity.

### 4. Response Parsing Strategy
**Decision:** Use `response.parsed` with fallback to `model_validate_json(response.text)`
**Rationale:** SDK returns Pydantic model directly when `response_schema` is a Pydantic class, but fallback provides robustness if SDK behavior changes.

## Impact

### Benefits
- **Removes 20MB size limit:** File API handles large PDFs without base64 encoding overhead
- **Simpler auth:** GOOGLE_API_KEY instead of GCP service account + project/location config
- **Less code:** 101 insertions vs 49 deletions in extract.py (net +52 lines but more readable)
- **Native SDK:** Direct use of google.genai instead of LangChain wrapper layer

### Breaking Changes
- **New env var required:** Must set GOOGLE_API_KEY (documented in .env.example)
- **No longer uses Vertex AI:** Vertex AI specific config removed (project, location, vertexai=True)

### Files Modified
- `services/extraction-service/src/extraction_service/nodes/extract.py` (complete rewrite)
- `services/extraction-service/scripts/verify_extraction.py` (matched extract.py pattern)
- `.env.example` (added GOOGLE_API_KEY documentation)

## Self-Check: PASSED

**Created files:** None (all files were modifications)

**Modified files:**
- FOUND: services/extraction-service/src/extraction_service/nodes/extract.py
- FOUND: services/extraction-service/scripts/verify_extraction.py
- FOUND: .env.example

**Commits:**
- FOUND: 9923b7c (Task 1: switch extract.py to google.genai.Client with File API)
- FOUND: d65042f (Task 2: update verify_extraction.py and .env.example for File API)

All claims verified. All files exist and contain expected changes.
