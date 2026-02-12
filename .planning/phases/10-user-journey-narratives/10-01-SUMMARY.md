---
phase: 10-user-journey-narratives
plan: 01
subsystem: documentation
tags: [user-journeys, sequence-diagrams, mkdocs]
dependency_graph:
  requires: [09-02]
  provides: [upload-extraction-journey, journey-navigation]
  affects: [mkdocs-navigation]
tech_stack:
  added: []
  patterns: [three-act-narrative, happy-path-focus, mermaid-sequence-diagrams]
key_files:
  created:
    - docs/journeys/upload-extraction.md
    - docs/journeys/grounding-review.md
  modified:
    - docs/journeys/index.md
    - mkdocs.yml
decisions:
  - title: Remove placeholder links to satisfy strict mode
    context: Plan specified placeholder links to non-existent component docs (api-service.md, extraction-service.md) with anchors, causing strict mode to fail
    decision: Replace markdown links with plain text references noting "coming in Phase 11"
    alternatives:
      - Keep placeholder links and accept strict mode failure (rejected - blocks verification)
      - Disable strict mode (rejected - loses validation benefits established in Phase 8)
      - Create stub component docs now (rejected - out of scope for this phase)
    rationale: Plain text preserves the error handling documentation roadmap while satisfying strict mode validation
metrics:
  duration_minutes: 10
  completed_date: 2026-02-12
---

# Phase 10 Plan 01: Upload & Extraction Journey Summary

**One-liner:** Created Upload & Extraction user journey narrative with 8-participant Mermaid sequence diagram showing signed URL upload, transactional outbox pattern, and async extraction via Gemini.

## What Was Built

### Upload & Extraction Journey Page (129 lines)

Created `docs/journeys/upload-extraction.md` with comprehensive journey narrative:

**User Story**: Clinical researcher uploading protocol PDF to get structured criteria (saves 2-4 hours vs manual extraction)

**Sequence Diagram** (8 participants):
- Researcher → HITL UI → API Service → GCS Bucket (signed URL upload)
- API Service → Outbox Processor → Extraction Service
- Extraction Service → Gemini API → PostgreSQL (criteria storage)
- Happy path explicitly noted with error handling references

**Three-Act Narrative**:
1. **Setup**: Client-side upload via GCS signed URLs (avoids server memory issues with 50+ MB PDFs)
2. **Action**: Transactional outbox pattern ensures at-least-once delivery, 4-stage extraction workflow (download → parse with pymupdf4llm → extract with Gemini → store)
3. **Resolution**: CriteriaExtracted event triggers grounding phase, status progression to pending_review

**Technical Details**:
- JSON schema validation for Gemini structured output
- Idempotency checks for retry scenarios
- Criteria fields: type, category, text, temporal constraints, numeric thresholds, confidence score

### Journey Navigation Structure

**Updated `docs/journeys/index.md`**:
- Journey overview table with Upload & Extraction and Grounding & HITL Review
- "How to Read These Journeys" structure guide (user story → runtime flow → narrative → error handling)
- Related documentation links (System Architecture, Data Models, HITL Flow Diagram)

**Created `docs/journeys/grounding-review.md` placeholder**:
- Status: placeholder (content coming in Phase 10 Plan 02)
- Satisfies strict mode requirement for all nav-linked files to exist

**Updated `mkdocs.yml`**:
- Added both journey pages to User Journeys nav section

## Must-Haves Verification

| Must-Have | Status | Evidence |
|-----------|--------|----------|
| PM can view Upload & Extraction sequence diagram | PASS | `docs/journeys/upload-extraction.md` contains sequenceDiagram with 8 participants (Researcher, UI, API, GCS, Outbox, Extract, Gemini, DB) |
| Upload & Extraction narrative explains user story and runtime behavior | PASS | Three-act structure with user story (Who/Goal/Why), runtime flow diagram, and narrative explanation (Setup/Action/Resolution) |
| Upload & Extraction diagram explicitly notes happy path and links to error handling | PASS | Opening note "UPLOAD & EXTRACTION JOURNEY (HAPPY PATH)", error handling section references component docs (Phase 11) and System Architecture |
| docs/journeys/upload-extraction.md exists with sequence diagram | PASS | 129-line file with sequenceDiagram block |
| docs/journeys/grounding-review.md placeholder exists | PASS | Created with status=placeholder |
| docs/journeys/index.md has links to both journeys | PASS | Table with links to upload-extraction.md and grounding-review.md |
| mkdocs.yml navigation includes both journey pages | PASS | User Journeys section has Upload & Extraction and Grounding & HITL Review entries |

**Overall: 7/7 must-haves PASS**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Issue] Removed placeholder links to non-existent component docs**
- **Found during:** Task 1 verification (mkdocs build --strict failing)
- **Issue:** Plan specified markdown links to `../components/api-service.md#pdf-quality`, `../components/extraction-service.md#error-handling`, etc. These docs don't exist (scheduled for Phase 11), causing strict mode to abort with warnings. Additionally, `../architecture/system-architecture.md#dead-letter-handling` anchor didn't exist.
- **Fix:** Replaced markdown links with plain text noting "component docs (coming in Phase 11)" for non-existent docs. For system-architecture.md, removed non-existent anchor and linked to page with note to see Production Hardening section.
- **Files modified:** `docs/journeys/upload-extraction.md`
- **Commit:** 4cb9989
- **Rationale:** Plan verification required `uv run mkdocs build --strict` to pass with zero errors (Task 2 line 224). Strict mode treats warnings as errors. Removing invalid links while preserving error handling roadmap in prose satisfies both the strict mode requirement and the documentation intent.

## Performance

| Metric | Value |
|--------|-------|
| Duration | 10 minutes |
| Tasks completed | 2/2 |
| Commits | 2 |
| Files created | 2 (upload-extraction.md, grounding-review.md) |
| Files modified | 2 (index.md, mkdocs.yml) |
| Strict mode | PASS (0 warnings, 0 errors) |

## Key Decisions

### 1. Remove placeholder links to satisfy strict mode
**Context:** Plan specified placeholder links to non-existent component docs (api-service.md, extraction-service.md) with anchors, causing strict mode to fail.

**Decision:** Replace markdown links with plain text references noting "coming in Phase 11".

**Alternatives:**
- Keep placeholder links and accept strict mode failure → Rejected (blocks Task 2 verification requirement)
- Disable strict mode → Rejected (loses validation benefits established in Phase 8)
- Create stub component docs now → Rejected (out of scope for this phase)

**Rationale:** Plain text preserves the error handling documentation roadmap while satisfying strict mode validation requirement.

## Architecture Patterns Used

### Pattern 1: Three-Act Narrative Structure
Applied storytelling principles to technical documentation:
- **Setup**: User goal and upload experience (why signed URLs matter)
- **Action**: System interactions with technical details (outbox pattern, extraction stages)
- **Resolution**: Outcome and next steps (link to grounding journey)

Borrowed from research finding: technical documentation is more accessible when structured as a story with context, not just process steps.

### Pattern 2: Mermaid Sequence Diagram with Consistent Styling
- Line breaks in participant names for readability (`Clinical<br/>Researcher`)
- Solid arrows (`->>`) for requests, dotted arrows (`-->>`) for responses
- `Note over` spanning participants for cross-cutting concerns
- Color consistency with existing `hitl-flow.md`: UI = light blue, API = green, agents = orange, data = yellow

### Pattern 3: Happy Path with Error Handling References
- Diagram focuses on mainline success flow
- Opening note explicitly states "HAPPY PATH"
- Error scenarios documented in prose with references to future component docs
- Avoids clutter from alt/else blocks in diagram

## Testing & Verification

**Automated Checks:**
```bash
# File existence
test -f docs/journeys/upload-extraction.md  # PASS
test -f docs/journeys/grounding-review.md   # PASS

# Content verification
grep -c "sequenceDiagram" docs/journeys/upload-extraction.md  # Returns 1
grep -c "HAPPY PATH" docs/journeys/upload-extraction.md       # Returns 1
grep -c "date_verified" docs/journeys/upload-extraction.md    # Returns 1
grep "participant.*as" docs/journeys/upload-extraction.md | wc -l  # Returns 8

# Navigation
grep "Upload & Extraction" mkdocs.yml             # PASS
grep "upload-extraction" docs/journeys/index.md   # PASS

# Strict mode
uv run mkdocs build --strict  # Exit 0, zero warnings
```

**Manual Verification:**
- Sequence diagram renders correctly in both light and dark mode (Mermaid handles theme automatically)
- Journey overview table displays both journeys
- Placeholder status displayed correctly for grounding-review.md

## Documentation Quality

**Strengths:**
- Concrete technical details (pymupdf4llm preserves tables, JSON schema validation)
- Explained design decisions (why signed URLs, why outbox pattern)
- Quantified user benefit (2-4 hours saved, ~5 minutes for 50-page protocol)
- Forward links to next journey maintain narrative continuity

**Improvements from plan:**
- Removed placeholder markdown links (strict mode compliance)
- Added more specificity on criteria fields and extraction workflow stages

## Dependencies

**Requires:**
- Phase 09-02 (Data Models): References Entity, CriteriaBatch, Protocol schemas
- Phase 08-02 (Docs validation): Relies on strict mode CI validation

**Provides:**
- Upload & Extraction journey documentation (consumed by PMs and engineers)
- Journey navigation structure (consumed by Phase 10 Plan 02)
- Pattern for future journey narratives (three-act structure, happy path focus)

**Affects:**
- Phase 10 Plan 02: Must follow same structure for Grounding & HITL Review journey
- Phase 11 (Component Deep Dives): Should link back to relevant journey sections

## Lessons Learned

### What Went Well
- Three-act narrative structure worked well for technical flow documentation
- Mermaid styling consistency with existing diagrams maintained visual coherence
- Creating placeholder for grounding-review.md upfront avoided navigation issues

### What Could Be Improved
- Plan should clarify strict mode expectations when placeholder links are specified
- Could add estimated read time to journey pages (e.g., "~5 min read")

### Recommendations for Next Plans
- Phase 10 Plan 02: Follow same three-act structure for Grounding & HITL Review
- Phase 11: Link component docs back to relevant journey sections (bidirectional navigation)
- Consider adding "When to read this journey" section (before implementing extraction? during debugging?)

## Self-Check: PASSED

**Created files exist:**
```bash
[ -f "docs/journeys/upload-extraction.md" ] && echo "FOUND: docs/journeys/upload-extraction.md" || echo "MISSING"
# FOUND: docs/journeys/upload-extraction.md

[ -f "docs/journeys/grounding-review.md" ] && echo "FOUND: docs/journeys/grounding-review.md" || echo "MISSING"
# FOUND: docs/journeys/grounding-review.md
```

**Commits exist:**
```bash
git log --oneline --all | grep -q "4cb9989" && echo "FOUND: 4cb9989" || echo "MISSING"
# FOUND: 4cb9989

git log --oneline --all | grep -q "00c83ba" && echo "FOUND: 00c83ba" || echo "MISSING"
# FOUND: 00c83ba
```

**Navigation verified:**
```bash
grep -q "Upload & Extraction" mkdocs.yml && echo "FOUND in mkdocs.yml" || echo "MISSING"
# FOUND in mkdocs.yml

grep -q "upload-extraction" docs/journeys/index.md && echo "FOUND in index.md" || echo "MISSING"
# FOUND in index.md
```

**Strict mode passes:**
```bash
uv run mkdocs build --strict >/dev/null 2>&1 && echo "PASS" || echo "FAIL"
# PASS
```

**All checks passed.**

---

**Phase 10 Plan 01 complete.** Upload & Extraction journey is now live with comprehensive narrative and sequence diagram. Ready for Phase 10 Plan 02 (Grounding & HITL Review journey).
