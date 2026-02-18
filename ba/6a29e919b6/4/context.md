# Session Context

## User Prompts

### Prompt 1

Implement the following plan:

# Plan: Fast, Opt-In E2E Pipeline Test

## Context

The current E2E tests (`test_pipeline_full.py`) process the full protocol — 20 criteria, ~46 entities, ~15 min wall clock. This makes them impractical: they time out at 180s and never pass. We need a focused E2E test that validates the full pipeline path (upload → extract → parse → ground → persist) but with a small enough scope to complete in ~1-2 minutes.

The test must be opt-in only — it should nev...

