# Jinja2 Prompts Reference

This document lists all Jinja2 prompt templates in the project, where they are used, what each is for, and their full text.

---

## Summary

| Service / Library | Template | Purpose |
|-------------------|----------|---------|
| **Protocol Processor** | `grounding_system.jinja2` | System prompt for MedGemma grounding decision (evaluate candidates, select best code) |
| **Protocol Processor** | `grounding_evaluate.jinja2` | User prompt listing candidates for MedGemma to evaluate per entity |
| **Protocol Processor** | `grounding_reasoning.jinja2` | User prompt for MedGemma agentic reasoning loop (3 questions before retry) |
| **Shared (libs/shared)** | `placeholder_system.j2` | Placeholder stub; not used by services |

---

## Protocol Processor Service

Templates live in `services/protocol-processor-service/src/protocol_processor/prompts/`.

Used by the **unified 5-node LangGraph pipeline** for protocol extraction and terminology grounding.

### 1. `grounding_system.jinja2`

- **Path:** `services/protocol-processor-service/src/protocol_processor/prompts/grounding_system.jinja2`
- **Variables:** None (rendered with no arguments).
- **Used by:** `protocol_processor.tools.medgemma_decider.medgemma_decide()` — rendered once as the system message for MedGemma.
- **Goal:** Define the system role for MedGemma as a medical terminology grounding expert that selects the best code from TerminologyRouter candidates.

---

### 2. `grounding_evaluate.jinja2`

- **Path:** `services/protocol-processor-service/src/protocol_processor/prompts/grounding_evaluate.jinja2`
- **Variables:** `entity_text`, `entity_type`, `criterion_context`, `candidates` (list of `GroundingCandidate` objects).
- **Used by:** `protocol_processor.tools.medgemma_decider.medgemma_decide()` — rendered per entity as the user message for candidate evaluation.
- **Goal:** Provide MedGemma with entity context and all TerminologyRouter candidates to select the best terminology code.

---

### 3. `grounding_reasoning.jinja2`

- **Path:** `services/protocol-processor-service/src/protocol_processor/prompts/grounding_reasoning.jinja2`
- **Variables:** `entity_text`, `entity_type`, `criterion_context`, `previous_query`.
- **Used by:** `protocol_processor.tools.medgemma_decider.agentic_reasoning_loop()` — rendered when initial grounding returns zero candidates or low confidence; asks 3 questions before retry.
- **Goal:** MedGemma agentic reasoning loop: (1) Is this a valid medical criterion? (2) Is this a derived entity mapping to a standard concept? (3) Can the search term be rephrased?

---

## Shared Library (Placeholder)

### 4. `placeholder_system.j2`

- **Path:** `libs/shared/src/shared/templates/placeholder_system.j2`
- **Variables:** Any passed at render time (template body does not use them).
- **Used by:** Nothing in the codebase. Stub for the shared-templates convention; actual prompts live in the services.
- **Goal:** Placeholder system prompt for the shared templates directory.

**Full template:**

```jinja2
{# Placeholder system prompt template. Replace with real templates; agents pass prompt_vars. #}
You are a helpful assistant.
```

---

## Rendering

- **Protocol processor grounding:** `protocol_processor.tools.medgemma_decider._render_template(template_name, **kwargs)` — Jinja2 `Environment` with `FileSystemLoader(protocol_processor/prompts)`; system template once per call, evaluate/reasoning templates once per entity.
