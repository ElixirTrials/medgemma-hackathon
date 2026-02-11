# Phase 3: Criteria Extraction Workflow - Research

**Researched:** 2026-02-11
**Domain:** LLM-based structured data extraction from clinical trial PDFs, LangGraph workflow orchestration, Gemini structured output
**Confidence:** MEDIUM-HIGH

## Summary

Phase 3 transforms agent-a-service from a placeholder into a fully operational LangGraph workflow that: (1) listens for `ProtocolUploaded` events via the outbox processor, (2) fetches and parses protocol PDFs using `pymupdf4llm`, (3) extracts structured inclusion/exclusion criteria using Gemini's structured output via `ChatVertexAI.with_structured_output()`, and (4) persists `CriteriaBatch` + `Criteria` records and publishes a `CriteriaExtracted` event.

The codebase already provides strong foundations: SQLModel domain models (`Protocol`, `CriteriaBatch`, `Criteria`) are defined in `libs/shared/src/shared/models.py`, the outbox pattern with `persist_with_outbox` exists in `libs/events-py/src/events_py/outbox.py`, the inference factory in `libs/inference/src/inference/factory.py` has `create_structured_extractor` with retry logic, and agent-a-service has a skeleton LangGraph StateGraph. The primary integration work is: wiring the outbox processor to trigger the graph, implementing PDF parsing and caching, designing the Pydantic extraction schema, writing effective extraction prompts, and implementing assertion/negation detection.

A key architectural decision is whether to use the google-genai SDK directly or go through LangChain's `ChatVertexAI` wrapper. **Use `ChatVertexAI` from `langchain-google-vertexai`** because the codebase already depends on it (see `libs/inference/src/inference/loaders.py`), it integrates natively with LangGraph nodes, and `with_structured_output()` supports nested Pydantic models. The google-genai SDK would be a parallel dependency with no clear benefit.

**Primary recommendation:** Build a 4-node LangGraph StateGraph (ingest -> extract -> parse -> queue) in agent-a-service, triggered by ProtocolUploaded events via the outbox processor, using `ChatVertexAI.with_structured_output()` for Gemini-based extraction with a nested Pydantic schema, `pymupdf4llm.to_markdown()` for PDF parsing with `diskcache` for caching, and prompt-based assertion/negation detection.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `langchain-google-vertexai` | latest (already in deps) | Gemini model access via LangChain | Already used in `libs/inference/loaders.py`; `with_structured_output()` integrates with LangGraph |
| `langgraph` | 1.0.6+ (already in deps) | StateGraph workflow orchestration | Already used for agent-a-service skeleton; standard for multi-step LLM workflows |
| `pymupdf4llm` | 0.2.9 | PDF-to-Markdown conversion with table/layout preservation | Best-in-class for LLM-optimized PDF extraction; HIGH reputation on Context7 (88.8 benchmark) |
| `diskcache` | 5.6.3+ (already in deps) | Caching parsed PDF markdown content | Already in project dependencies; pure-Python, faster than Redis for local caching |
| `pydantic` | v2 (already in deps via SQLModel) | Structured output schema definition | Standard for defining Gemini response schemas; `ChatVertexAI.with_structured_output()` accepts Pydantic models |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pymupdf` (fitz) | latest (already in deps) | Low-level PDF operations, byte-stream handling | Already used in `api_service/quality.py`; needed for opening PDF from GCS bytes |
| `tenacity` | 8.2+ (already in deps) | Retry with exponential backoff on Gemini API calls | Already used in `inference/factory.py`; wrap extraction calls |
| `jinja2` | already in deps | Prompt templates for extraction | Already used in `inference/factory.py` `render_prompts()` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `ChatVertexAI` (LangChain) | `google-genai` SDK directly | Direct SDK gives more control but duplicates model management; LangChain integrates with LangGraph natively |
| `pymupdf4llm` | `pypdf` + custom markdown | pypdf lacks table detection and LLM-optimized output; pymupdf4llm purpose-built for this |
| `diskcache` | Redis | Redis requires separate service; diskcache is pure-Python, already a dependency |
| Prompt-based assertion detection | Dedicated NLP model (e.g., clinical-assertion-negation-bert) | Dedicated model adds complexity and GPU requirement; Gemini can handle assertion classification in the same structured output call |

**Installation:**
```bash
uv add pymupdf4llm
```
Note: `pymupdf4llm` is the only NEW dependency. All others are already in the workspace.

## Architecture Patterns

### Recommended Project Structure
```
services/agent-a-service/src/agent_a_service/
  __init__.py           # Exports get_graph()
  graph.py              # LangGraph StateGraph: ingest -> extract -> parse -> queue
  state.py              # ExtractionState TypedDict (replaces generic AgentState)
  nodes/
    __init__.py
    ingest.py           # PDF fetch + pymupdf4llm parsing + diskcache
    extract.py          # Gemini structured extraction via ChatVertexAI
    parse.py            # Post-process: assertion refinement, confidence calibration
    queue.py            # Persist CriteriaBatch/Criteria + publish CriteriaExtracted event
  schemas/
    __init__.py
    criteria.py         # Pydantic models for Gemini structured output
  prompts/
    system.jinja2       # System prompt for criteria extraction
    user.jinja2         # User prompt template with protocol markdown
  pdf_parser.py         # pymupdf4llm wrapper with diskcache integration
  trigger.py            # Outbox handler: ProtocolUploaded -> invoke graph
```

### Pattern 1: Event-Triggered LangGraph Workflow
**What:** The outbox processor dispatches `ProtocolUploaded` events to a handler that invokes the LangGraph workflow.
**When to use:** When an agent must react to domain events asynchronously.
**Example:**
```python
# trigger.py - Outbox handler wires event to graph invocation
from agent_a_service.graph import get_graph
from agent_a_service.state import ExtractionState

async def handle_protocol_uploaded(payload: dict) -> None:
    """Handle ProtocolUploaded event by running extraction workflow."""
    graph = get_graph()
    initial_state: ExtractionState = {
        "protocol_id": payload["protocol_id"],
        "file_uri": payload["file_uri"],
        "title": payload["title"],
        "markdown_content": "",
        "raw_criteria": [],
        "criteria_batch_id": "",
        "error": None,
    }
    await graph.ainvoke(initial_state)
```

**Integration point (in api-service/main.py lifespan):**
```python
# Register handler with outbox processor
from agent_a_service.trigger import handle_protocol_uploaded

processor = OutboxProcessor(
    engine=engine,
    handlers={
        "protocol_uploaded": [handle_protocol_uploaded],
    },
)
```

### Pattern 2: Pydantic Schema for Gemini Structured Output
**What:** Define nested Pydantic models that `ChatVertexAI.with_structured_output()` uses to constrain Gemini's JSON response.
**When to use:** When extracting structured data from unstructured text via LLM.
**Example:**
```python
# schemas/criteria.py
from pydantic import BaseModel, Field
from typing import Literal
from enum import Enum

class AssertionStatus(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    HYPOTHETICAL = "HYPOTHETICAL"
    HISTORICAL = "HISTORICAL"
    CONDITIONAL = "CONDITIONAL"

class TemporalConstraint(BaseModel):
    """Temporal constraint on a criterion."""
    duration: str | None = Field(None, description="Duration value, e.g., '6 months'")
    relation: str | None = Field(None, description="Temporal relation: within, before, after, at_least")
    reference_point: str | None = Field(None, description="Reference point: screening, enrollment, diagnosis")

class NumericThreshold(BaseModel):
    """Numeric threshold for a criterion."""
    value: float = Field(description="The numeric value")
    unit: str = Field(description="Unit of measurement")
    comparator: str = Field(description="Comparison operator: >=, <=, >, <, ==, range")
    upper_value: float | None = Field(None, description="Upper bound for range comparisons")

class ExtractedCriterion(BaseModel):
    """A single extracted criterion from a clinical trial protocol."""
    text: str = Field(description="The original criterion text as written in the protocol")
    criteria_type: Literal["inclusion", "exclusion"] = Field(
        description="Whether this is an inclusion or exclusion criterion"
    )
    category: str | None = Field(
        None,
        description="Category: demographics, medical_history, lab_values, medications, procedures, other"
    )
    temporal_constraint: TemporalConstraint | None = Field(
        None, description="Any temporal constraint on this criterion"
    )
    conditions: list[str] = Field(
        default_factory=list,
        description="Conditional dependencies, e.g., 'if female of childbearing potential'"
    )
    numeric_thresholds: list[NumericThreshold] = Field(
        default_factory=list,
        description="Numeric thresholds mentioned in the criterion"
    )
    assertion_status: AssertionStatus = Field(
        description="Assertion status: PRESENT means required, ABSENT means must not have, etc."
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence score for this extraction"
    )
    source_section: str | None = Field(
        None, description="Section header where this criterion was found"
    )

class ExtractionResult(BaseModel):
    """Complete extraction result from a protocol."""
    criteria: list[ExtractedCriterion] = Field(
        description="All extracted inclusion and exclusion criteria"
    )
    protocol_summary: str = Field(
        description="Brief summary of the protocol's purpose"
    )
```
**Source:** Verified against Context7 `/langchain-ai/langchain-google` and `/googleapis/python-genai` docs showing Pydantic model support with nested objects.

### Pattern 3: PDF Parsing with Caching
**What:** Parse PDF to markdown using pymupdf4llm, cache result keyed by protocol_id to avoid re-parsing.
**When to use:** PDF content is immutable once uploaded; parsing is CPU-intensive.
**Example:**
```python
# pdf_parser.py
import diskcache
import pymupdf4llm
import pymupdf
from pathlib import Path

_cache = diskcache.Cache(directory=str(Path.home() / ".cache" / "medgemma" / "pdf_markdown"))

def parse_pdf_to_markdown(
    pdf_bytes: bytes,
    cache_key: str,
    force_reparse: bool = False,
) -> str:
    """Parse PDF bytes to LLM-optimized markdown with caching."""
    if not force_reparse:
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    md_text = pymupdf4llm.to_markdown(
        doc,
        page_chunks=False,      # Single string for full document
        table_strategy="lines_strict",  # Best table detection
        force_text=True,         # Extract text even on image pages
        show_progress=False,
    )
    doc.close()

    _cache.set(cache_key, md_text, expire=86400 * 7)  # Cache for 7 days
    return md_text
```
**Source:** Verified against Context7 `/pymupdf/pymupdf4llm` docs and `/grantjenks/python-diskcache` docs.

### Pattern 4: LangGraph State with Error Handling
**What:** ExtractionState TypedDict carries data between nodes; error field enables graceful failure routing.
**When to use:** Multi-step workflows where any node can fail.
**Example:**
```python
# state.py
from typing import Any
from typing_extensions import TypedDict

class ExtractionState(TypedDict):
    """State for the criteria extraction workflow."""
    protocol_id: str
    file_uri: str
    title: str
    markdown_content: str
    raw_criteria: list[dict[str, Any]]
    criteria_batch_id: str
    error: str | None
```

### Anti-Patterns to Avoid
- **Parsing PDF inside the LLM call:** Parse PDF to markdown FIRST, then send markdown to Gemini. Sending raw PDF bytes wastes tokens and produces worse results.
- **One giant extraction prompt:** For long protocols (>100 pages), chunk the markdown and extract criteria per-section, then deduplicate. Single-pass extraction on very long documents may miss criteria or hit context limits.
- **Skipping assertion detection in the prompt:** If the prompt does not explicitly ask for assertion status, Gemini will default everything to PRESENT. The system prompt MUST define assertion categories with examples.
- **Hardcoding model name:** Use environment variable (`GEMINI_MODEL_NAME`) with a sensible default (`gemini-2.5-flash`). This allows switching models without code changes.
- **Synchronous outbox handler calling async graph:** The outbox processor currently runs handlers synchronously. The handler must bridge to async (e.g., `asyncio.run()` or run in executor).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PDF-to-Markdown conversion | Custom text extraction with pymupdf | `pymupdf4llm.to_markdown()` | Handles tables, columns, headers, images; tested across thousands of PDF layouts |
| Structured LLM output | JSON parsing with regex/string matching | `ChatVertexAI.with_structured_output(PydanticModel)` | Guaranteed schema compliance; automatic validation; retry-compatible |
| Caching parsed content | Custom file-based cache | `diskcache.Cache` | Thread-safe, ACID-compliant, handles eviction, expiry, and concurrent access |
| Retry logic on API calls | Custom try/except loops | `tenacity` decorators (already in `inference/factory.py`) | Exponential backoff, configurable stop conditions, logging hooks |
| Prompt template rendering | String formatting / f-strings | Jinja2 templates via `inference/factory.py render_prompts()` | Separation of concerns; testable templates; variable escaping |

**Key insight:** The existing `create_structured_extractor` in `libs/inference/src/inference/factory.py` already implements the pattern of model loading + prompt rendering + structured output + retry. Phase 3 should either use it directly or follow the same pattern closely for the extraction node.

## Common Pitfalls

### Pitfall 1: Gemini Context Window Limits on Long Protocols
**What goes wrong:** Clinical trial protocols can be 50-200+ pages. Even with Gemini 2.5 Flash's large context window (1M tokens), sending the entire document as one prompt can cause extraction quality degradation toward the end of the document.
**Why it happens:** LLM attention degrades on very long inputs; criteria scattered across sections may be missed.
**How to avoid:** Implement a chunking strategy: detect "Inclusion Criteria" and "Exclusion Criteria" sections via header detection, extract the relevant sections, and send targeted chunks. Use `pymupdf4llm` with `page_chunks=True` to get per-page metadata and section headers, then filter to relevant sections before extraction.
**Warning signs:** Extraction misses criteria that appear late in the document; confidence scores are systematically lower for criteria from later pages.

### Pitfall 2: Assertion Status Defaults to PRESENT
**What goes wrong:** Without explicit assertion detection guidance in the prompt, Gemini classifies all criteria as PRESENT, missing negations like "no history of diabetes" (should be ABSENT) or "if applicable" (should be CONDITIONAL).
**Why it happens:** The default assumption for eligibility criteria is that they describe required conditions. Negation and conditionality are linguistically subtle.
**How to avoid:** Include explicit assertion detection instructions with examples in the system prompt. Provide at least 3 examples for each assertion status (PRESENT, ABSENT, HYPOTHETICAL, HISTORICAL, CONDITIONAL). Research shows fine-tuned models achieve 96.2% assertion accuracy vs 90.1% for GPT-4o zero-shot.
**Warning signs:** All criteria have assertion_status=PRESENT; criteria containing "no", "without", "not", "history of" are misclassified.

### Pitfall 3: Nested Pydantic Model Serialization Issues
**What goes wrong:** `ChatVertexAI.with_structured_output()` may return flat dicts instead of nested Pydantic objects for complex schemas, especially with lists of nested models.
**Why it happens:** Known issue in langchain-google-vertexai with deeply nested schemas; Gemini may produce slightly malformed JSON for complex nesting.
**How to avoid:** Use `method="json_mode"` parameter with `with_structured_output()`. Add a validation step in the parse node that manually constructs Pydantic models from the raw dict output if automatic parsing fails. Keep nesting to 2 levels max.
**Warning signs:** `ValidationError` on extraction output; fields like `temporal_constraint` or `numeric_thresholds` come back as `None` when they should have values.

### Pitfall 4: Outbox Handler Sync/Async Mismatch
**What goes wrong:** The outbox processor in `events_py/outbox.py` calls handlers synchronously (`handler(event.payload)`), but the LangGraph workflow is async (`await graph.ainvoke()`).
**Why it happens:** The outbox processor was designed for simple synchronous handlers; LangGraph graphs are async by default.
**How to avoid:** Two options: (a) Make the handler synchronous and use `asyncio.run()` to bridge, or (b) modify the outbox processor to support async handlers via `await handler(event.payload)`. Option (a) is simpler for Phase 3; option (b) is better long-term but requires modifying shared library code.
**Warning signs:** `RuntimeError: This event loop is already running` or handler silently fails.

### Pitfall 5: PDF Fetching from GCS in Agent Context
**What goes wrong:** Agent-a needs to download the PDF from GCS to parse it, but the GCS path may be a mock `local://` path in development.
**Why it happens:** Phase 2 implemented mock GCS URLs for local development. Agent-a must handle both real `gs://` paths and mock paths.
**How to avoid:** Create a `fetch_pdf_bytes(file_uri: str) -> bytes` helper that handles both `gs://` (download from GCS) and `local://` (read from local filesystem or return test fixture). Reuse the `get_gcs_client()` pattern from `api_service/gcs.py`.
**Warning signs:** `FileNotFoundError` or `ValueError` when processing protocols uploaded in local dev mode.

### Pitfall 6: Duplicate Criteria from Overlapping Sections
**What goes wrong:** Protocols often repeat criteria in summaries, abstracts, and the formal eligibility section. Extraction produces duplicates.
**Why it happens:** The same criterion text appears in multiple sections of the document.
**How to avoid:** Add a deduplication step in the parse node that compares criteria text using fuzzy matching (e.g., >90% similarity). Track `source_section` to prefer criteria from the formal "Eligibility" section over other locations.
**Warning signs:** CriteriaBatch contains near-duplicate criteria with different source_sections.

## Code Examples

### Example 1: LangGraph StateGraph with 4 Nodes
```python
# graph.py - Verified pattern from Context7 /websites/langchain_oss_python_langgraph
from langgraph.graph import END, START, StateGraph
from agent_a_service.state import ExtractionState
from agent_a_service.nodes.ingest import ingest_node
from agent_a_service.nodes.extract import extract_node
from agent_a_service.nodes.parse import parse_node
from agent_a_service.nodes.queue import queue_node

def should_continue(state: ExtractionState) -> str:
    """Route based on error state."""
    if state.get("error"):
        return "error"
    return "continue"

def create_graph():
    workflow = StateGraph(ExtractionState)

    workflow.add_node("ingest", ingest_node)
    workflow.add_node("extract", extract_node)
    workflow.add_node("parse", parse_node)
    workflow.add_node("queue", queue_node)

    workflow.add_edge(START, "ingest")
    workflow.add_conditional_edges("ingest", should_continue, {
        "continue": "extract",
        "error": END,
    })
    workflow.add_conditional_edges("extract", should_continue, {
        "continue": "parse",
        "error": END,
    })
    workflow.add_edge("parse", "queue")
    workflow.add_edge("queue", END)

    return workflow.compile()
```

### Example 2: Extraction Node Using ChatVertexAI Structured Output
```python
# nodes/extract.py
# Source: Context7 /langchain-ai/langchain-google (nested Pydantic support)
import logging
from typing import Any
from langchain_google_vertexai import ChatVertexAI
from agent_a_service.schemas.criteria import ExtractionResult
from agent_a_service.state import ExtractionState
from inference.factory import render_prompts
from pathlib import Path

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

async def extract_node(state: ExtractionState) -> dict[str, Any]:
    """Extract structured criteria from protocol markdown using Gemini."""
    if state.get("error"):
        return {}

    try:
        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
        llm = ChatVertexAI(model_name=model_name, temperature=0)
        structured_llm = llm.with_structured_output(ExtractionResult, method="json_mode")

        system_prompt, user_prompt = render_prompts(
            prompts_dir=PROMPTS_DIR,
            system_template="system.jinja2",
            user_template="user.jinja2",
            prompt_vars={
                "title": state["title"],
                "markdown_content": state["markdown_content"],
            },
        )

        result = await structured_llm.ainvoke([
            ("system", system_prompt),
            ("user", user_prompt),
        ])

        criteria_dicts = [c.model_dump() for c in result.criteria]
        return {"raw_criteria": criteria_dicts}

    except Exception as e:
        logger.error("Extraction failed for protocol %s: %s", state["protocol_id"], e)
        return {"error": f"Extraction failed: {e}"}
```

### Example 3: Queue Node with Outbox Pattern
```python
# nodes/queue.py
# Source: Existing pattern from events_py/outbox.py persist_with_outbox()
import logging
from typing import Any
from shared.models import CriteriaBatch, Criteria
from events_py.models import DomainEventKind
from events_py.outbox import persist_with_outbox
from sqlmodel import Session
from api_service.storage import engine
from agent_a_service.state import ExtractionState

logger = logging.getLogger(__name__)

async def queue_node(state: ExtractionState) -> dict[str, Any]:
    """Persist extracted criteria and publish CriteriaExtracted event."""
    batch = CriteriaBatch(
        protocol_id=state["protocol_id"],
        status="pending_review",
        extraction_model=os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash"),
    )

    criteria_ids = []
    with Session(engine) as session:
        session.add(batch)
        session.flush()  # Get batch.id

        for raw in state["raw_criteria"]:
            criterion = Criteria(
                batch_id=batch.id,
                criteria_type=raw["criteria_type"],
                category=raw.get("category"),
                text=raw["text"],
                temporal_constraint=raw.get("temporal_constraint"),
                conditions=raw.get("conditions"),
                numeric_thresholds=raw.get("numeric_thresholds"),
                assertion_status=raw.get("assertion_status"),
                confidence=raw.get("confidence", 1.0),
                source_section=raw.get("source_section"),
            )
            session.add(criterion)
            session.flush()
            criteria_ids.append(criterion.id)

        # Publish CriteriaExtracted event via outbox
        persist_with_outbox(
            session=session,
            entity=batch,  # Already added, persist_with_outbox calls session.add again (idempotent)
            event_type=DomainEventKind.CRITERIA_EXTRACTED,
            aggregate_type="criteria_batch",
            aggregate_id=batch.id,
            payload={
                "batch_id": batch.id,
                "protocol_id": state["protocol_id"],
                "criteria_ids": criteria_ids,
                "criteria_count": len(criteria_ids),
            },
        )
        session.commit()

    return {"criteria_batch_id": batch.id}
```

### Example 4: Assertion Detection Prompt Pattern
```
# prompts/system.jinja2 (excerpt for assertion guidance)
## Assertion Status Classification

For each criterion, determine the assertion status:

- **PRESENT**: The condition must be true/present. Example: "Age >= 18 years" -> PRESENT
- **ABSENT**: The condition must NOT be true/absent. Example: "No history of cardiac disease" -> ABSENT
- **HYPOTHETICAL**: A theoretical/future condition. Example: "Willing to use contraception during study" -> HYPOTHETICAL
- **HISTORICAL**: Refers to past medical history. Example: "Prior treatment with platinum-based chemotherapy" -> HISTORICAL
- **CONDITIONAL**: Depends on another condition. Example: "If female of childbearing potential, must have negative pregnancy test" -> CONDITIONAL

Key negation markers that indicate ABSENT:
- "no history of", "without", "absence of", "not have", "free of", "no evidence of", "no prior"

Key conditionality markers:
- "if", "in case of", "when applicable", "for patients who"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Rule-based NegEx for negation | LLM-based assertion detection in-context | 2024-2025 | Gemini/GPT-4 can detect assertion status with >90% accuracy in-prompt; no separate NLP pipeline needed |
| pymupdf + custom markdown | pymupdf4llm with `table_strategy` | 2024 (v0.1.0) | Purpose-built for LLM consumption; handles tables, columns, headers automatically |
| Unstructured text output from LLM | Pydantic-constrained structured output | 2024-2025 | Gemini native JSON mode with `response_schema` guarantees valid JSON; eliminates post-processing parsing |
| Gemini 1.5 Pro | Gemini 2.5 Flash | 2025-2026 | Better structured output, larger context window (1M tokens), faster, cheaper |
| Custom PDF chunking | pymupdf4llm `page_chunks=True` with metadata | 2025 | Per-page metadata includes section headers, table boundaries, enabling targeted extraction |

**Deprecated/outdated:**
- `pdf4llm` package: Renamed to `pymupdf4llm` (still works as alias but use the canonical name)
- `langchain_core.pydantic_v1`: Use standard `pydantic` v2 imports. LangChain has migrated to Pydantic v2.
- `gemini-1.5-pro` model name: Still works but `gemini-2.5-flash` is recommended for extraction tasks (faster, cheaper, comparable quality)

## Open Questions

1. **Outbox processor async handler support**
   - What we know: Current `OutboxProcessor.poll_and_process()` calls `handler(event.payload)` synchronously. LangGraph's `graph.ainvoke()` is async.
   - What's unclear: Whether modifying the outbox processor to support async handlers is safe, or if we should bridge with `asyncio.run()` in the handler.
   - Recommendation: Use `asyncio.run()` in the handler for Phase 3 (simplest). Create a follow-up task to make OutboxProcessor async-aware if needed for Phase 5.

2. **Agent-a as separate service vs integrated with api-service**
   - What we know: Docker Compose defines agent-a as a separate container. But for Phase 3, the handler needs database access and the outbox processor runs in api-service.
   - What's unclear: Should agent-a run its own outbox processor polling the same database, or should the api-service handler import and invoke agent-a's graph directly?
   - Recommendation: For Phase 3, register the handler in api-service's outbox processor (simplest, single-process). Agent-a's graph code lives in its own package but is invoked from api-service. Separate process deployment can happen in Phase 7 (production hardening).

3. **Long document chunking strategy**
   - What we know: Protocols can be 50-200 pages. Gemini 2.5 Flash supports 1M tokens (~750K words of input).
   - What's unclear: Whether sending the full document works well enough, or whether section-targeted extraction produces better results.
   - Recommendation: Start with full-document extraction (simpler). Add section-targeted chunking only if quality degrades on long protocols. Track `source_section` to enable this optimization later.

4. **GCS PDF download for local dev**
   - What we know: Phase 2 stores `local://` paths for dev mode. Agent-a needs to read the actual PDF bytes.
   - What's unclear: How mock upload stores actual bytes in local dev (it doesn't currently -- the mock endpoint just consumes and discards the body).
   - Recommendation: For local dev, store uploaded PDF bytes to a local directory during mock upload, and have the PDF fetcher read from that path. Alternatively, provide a test fixture PDF for development.

## Sources

### Primary (HIGH confidence)
- Context7 `/pymupdf/pymupdf4llm` - PDF-to-markdown API, table_strategy, page_chunks, header detection
- Context7 `/websites/langchain_oss_python_langgraph` - StateGraph patterns, async nodes, structured output with Pydantic
- Context7 `/googleapis/python-genai` - Gemini structured output with Pydantic response_schema
- Context7 `/langchain-ai/langchain-google` - ChatVertexAI.with_structured_output() for nested Pydantic models, json_mode
- Context7 `/grantjenks/python-diskcache` - Cache API with TTL, memoize decorator, set/get patterns
- Existing codebase: `libs/shared/src/shared/models.py`, `libs/events-py/src/events_py/outbox.py`, `libs/inference/src/inference/factory.py`, `services/agent-a-service/src/agent_a_service/graph.py`

### Secondary (MEDIUM confidence)
- [PyMuPDF4LLM PyPI](https://pypi.org/project/pymupdf4llm/) - Version 0.2.9 (Jan 2026), changelog verified
- [PyMuPDF4LLM API docs](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/api.html) - Full to_markdown() parameter reference
- [Gemini 2.5 Flash docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash) - Model capabilities, structured output support
- [LangChain structured output docs](https://docs.langchain.com/oss/python/langchain/structured-output) - with_structured_output() patterns
- [Assertion detection research (2025)](https://arxiv.org/abs/2503.17425) - PRESENT/ABSENT/HYPOTHETICAL/CONDITIONAL categories, fine-tuned models achieve 96.2% accuracy

### Tertiary (LOW confidence)
- [Clinical trial criteria extraction with LLMs (JAMIA 2025)](https://academic.oup.com/jamia/article/32/3/447/7933305) - Criteria clustering approaches
- [Criteria2Query 3.0](https://medinform.jmir.org/2025/1/e71252) - LLM-based criteria to OMOP conversion, F1=0.891 but 21-50% hallucination rates

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries verified via Context7 with code examples; most already in project dependencies
- Architecture: MEDIUM-HIGH - LangGraph StateGraph pattern well-documented; outbox integration is custom but follows existing project patterns
- Pitfalls: MEDIUM - Assertion detection and nested schema issues confirmed via multiple sources; long-document chunking needs empirical validation
- PDF parsing: HIGH - pymupdf4llm API thoroughly documented with specific parameter recommendations

**Research date:** 2026-02-11
**Valid until:** 2026-03-11 (30 days - stable libraries, well-established patterns)
