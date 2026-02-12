---
phase: 21-gemini-3-flash-upgrade
plan: 01
status: complete
---

## Summary

Updated all Gemini model references from `gemini-2.5-flash` to `gemini-3-flash-preview` across the extraction and grounding services. Also included the ChatVertexAI to ChatGoogleGenerativeAI migration that was pending from Phase 18.

## Files Modified

- `services/extraction-service/src/extraction_service/nodes/extract.py` — Default model updated to `gemini-3-flash-preview`
- `services/extraction-service/src/extraction_service/nodes/queue.py` — extraction_model default updated
- `services/extraction-service/scripts/verify_extraction.py` — Verification script default updated
- `services/grounding-service/src/grounding_service/nodes/extract_entities.py` — Default model updated
- `.env.example` — Added `GEMINI_MODEL_NAME=gemini-3-flash-preview`
- `.env` — Updated to `gemini-3-flash-preview` (not committed)

## Verification

- No remaining `gemini-2.5-flash` references in Python source files
- `.env.example` documents `GEMINI_MODEL_NAME=gemini-3-flash-preview`
- `uv run ruff check` passes on all core modified files
