# Phase 32: Entity Model, Ground Node & Multi-Code Display - Context

**Gathered:** 2026-02-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Extend Entity model for multi-terminology codes (RxNorm, ICD-10, LOINC, HPO), implement real ground node with terminology routing, add pipeline error handling with retry from failed node, display color-coded multi-code badges in UI with per-system autocomplete editing.

</domain>

<decisions>
## Implementation Decisions

### Multi-code display
- Goal: one definitive grounding code per terminology system per entity (not synonym lists) — enables inner joins on structured patient data
- Show ALL resolved codes per entity (RxNorm + UMLS CUI + SNOMED + ICD-10 + LOINC + HPO if resolved)
- Color-coded badges by system: RxNorm=blue, ICD-10=orange, SNOMED=green, LOINC=purple, HPO=teal (exact colors at Claude's discretion)
- All codes are user-modifiable with per-system autocomplete search (like UMLS autocomplete but functional and low-latency for each terminology system)
- Current UMLS autocomplete doesn't work correctly — this phase should fix it along with adding other system autocompletes

### Error recovery UX
- Red "Failed" badge with specific error reason (e.g., "Grounding failed: UMLS API timeout")
- Retry from failed node only (resume from last LangGraph checkpoint) — not full pipeline restart
- Simple processing spinner only (no real-time node progress)

### Entity extraction approach
- Gemini produces fully structured results using native structured output (response_schema with Pydantic models) — guaranteed valid JSON
- MedGemma serves as medical expert — consulted for medical domain knowledge
- No separate research spike needed — implement this approach, review decision after it works
- Can revisit approach once everything is implemented and running

### Migration & backwards compatibility
- Clean migration — no backwards compatibility concerns (still in development, no production data)
- Drop and recreate database schema (fresh from models, no Alembic migration needed)
- New multi-code columns added directly to Entity model

### Claude's Discretion
- Exact badge color assignments per terminology system
- Autocomplete debounce and minimum character settings per system
- How the retry button integrates with existing protocol detail page

</decisions>

<specifics>
## Specific Ideas

- Autocomplete must actually work with low latency — the current UMLS autocomplete is broken
- One code per system per entity — not a list of synonyms. The system should pick the best match.
- All codes modifiable by user — reviewer can correct any grounding code via autocomplete

</specifics>

<deferred>
## Deferred Ideas

- Real-time pipeline progress display (SSE/WebSocket) — too complex for now, spinner is sufficient
- Re-process entire pipeline option (alongside retry-from-failure) — add if users request it

</deferred>

---

*Phase: 32-entity-model-ground-node-multi-code-display*
*Context gathered: 2026-02-16*
