# MedGemma Integration Guide

This document maps where and how MedGemma 4B-IT (`google/medgemma-4b-it`) is used throughout the GemmaCrit codebase. It serves as a quick reference for understanding the HAI-DEF model integration.

## Two-Model Architecture

GemmaCrit uses a two-model architecture where each model plays a distinct role:

| Model | Role | Used For |
|-------|------|----------|
| **MedGemma 4B-IT** | Medical reasoning agent | Evaluating terminology candidates, selecting best matches, agentic retry reasoning |
| **Gemini 2.5 Flash** | Structured output engine | PDF extraction, structuring MedGemma's free-form output into Pydantic models |

MedGemma produces free-form medical reasoning text. Gemini then parses this into structured `GroundingDecision` or `AgenticReasoningResult` objects. This division leverages MedGemma's biomedical domain knowledge while using Gemini's reliable structured output capabilities.

## Code Map

### Model Loading & Configuration

**`libs/inference/src/inference/config.py`** &mdash; `AgentConfig`
- Defines `model_path` (default: `google/medgemma-4b-it`), `backend` (`vertex` | `local`), `quantization` (`4bit` | `8bit` | `none`)
- `AgentConfig.from_env()` reads `MODEL_BACKEND`, `MEDGEMMA_MODEL_PATH`, `MEDGEMMA_QUANTIZATION`, `GCP_PROJECT_ID`, etc.

**`libs/inference/src/inference/model_garden.py`** &mdash; Model loading factory
- `create_model_loader(config)` &mdash; Entry point that returns a lazy model loader callable
- `ModelGardenChatModel` &mdash; LangChain `BaseChatModel` wrapper for Vertex AI Model Garden endpoints
- `LocalMedGemmaChatModel` &mdash; LangChain `BaseChatModel` wrapper for local GPU loading with HuggingFace transformers + bitsandbytes quantization
- `_build_gemma_prompt()` &mdash; Formats messages using Gemma chat template (`<start_of_turn>`)
- Both backends expose the same LangChain interface, making the pipeline backend-agnostic

### MedGemma Decision Logic

**`services/protocol-processor-service/src/protocol_processor/tools/medgemma_decider.py`**

This is the core MedGemma integration point:

- **`medgemma_decide(entity, candidates, criterion_context)`** &mdash; Uses MedGemma to evaluate terminology candidates and select the best match. Returns `EntityGroundingResult` with selected code, confidence (0.0-1.0), and reasoning.

- **`agentic_reasoning_loop(entity, criterion_context, router, attempt)`** &mdash; When grounding confidence is low (< 0.5), asks MedGemma three reasoning questions:
  1. Is this a valid medical criterion?
  2. Is this a derived entity mapping to a standard concept?
  3. Can this entity be rephrased for better terminology search?

- **`_structure_decision_with_gemini(raw_text)`** &mdash; Takes MedGemma's free-form reasoning output and structures it using Gemini's `with_structured_output()` into a `GroundingDecision` Pydantic model.

- **`_structure_reasoning_with_gemini(raw_text)`** &mdash; Structures MedGemma's reasoning output into `AgenticReasoningResult`. Gemini can also contribute its own reformulation via `gemini_suggestion`.

### Agentic Retry in the Pipeline

**`services/protocol-processor-service/src/protocol_processor/nodes/ground.py`**

- **`_ground_entity_with_retry(entity, router, criterion_text)`** &mdash; Orchestrates the full grounding flow:
  1. Route entity through TerminologyRouter to get candidates
  2. Pass candidates to `medgemma_decide()` for best-match selection
  3. If confidence < 0.5 and attempts remain, call `agentic_reasoning_loop()`
  4. Retry with reformulated query (up to 3 total attempts)
  5. Route to `expert_review` if all attempts exhausted

- **`_ground_entity_parallel()`** &mdash; Runs dual grounding (TerminologyRouter + OMOP mapper) in parallel, then reconciles results

- **`ground_node(state)`** &mdash; LangGraph node that processes all entities with semaphore-controlled concurrency (4 concurrent), includes MedGemma warmup

### Prompts

**`services/protocol-processor-service/src/protocol_processor/prompts/`**

- `grounding_system.jinja2` &mdash; System prompt establishing MedGemma's role as a medical terminology expert
- `grounding_evaluate.jinja2` &mdash; Prompt for candidate evaluation (used by `medgemma_decide`)
- `grounding_reasoning.jinja2` &mdash; Prompt for the 3-question agentic reasoning loop

### Audit Trail

Every MedGemma decision is logged to the `AuditLog` database table via `_log_grounding_audit()` in `ground.py`. Logged details include:
- Entity text, type, and criterion context
- All candidates considered (with source API, code, term, and score)
- Selected code, system, preferred term, confidence, and reasoning
- OMOP concept ID and reconciliation status

## Why MedGemma

1. **Biomedical domain knowledge** &mdash; MedGemma is trained on biomedical data and understands medical terminology, drug names, condition hierarchies, and lab values that general-purpose models often misinterpret.

2. **Open-weight privacy** &mdash; Clinical trial protocols may contain sensitive information. MedGemma's open weights enable local deployment, keeping data on-premises.

3. **Local deployment capability** &mdash; The 4B parameter model fits on a single GPU with 4-bit quantization (8 GB VRAM), enabling edge deployment without cloud dependencies.

4. **Medical reasoning quality** &mdash; MedGemma's domain-specific training produces better reasoning about whether entities are valid medical criteria, how derived concepts map to standard terminologies, and how to rephrase queries for better search results.
