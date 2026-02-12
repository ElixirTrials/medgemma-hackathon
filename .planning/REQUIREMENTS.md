# Requirements: v1.4 Structured Entity Display & Grounding Fixes

## Milestone Goal

Fix the broken UMLS/SNOMED grounding pipeline so entities get real CUI/SNOMED codes, make the extraction LLM populate numeric thresholds, and display all structured data (temporal constraints, thresholds, SNOMED/UMLS mappings) in the HITL UI.

## Investigation Findings (2026-02-12)

Ran 3 protocols through the pipeline (103 criteria, 266 entities). Found:

1. **UMLS/SNOMED grounding 100% failed** — 266/266 entities have null CUI, null SNOMED. All flagged `expert_review`. MCP `concept_linking` calls fail silently per-entity.
2. **`numeric_thresholds` never populated** — 0/103 criteria. Schema exists but Gemini returns empty lists. Criteria like "40-85 years old" and "WOMAC <1.5" should have structured thresholds.
3. **`temporal_constraint` not displayed** — 47/103 criteria have data but CriterionCard doesn't render it.
4. **No threshold/SNOMED UI** — Even when backend data arrives, no UI components render it.

## Requirements

### FE — Frontend Display (data exists, just not shown)

- **FE-01**: CriterionCard displays `temporal_constraint` when present (duration, relation, reference_point as human-readable text)
- **FE-02**: CriterionCard displays `numeric_thresholds` when present (value, comparator, unit rendered as e.g. ">=18 years", "<1.5 WOMAC")
- **FE-03**: EntityCard displays SNOMED badge and UMLS CUI link when data is populated (code already exists in EntityCard.tsx, verify it works once backend provides data)

### EXT — Extraction Structured Output

- **EXT-01**: Gemini extraction prompt includes few-shot examples for `numeric_thresholds` (age ranges, lab values, dosage limits)
- **EXT-02**: Re-extracted criteria for existing protocols have populated `numeric_thresholds` for criteria containing numeric values
- **EXT-03**: Extraction prompt includes few-shot examples for `conditions` (conditional dependencies)

### GRD — Grounding Pipeline Fix

- **GRD-01**: Diagnose why MCP `concept_linking` tool calls fail — determine if MCP server starts, if tool returns expected format, or if UMLS API key is missing
- **GRD-02**: Fix `ground_to_umls.py` so common medical terms (e.g., "acetaminophen", "osteoarthritis", "Heparin") successfully resolve to UMLS CUI
- **GRD-03**: Fix `map_to_snomed.py` so entities with UMLS CUI get SNOMED-CT codes mapped
- **GRD-04**: After fix, re-run grounding on existing protocols shows >50% entities grounded (non-zero CUI/SNOMED)

## Priority Order

1. FE-01 (temporal_constraint display) — quickest win, data already exists
2. GRD-01 through GRD-04 (grounding fix) — highest impact, currently 0% grounded
3. EXT-01 through EXT-03 (extraction improvement) — meaningful but lower impact
4. FE-02, FE-03 (threshold + SNOMED display) — frontend polish after backend produces data

### MGR — MedGemma Agentic Grounding

- **MGR-01**: MedGemma Vertex AI Model Garden endpoint integrated via `ModelGardenChatModel` (ported from gemma-hackathon) with `AgentConfig.from_env()` config pattern
- **MGR-02**: Agentic grounding loop where MedGemma extracts entities, suggests UMLS search terms, evaluates UMLS MCP results, and iteratively refines until satisfactory match (max 3 iterations)
- **MGR-03**: UMLS MCP `concept_search` used for both CUI linking and SNOMED mapping (replaces separate `map_to_snomed` direct API call)
- **MGR-04**: Grounding graph simplified: agentic grounding node replaces `extract_entities` + `ground_to_umls` + `map_to_snomed` (3 nodes → 1 agentic node + `validate_confidence`)

### G3F — Gemini 3 Flash Upgrade

- **G3F-01**: Criteria extraction uses `gemini-3-flash-preview` model (upgraded from `gemini-2.5-flash`)
- **G3F-02**: Extraction verified working with new model on existing protocol PDFs

## Priority Order

1. FE-01 (temporal_constraint display) — quickest win, data already exists
2. GRD-01 through GRD-04 (grounding fix) — highest impact, currently 0% grounded
3. EXT-01 through EXT-03 (extraction improvement) — meaningful but lower impact
4. FE-02, FE-03 (threshold + SNOMED display) — frontend polish after backend produces data
5. MGR-01 through MGR-04 (MedGemma agentic grounding) — proper MedGemma integration with iterative UMLS MCP
6. G3F-01, G3F-02 (Gemini 3 Flash) — latest model for extraction

## Success Criteria

- [ ] Temporal constraints visible on criteria cards for criteria that have them
- [ ] Numeric thresholds visible on criteria cards for criteria like age ranges and lab values
- [ ] At least some entities display SNOMED code + UMLS CUI in the Entity tab
- [ ] Grounding pipeline produces non-zero CUI/SNOMED for common medical terms
- [ ] MedGemma drives entity extraction via Vertex AI Model Garden endpoint
- [ ] Grounding loop iteratively refines UMLS matches using MedGemma reasoning
- [ ] Criteria extraction uses Gemini 3 Flash
