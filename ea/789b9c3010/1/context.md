# Session Context

## User Prompts

### Prompt 1

Implement the following plan:

# Phase 3: Value and Unit Normalization

## Context

Phase 2 (Expression Trees) is complete and verified (119/119 tests passing). The `atomic_criteria` table stores `unit_text` as raw free-text strings (e.g., "mg/dL", "%", "years") but has no `unit_concept_id` column. Per gap_closure_plan.md Phase 3 (Gap 7), we need a static UCUM lookup mapping ~50 common clinical trial units to OMOP `unit_concept_id` values, plus optional categorical value normalization ("positive...

### Prompt 2

Can you run a few inclusion/exclusion criteria through the backend and see that it properly catches the entities, relations, values and units? Check that everything is working.

### Prompt 3

I think we should add units and unit_concept_ids for booleans (positive/negative) and some kind of unit concept for ECOG. For example in SNOMED there is a concept for each level. ECOG observation is bound to LOINC 89247-1 for ECOG performance. We should reference both LOINC answer list, SNOMED CT ECOG grade concepts somewhere. Consider schema's and where it's appropriate to map this.

