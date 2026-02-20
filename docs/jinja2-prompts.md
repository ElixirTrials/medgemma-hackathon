# Jinja2 Prompts Reference

This document lists the current Jinja2 templates in the repository and where they are used.

Last verified against code and template files: 2026-02-20.

---

## Current Template Inventory

| Area | Template | Purpose |
|---|---|---|
| Protocol Processor | `system.jinja2` | System prompt for structured criteria extraction from protocol PDFs |
| Protocol Processor | `user.jinja2` | User prompt for extraction request, including protocol title context |
| Protocol Processor | `entity_decompose.jinja2` | Prompt to split a criterion sentence into discrete groundable entities |
| Protocol Processor | `grounding_system.jinja2` | System prompt for MedGemma terminology selection |
| Protocol Processor | `grounding_evaluate.jinja2` | User prompt with terminology candidates for entity-level grounding |
| Protocol Processor | `grounding_reasoning.jinja2` | User prompt for retry-time agentic reasoning (skip/derive/rephrase) |
| Shared (`libs/shared`) | `placeholder_system.j2` | Placeholder template; currently not used by runtime services |

---

## Protocol Processor Prompts

All protocol-processor templates live in `services/protocol-processor-service/src/protocol_processor/prompts/`.

### `system.jinja2`
- **Used by:** `protocol_processor.tools.gemini_extractor.extract_criteria_structured()`
- **Render path:** `inference.factory.render_prompts(...)` with `system_template="system.jinja2"`
- **Variables:** none
- **Role:** Defines extraction rules (criteria splitting, numeric thresholds, assertion status, page number guidance)

### `user.jinja2`
- **Used by:** `protocol_processor.tools.gemini_extractor.extract_criteria_structured()`
- **Render path:** `inference.factory.render_prompts(...)` with `user_template="user.jinja2"`
- **Variables:** `title`
- **Role:** Provides protocol-specific extraction instructions for the attached PDF

### `entity_decompose.jinja2`
- **Used by:** `protocol_processor.tools.entity_decomposer.decompose_entities_from_criterion()`
- **Render path:** `protocol_processor.tools.entity_decomposer._render_decompose_prompt()`
- **Variables:** `criterion_text`, `category`
- **Role:** Extracts one or more discrete medical entities from a criterion for downstream terminology routing

### `grounding_system.jinja2`
- **Used by:** `protocol_processor.tools.medgemma_decider.medgemma_decide()`, `protocol_processor.tools.medgemma_decider.agentic_reasoning_loop()`
- **Render path:** `protocol_processor.tools.medgemma_decider._render_template()`
- **Variables:** none
- **Role:** Sets MedGemma behavior for terminology grounding decisions

### `grounding_evaluate.jinja2`
- **Used by:** `protocol_processor.tools.medgemma_decider.medgemma_decide()`
- **Render path:** `protocol_processor.tools.medgemma_decider._render_template()`
- **Variables:** `entity_text`, `entity_type`, `criterion_context`, `candidates`
- **Role:** Presents candidate concepts and asks MedGemma to select best match with confidence/reasoning

### `grounding_reasoning.jinja2`
- **Used by:** `protocol_processor.tools.medgemma_decider.agentic_reasoning_loop()`
- **Render path:** `protocol_processor.tools.medgemma_decider._render_template()`
- **Variables:** `entity_text`, `entity_type`, `criterion_context`, `previous_query`, `attempt`
- **Role:** Runs 3-question retry reasoning (valid criterion, derived concept, better query phrase)

---

## Shared Template

### `placeholder_system.j2`
- **Path:** `libs/shared/src/shared/templates/placeholder_system.j2`
- **Used by:** currently unused (placeholder only)
- **Variables:** accepts prompt vars but template body does not consume them
