# Quick Task 2: Fix MedGemma Entity Extraction to Split Compound Criteria Summary

**One-liner:** Prompt-level fix to decompose compound criteria like "liver abnormality (e.g. cirrhosis, transplant)" into atomic entities, each grounding to exactly one UMLS CUI.

## Plan Reference

- **Phase:** quick-2
- **Plan:** 01
- **Type:** execute
- **Status:** Complete

## Objective

Fix MedGemma entity extraction prompts so compound criteria are decomposed into individual atomic entities, each grounding to exactly one UMLS CUI / SNOMED code. Previously, MedGemma extracted overly broad entity text like "No known clinically significant liver abnormality (e.g. cirrhosis, transplant, etc.)" as a single entity, which failed UMLS grounding because no single CUI maps to an entire compound phrase.

## Tasks Completed

| Task | Description | Commit | Duration |
|------|-------------|--------|----------|
| 1 | Add compound entity decomposition rules to agentic system prompt | a9acfd1 | ~1 min |
| 2 | Reinforce atomic extraction in the agentic extract prompt | 0bfacc6 | ~1 min |

## Key Changes

### 1. Entity Decomposition Section (agentic_system.jinja2)

Added new section between "Entity Types" and "JSON Output Schema" with:
- **Atomic entity rule**: Each extracted entity MUST map to exactly one UMLS CUI
- **Compound criteria splitting**: Extract EACH specific condition as separate entity
- **Negative/qualifier handling**: For compound exclusion criteria, extract parent + children
- **search_term optimization**: Use standard UMLS-searchable term for atomic concept
- **Before/after example**: Shows bad compound extraction vs. good decomposition

### 2. Updated Rules (agentic_system.jinja2)

- **Rule 3**: Changed from "standard medical term" to "standard medical term for a SINGLE concept" with explicit "Never use compound phrase" instruction
- **Rule 8** (new): "NEVER extract an entire criterion clause or long parenthetical phrase as a single entity"

### 3. Compound Decomposition Example (agentic_system.jinja2)

Added Example 1b demonstrating decomposition of:
```
"No known clinically significant liver abnormality (e.g. cirrhosis, transplant, etc.)"
```

Into 3 atomic entities:
1. "liver abnormality" (search_term: "liver disease")
2. "cirrhosis" (search_term: "hepatic cirrhosis")
3. "transplant" (search_term: "liver transplantation")

### 4. Extract Prompt Reinforcement (agentic_extract.jinja2)

Added IMPORTANT paragraph before entity field list:
```
IMPORTANT: Each entity must be an atomic medical concept that maps to exactly one UMLS CUI.
If a criterion contains compound phrases, parenthetical examples (e.g., "such as X, Y, Z"),
or comma-separated conditions, extract EACH specific condition as a separate entity.
Do NOT extract entire clauses or long phrases as a single entity.
```

### 5. Non-Agentic Path Coverage (system.jinja2)

Updated Rule 3 from:
```
For compound entities, extract the most specific term (e.g., "Type 2 diabetes mellitus" not just "diabetes")
```

To:
```
For compound criteria with lists of conditions (e.g., parenthetical examples, "such as" clauses),
extract EACH specific condition as a separate entity. Each entity must be an atomic medical concept
mappable to one UMLS CUI. For example, "liver abnormality (e.g. cirrhosis, transplant)" should
produce 3 entities: "liver abnormality", "cirrhosis", "transplant" -- NOT one entity with the full text.
```

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

**Template Syntax Check:** All three templates (agentic_system.jinja2, agentic_extract.jinja2, system.jinja2) validated successfully with Jinja2 Template parser.

**Instruction Coverage Check:** Decomposition instructions confirmed in THREE locations:
1. agentic_system.jinja2: Entity Decomposition section + Rules 3, 8 + Example 1b
2. agentic_extract.jinja2: IMPORTANT reinforcement paragraph
3. system.jinja2: Updated Rule 3 for non-agentic (Gemini) extraction path

**No code changes needed:** The `medgemma_ground.py` agentic loop already handles multiple entities per criterion correctly via iteration over `action.entities`.

## Files Modified

| File | Changes |
|------|---------|
| `services/grounding-service/src/grounding_service/prompts/agentic_system.jinja2` | Added Entity Decomposition section, updated Rule 3, added Rule 8, added Example 1b |
| `services/grounding-service/src/grounding_service/prompts/agentic_extract.jinja2` | Added atomic extraction reinforcement paragraph |
| `services/grounding-service/src/grounding_service/prompts/system.jinja2` | Updated Rule 3 for compound criteria decomposition |

## Success Criteria Met

- [x] All three prompt templates updated with compound entity decomposition instructions
- [x] Instructions include concrete before/after examples showing expected behavior
- [x] Both agentic (MedGemma) and non-agentic (Gemini) extraction paths covered
- [x] No Python code changes required (the loop logic already handles N entities per criterion)
- [x] Jinja2 templates remain syntactically valid

## Commits

1. `a9acfd1` - feat(quick-2): add compound entity decomposition rules to prompts
2. `0bfacc6` - feat(quick-2): reinforce atomic extraction in agentic extract prompt

## Metrics

- **Tasks completed:** 2/2
- **Duration:** 2 minutes
- **Files modified:** 3
- **Commits:** 2
- **Completed:** 2026-02-13

## Self-Check: PASSED

**Created files verification:**
```
FOUND: services/grounding-service/src/grounding_service/prompts/agentic_system.jinja2
FOUND: services/grounding-service/src/grounding_service/prompts/agentic_extract.jinja2
FOUND: services/grounding-service/src/grounding_service/prompts/system.jinja2
```

**Commits verification:**
```
FOUND: a9acfd1
FOUND: 0bfacc6
```

All verification checks passed.
