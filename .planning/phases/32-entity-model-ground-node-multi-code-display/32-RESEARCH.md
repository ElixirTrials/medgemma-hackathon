# Phase 32: Entity Model, Ground Node & Multi-Code Display - Research

**Researched:** 2026-02-16
**Domain:** Entity model extension, LangGraph ground node implementation, multi-terminology grounding, UI badge display
**Confidence:** HIGH

## Summary

Phase 32 extends the Entity model to support multi-terminology codes (RxNorm, ICD-10, LOINC, HPO), implements a real ground node with terminology routing to replace the current subprocess-based MCP grounding, adds pipeline error handling with checkpoint-based retry, and displays color-coded multi-code badges in the UI with per-system autocomplete editing.

The research reveals that the current architecture already has terminology clients (UmlsClient), LangGraph checkpointing support, and Gemini structured output patterns in place. The key additions needed are: (1) Entity model columns for new terminology codes, (2) terminology router that dispatches to system-specific APIs, (3) LangGraph checkpointing integration for retry, and (4) UI components for multi-code badge display with working autocomplete.

**Primary recommendation:** Use PostgreSQL checkpointer for fault tolerance, direct HTTP clients for terminology APIs (not MCP subprocesses), Gemini structured output for entity extraction, and color-coded badges per terminology system in the UI.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Multi-code display:**
- Goal: one definitive grounding code per terminology system per entity (not synonym lists)
- Show ALL resolved codes per entity (RxNorm + UMLS CUI + SNOMED + ICD-10 + LOINC + HPO if resolved)
- Color-coded badges by system
- All codes are user-modifiable with per-system autocomplete search
- Current UMLS autocomplete doesn't work correctly — fix it along with adding other system autocompletes

**Error recovery UX:**
- Red "Failed" badge with specific error reason
- Retry from failed node only (resume from last LangGraph checkpoint)
- Simple processing spinner only

**Entity extraction approach:**
- Gemini produces fully structured results using native structured output (response_schema with Pydantic models)
- MedGemma serves as medical expert — consulted for medical domain knowledge
- No separate research spike needed — implement this approach, review decision after

**Migration & backwards compatibility:**
- Clean migration — no backwards compatibility concerns
- Drop and recreate database schema (fresh from models, no Alembic migration needed)
- New multi-code columns added directly to Entity model

### Claude's Discretion

- Exact badge color assignments per terminology system
- Autocomplete debounce and minimum character settings per system
- How the retry button integrates with existing protocol detail page

### Deferred Ideas (OUT OF SCOPE)

- Real-time pipeline progress display (SSE/WebSocket)
- Re-process entire pipeline option (alongside retry-from-failure)

</user_constraints>

---

## Standard Stack

### Core (Entity Model & Grounding)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLModel | 0.0.22+ | Entity model with new code columns | Already used for all models in codebase |
| httpx | 0.27+ | HTTP client for terminology APIs | Already used in UmlsClient, sync+async support |
| diskcache | 5.6+ | Disk-based caching for API responses | Already used in UmlsClient for UMLS cache |
| tenacity | 8.5+ | Retry with exponential backoff | Already used in UmlsClient and nodes |
| Pydantic | 2.x | Gemini structured output schemas | Already used for extraction schemas |

### Core (LangGraph Checkpointing)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| langgraph | 1.0.8+ | StateGraph with checkpointing | Already used for extraction and grounding graphs |
| langgraph-checkpoint-postgres | 2.0+ | PostgreSQL checkpointer for fault tolerance | Production-grade persistence, queryable history |
| psycopg | 3.x | PostgreSQL adapter for checkpointer | Standard for PostgreSQL in Python 3.13+ |

### Core (UI Multi-Code Display)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React | 18.x | UI components for badge display | Already used in hitl-ui |
| TanStack Query | 5.x | API queries for terminology autocomplete | Already used for all data fetching |
| Radix UI Popover | 1.x | Autocomplete dropdown positioning | Already used in UmlsCombobox |
| cmdk | 1.x | Command palette for autocomplete | Already used in UmlsCombobox |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| platformdirs | 4.x | Cache directory paths | Used by terminology clients for disk cache location |
| lucide-react | 0.x | Icons for badges and status | Already used for UI icons |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PostgreSQL checkpointer | MemorySaver (in-memory) | MemorySaver clears on restart, no cross-process persistence |
| PostgreSQL checkpointer | RedisSaver | Redis faster but requires separate service, less queryable |
| Direct HTTP clients | ToolUniverse MCP | ToolUniverse adds 211+ tools, subprocess overhead, same failure mode as current UMLS MCP |
| Color-coded badges | Icon-per-system | Badges provide visual hierarchy and code visibility |

**Installation:**

```bash
# Backend (already in project)
uv add langgraph-checkpoint-postgres psycopg

# Frontend (already in project)
cd apps/hitl-ui && npm install @radix-ui/react-popover cmdk
```

---

## Architecture Patterns

### Recommended Project Structure

```
libs/shared/src/shared/
├── models.py                    # Entity model with new code columns
└── resilience.py                # Circuit breakers per terminology API

services/grounding-service/src/grounding_service/
├── graph.py                     # Updated with checkpointer
├── state.py                     # GroundingState unchanged
├── nodes/
│   └── ground.py               # NEW: ground node with terminology router
├── terminology/
│   ├── __init__.py             # Re-exports
│   ├── router.py               # TerminologyRouter class
│   ├── base.py                 # BaseTerminologyClient ABC
│   ├── umls.py                 # UmlsClient adapter (existing)
│   ├── rxnorm.py               # RxNormClient (NEW)
│   ├── loinc.py                # LoincClient (NEW)
│   ├── icd10.py                # Icd10Client (NEW)
│   └── hpo.py                  # HpoClient (NEW)
└── prompts/
    └── ground.jinja2            # Gemini structured output prompt

apps/hitl-ui/src/
├── components/
│   ├── EntityCard.tsx           # Updated with multi-code badges
│   ├── TerminologyBadge.tsx    # NEW: color-coded badge component
│   └── TerminologyCombobox.tsx # NEW: per-system autocomplete
└── screens/
    └── ProtocolDetail.tsx       # Updated with retry button
```

### Pattern 1: Entity Model Extension (SQLModel)

**What:** Add nullable columns for multi-terminology codes to Entity model

**When to use:** Need to store codes from multiple terminology systems per entity

**Example:**

```python
# libs/shared/src/shared/models.py
class Entity(SQLModel, table=True):
    """Medical entity extracted from criteria."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    criteria_id: str = Field(foreign_key="criteria.id", index=True)
    entity_type: str = Field(index=True)
    text: str = Field()

    # Existing fields
    umls_cui: str | None = Field(default=None)
    snomed_code: str | None = Field(default=None)
    preferred_term: str | None = Field(default=None)

    # NEW: Multi-terminology codes
    rxnorm_code: str | None = Field(default=None, index=True)
    icd10_code: str | None = Field(default=None, index=True)
    loinc_code: str | None = Field(default=None, index=True)
    hpo_code: str | None = Field(default=None, index=True)

    # Grounding metadata
    grounding_confidence: float | None = Field(default=None)
    grounding_method: str | None = Field(default=None)
    grounding_system: str | None = Field(default=None)  # Which system was primary

    # Error tracking
    grounding_error: str | None = Field(default=None)  # Specific error message

    # Existing fields
    review_status: str | None = Field(default=None)
    context_window: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(sa_column=_ts_col())
    updated_at: datetime = Field(sa_column=_ts_col_update())
```

### Pattern 2: Terminology Router (Entity-Type-Aware Dispatch)

**What:** Route entities to appropriate terminology APIs based on entity type

**When to use:** Need to ground entities to different terminology systems based on medical domain

**Example:**

```python
# services/grounding-service/src/grounding_service/terminology/router.py
from dataclasses import dataclass

@dataclass
class TerminologyResult:
    """Result from a terminology lookup."""
    code: str
    display: str
    system: str              # "SNOMEDCT_US", "RxNorm", "LOINC", "ICD-10-CM", "HPO"
    confidence: float
    method: str              # "exact_match", "semantic_similarity", "not_found"

class TerminologyRouter:
    """Routes entities to appropriate terminology APIs based on entity type."""

    # Entity type -> list of terminology systems to search (in priority order)
    ROUTING_TABLE: dict[str, list[str]] = {
        "Medication":  ["rxnorm", "umls_snomed"],
        "Condition":   ["umls_snomed", "icd10"],
        "Procedure":   ["umls_snomed"],
        "Lab_Value":   ["loinc", "umls_snomed"],
        "Biomarker":   ["umls_snomed", "hpo"],
        "Demographic": [],  # Skip grounding for demographics
    }

    def __init__(self) -> None:
        """Initialize terminology clients."""
        self.umls_client = get_umls_client()
        self.rxnorm_client = RxNormClient()
        self.loinc_client = LoincClient()
        self.icd10_client = Icd10Client()
        self.hpo_client = HpoClient()

    async def ground_entity(
        self, entity_text: str, entity_type: str, context: str = ""
    ) -> dict[str, str | None]:
        """Ground entity to all relevant terminology systems.

        Returns dict with keys: rxnorm_code, icd10_code, loinc_code, hpo_code,
        umls_cui, snomed_code, grounding_system, grounding_error.
        """
        systems = self.ROUTING_TABLE.get(entity_type, [])

        if not systems:
            return {
                "rxnorm_code": None,
                "icd10_code": None,
                "loinc_code": None,
                "hpo_code": None,
                "umls_cui": None,
                "snomed_code": None,
                "grounding_system": None,
                "grounding_error": f"Entity type '{entity_type}' not routable",
            }

        results: dict[str, TerminologyResult | None] = {}

        for system in systems:
            try:
                result = await self._search_system(system, entity_text, context)
                results[system] = result
            except Exception as e:
                logger.warning("Terminology search failed for %s/%s: %s",
                             system, entity_text, e)
                results[system] = None

        # Map results to entity fields
        return {
            "rxnorm_code": results.get("rxnorm")?.code,
            "icd10_code": results.get("icd10")?.code,
            "loinc_code": results.get("loinc")?.code,
            "hpo_code": results.get("hpo")?.code,
            "umls_cui": results.get("umls_snomed")?.cui,
            "snomed_code": results.get("umls_snomed")?.code,
            "grounding_system": self._determine_primary_system(results, entity_type),
            "grounding_error": None,
        }

    async def _search_system(
        self, system: str, term: str, context: str
    ) -> TerminologyResult | None:
        """Dispatch to specific terminology API."""
        if system == "umls_snomed":
            candidates = self.umls_client.search_snomed(term, limit=1)
            if candidates:
                c = candidates[0]
                return TerminologyResult(c.code, c.display, "SNOMEDCT_US", c.confidence, "umls_api")
        elif system == "rxnorm":
            return await self.rxnorm_client.search(term)
        elif system == "loinc":
            return await self.loinc_client.search(term)
        elif system == "icd10":
            return await self.icd10_client.search(term)
        elif system == "hpo":
            return await self.hpo_client.search(term)
        return None

    def _determine_primary_system(
        self, results: dict[str, TerminologyResult | None], entity_type: str
    ) -> str | None:
        """Select primary terminology system for an entity based on routing priority."""
        systems = self.ROUTING_TABLE.get(entity_type, [])
        for system in systems:
            if results.get(system):
                return system
        return None
```

### Pattern 3: LangGraph Checkpointing for Retry

**What:** Use PostgreSQL checkpointer to enable retry from failed node

**When to use:** Pipeline can fail mid-execution and needs recovery without re-running successful nodes

**Example:**

```python
# services/grounding-service/src/grounding_service/graph.py
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection

def create_graph() -> Any:
    """Create grounding workflow graph with PostgreSQL checkpointer."""
    workflow = StateGraph(GroundingState)

    workflow.add_node("medgemma_ground", medgemma_ground_node)
    workflow.add_node("validate_confidence", validate_confidence_node)

    workflow.add_edge(START, "medgemma_ground")
    workflow.add_conditional_edges(
        "medgemma_ground",
        should_continue,
        {"continue": "validate_confidence", "error": END},
    )
    workflow.add_edge("validate_confidence", END)

    # Add PostgreSQL checkpointer
    from api_service.storage import engine
    connection_string = str(engine.url)

    checkpointer = PostgresSaver.from_conn_string(connection_string)
    checkpointer.setup()  # Create checkpoint tables if needed

    return workflow.compile(checkpointer=checkpointer)

# Invoke with thread_id for checkpointing
async def invoke_grounding_with_retry(state: GroundingState, thread_id: str) -> GroundingState:
    """Invoke grounding graph with fault tolerance."""
    config = {"configurable": {"thread_id": thread_id}}

    graph = get_graph()

    try:
        result = await graph.ainvoke(state, config)
        return result
    except Exception as e:
        logger.error("Grounding failed for thread %s: %s", thread_id, e)
        # Update protocol status to "grounding_failed" with error reason
        # Return state with error field set
        return {**state, "error": str(e)}

async def retry_grounding_from_checkpoint(thread_id: str) -> GroundingState:
    """Resume grounding from last checkpoint after failure."""
    config = {"configurable": {"thread_id": thread_id}}

    graph = get_graph()

    # Resume from checkpoint by passing None as input
    result = await graph.ainvoke(None, config)
    return result
```

### Pattern 4: Gemini Structured Output for Entity Extraction

**What:** Use Gemini native structured output with Pydantic schemas

**When to use:** Need guaranteed valid JSON output from LLM for entity extraction

**Example:**

```python
# services/grounding-service/src/grounding_service/nodes/ground.py
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

class ExtractedEntity(BaseModel):
    """Single extracted entity with grounding metadata."""
    text: str = Field(description="Entity text as it appears in criterion")
    entity_type: str = Field(description="Condition, Medication, Procedure, Lab_Value, Biomarker, Demographic")
    span_start: int = Field(description="Character offset where entity starts")
    span_end: int = Field(description="Character offset where entity ends")
    context_window: str = Field(description="Surrounding text for disambiguation")

class CriterionEntities(BaseModel):
    """Entities extracted from a single criterion."""
    criterion_id: str
    entities: list[ExtractedEntity]

class BatchEntityExtractionResult(BaseModel):
    """Batch extraction result for all criteria."""
    results: list[CriterionEntities]

async def extract_entities_with_gemini(criteria_texts: list[dict]) -> list[dict]:
    """Extract entities using Gemini structured output."""

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
        vertexai=True,
        project=os.getenv("GCP_PROJECT_ID"),
        location=os.getenv("GCP_REGION", "us-central1"),
    )

    # Pass Pydantic model directly to response_schema
    structured_llm = llm.with_structured_output(BatchEntityExtractionResult)

    system_prompt, user_prompt = render_prompts(
        prompts_dir=PROMPTS_DIR,
        system_template="system.jinja2",
        user_template="user.jinja2",
        prompt_vars={"criteria": criteria_texts},
    )

    result = await structured_llm.ainvoke(
        [("system", system_prompt), ("user", user_prompt)]
    )

    # Result is guaranteed to be BatchEntityExtractionResult
    return [
        {
            "criteria_id": cr.criterion_id,
            "text": entity.text,
            "entity_type": entity.entity_type,
            "span_start": entity.span_start,
            "span_end": entity.span_end,
            "context_window": entity.context_window,
        }
        for cr in result.results
        for entity in cr.entities
    ]
```

### Pattern 5: Multi-Code Badge Display (React)

**What:** Display color-coded badges for each terminology system with codes

**When to use:** Need to show all grounding codes per entity in a visually scannable way

**Example:**

```typescript
// apps/hitl-ui/src/components/TerminologyBadge.tsx
interface TerminologyBadgeProps {
    system: 'rxnorm' | 'icd10' | 'snomed' | 'loinc' | 'hpo' | 'umls';
    code: string;
    display?: string;
}

const SYSTEM_COLORS = {
    rxnorm: 'bg-blue-100 text-blue-800 border-blue-300',
    icd10: 'bg-orange-100 text-orange-800 border-orange-300',
    snomed: 'bg-green-100 text-green-800 border-green-300',
    loinc: 'bg-purple-100 text-purple-800 border-purple-300',
    hpo: 'bg-teal-100 text-teal-800 border-teal-300',
    umls: 'bg-indigo-100 text-indigo-800 border-indigo-300',
};

const SYSTEM_LABELS = {
    rxnorm: 'RxNorm',
    icd10: 'ICD-10',
    snomed: 'SNOMED',
    loinc: 'LOINC',
    hpo: 'HPO',
    umls: 'UMLS CUI',
};

export function TerminologyBadge({ system, code, display }: TerminologyBadgeProps) {
    const colorClass = SYSTEM_COLORS[system];
    const label = SYSTEM_LABELS[system];

    return (
        <span className={cn(
            'inline-flex items-center gap-1 rounded-full px-3 py-1 text-sm font-medium border',
            colorClass
        )}>
            <span className="font-semibold">{label}:</span>
            <span>{code}</span>
            {display && <span className="text-xs">({display})</span>}
        </span>
    );
}

// apps/hitl-ui/src/components/EntityCard.tsx
function EntityCodeBadges({ entity }: { entity: EntityResponse }) {
    return (
        <div className="flex flex-wrap gap-2 mb-3">
            {entity.rxnorm_code && (
                <TerminologyBadge system="rxnorm" code={entity.rxnorm_code} />
            )}
            {entity.icd10_code && (
                <TerminologyBadge system="icd10" code={entity.icd10_code} />
            )}
            {entity.snomed_code && (
                <TerminologyBadge system="snomed" code={entity.snomed_code} display={entity.preferred_term} />
            )}
            {entity.loinc_code && (
                <TerminologyBadge system="loinc" code={entity.loinc_code} />
            )}
            {entity.hpo_code && (
                <TerminologyBadge system="hpo" code={entity.hpo_code} />
            )}
            {entity.umls_cui && (
                <TerminologyBadge system="umls" code={entity.umls_cui} />
            )}

            {entity.grounding_error && (
                <span className="inline-flex items-center gap-1 rounded-full px-3 py-1 text-sm font-medium border bg-red-100 text-red-800 border-red-300">
                    <span className="font-semibold">Failed:</span>
                    <span>{entity.grounding_error}</span>
                </span>
            )}
        </div>
    );
}
```

### Anti-Patterns to Avoid

- **MCP subprocess for terminology clients**: Same 5-15s startup overhead as current UMLS MCP. Use direct HTTP clients.
- **No checkpointing**: Pipeline failures leave protocols in "grounding" status forever. Use PostgreSQL checkpointer.
- **Gemini without response_schema**: Output parsing errors require fallback logic. Use Pydantic models with native structured output.
- **Single badge for all codes**: Users can't distinguish which terminology system each code is from. Use color-coded badges per system.
- **Broken autocomplete**: Current UMLS autocomplete has latency issues. Build working autocomplete per terminology system with proper debouncing.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LangGraph checkpointing | Custom state persistence with database writes | langgraph-checkpoint-postgres | Handles partial success, concurrent writes, thread isolation |
| Terminology API clients | Custom retry/cache logic per API | BaseTerminologyClient ABC with httpx + diskcache + tenacity | Proven pattern from UmlsClient, consistent error handling |
| Gemini structured output | JSON parsing with try/except fallbacks | with_structured_output(PydanticModel) | Native Gemini feature, guaranteed valid output |
| Multi-code autocomplete | Custom search endpoints per system | Shared TerminologyCombobox component with system prop | DRY, consistent UX across all terminology systems |
| Badge color coordination | Hardcoded colors per component | SYSTEM_COLORS constant | Single source of truth for color scheme |

**Key insight:** LangGraph checkpointing is the critical feature that enables retry-from-failure. Without it, every pipeline error requires manual intervention or full pipeline restart.

---

## Common Pitfalls

### Pitfall 1: PostgreSQL Checkpointer Connection Pool Exhaustion

**What goes wrong:** Grounding graph creates new PostgreSQL connection per checkpoint write, exhausts pool, subsequent grounding fails with "connection pool exhausted" error.

**Why it happens:** PostgresSaver.from_conn_string() creates a new connection pool per graph instance. If graph is created in a node function (not at module level), each grounding invocation creates a new pool. Default pool size is 5 connections; grounding 10 batches simultaneously exhausts pool.

**How to avoid:**
- Create graph instance once at module level (singleton pattern already used in current codebase)
- Reuse checkpointer across all invocations
- Configure pool size if needed: `PostgresSaver.from_conn_string(conn_string, pool_size=20)`
- Monitor connection pool usage with `SELECT count(*) FROM pg_stat_activity WHERE datname = 'medgemma'`

**Warning signs:**
- Error: "psycopg.OperationalError: connection pool exhausted"
- Grounding succeeds for first few batches, then fails
- Database shows many idle connections from grounding-service

---

### Pitfall 2: Terminology Router Returns None for All Codes

**What goes wrong:** Entity persisted with all code fields NULL despite successful API calls, because terminology router silently swallows exceptions or returns None on partial failure.

**Why it happens:** Router calls 3-5 APIs per entity. If one API fails (timeout, 429, auth error), router catches exception and returns None for that system. If no fallback logic exists, entity gets persisted with all codes NULL even though some APIs succeeded.

**How to avoid:**
- Return partial results: if RxNorm succeeds but ICD-10 fails, still return RxNorm code
- Log specific API failures: "RxNorm API timeout for entity 'aspirin'" not "Terminology search failed"
- Set `grounding_error` field to most severe error, not first error
- Add per-API circuit breakers to prevent cascading failures

**Warning signs:**
- Entities have grounding_method="expert_review" but no error logged
- All entities in a batch have NULL codes despite different entity types
- API logs show mix of 200 OK and 5xx errors, but all entities show "not found"

---

### Pitfall 3: Gemini Structured Output with Nested Lists Fails Validation

**What goes wrong:** Gemini returns valid JSON but Pydantic validation fails with "field required" for nested list items, because Gemini omits optional fields in list elements.

**Why it happens:** Pydantic requires all fields present even if marked Optional, unless Field(default=None) is set. Gemini structured output omits optional fields to reduce token usage. For `entities: list[ExtractedEntity]`, if ExtractedEntity has `context_window: str`, Gemini may omit it, causing validation error.

**How to avoid:**
- Mark all optional fields with `Field(default=None)` or `Field(default="")`
- Use `model_config = ConfigDict(extra='allow')` to ignore extra fields
- Test schema with minimal prompts before using in production
- Add fallback: catch ValidationError and log the raw JSON response

**Warning signs:**
- Error: "ValidationError: 1 validation error for ExtractedEntity"
- Gemini returns JSON but Pydantic parsing fails
- Schema works in unit tests but fails in production with real criteria

---

### Pitfall 4: UI Autocomplete Debounce Too Aggressive, Feels Broken

**What goes wrong:** User types "aspirin" but autocomplete doesn't show results until they stop typing for 500ms. Feels laggy and broken compared to Google search.

**Why it happens:** Current UmlsCombobox uses 500ms debounce to reduce API calls. For terminology APIs with <200ms latency, this debounce is too long. User expects instant feedback.

**How to avoid:**
- Reduce debounce to 150ms for fast APIs (RxNorm, LOINC)
- Keep 300-500ms debounce for slow APIs (UMLS, HPO)
- Show "Searching..." spinner immediately on keypress
- Minimum 3 characters before search (prevent 1-2 char queries)
- Cache results in TanStack Query with 5-minute staleTime

**Warning signs:**
- Users report autocomplete "doesn't work" or "is slow"
- Network tab shows requests firing after delay feels too long
- Autocomplete works but users don't trust it

---

### Pitfall 5: Retry Button Invokes Full Pipeline Instead of Resuming from Checkpoint

**What goes wrong:** User clicks "Retry" on failed protocol, full pipeline re-runs (PDF fetch, extraction, grounding), even though extraction already succeeded. Wastes 30-60s and Gemini API quota.

**Why it happens:** Retry handler calls `graph.ainvoke(initial_state, config)` with fresh state instead of `graph.ainvoke(None, config)` to resume from checkpoint. Fresh state tells LangGraph to start from the beginning.

**How to avoid:**
- Retry from checkpoint: `graph.ainvoke(None, config={"configurable": {"thread_id": protocol_id}})`
- Do NOT pass initial state when resuming
- Use protocol_id as thread_id for deterministic checkpoint lookup
- Add API endpoint: `POST /protocols/{id}/retry` that resumes from checkpoint

**Warning signs:**
- Retry takes same time as initial run
- Logs show "Fetching PDF" and "Extracting criteria" on retry even though criteria already exist
- Checkpoint table has entries but they're never read

---

## Code Examples

Verified patterns from official sources and codebase:

### LangGraph Checkpoint Resume After Error

Source: [LangGraph Persistence Documentation](https://docs.langchain.com/oss/python/langgraph/persistence)

```python
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import StateGraph

# Create graph with PostgreSQL checkpointer
def create_graph_with_checkpointing(connection_string: str):
    checkpointer = PostgresSaver.from_conn_string(connection_string)
    checkpointer.setup()  # Create tables if needed

    workflow = StateGraph(GroundingState)
    # ... add nodes and edges ...

    return workflow.compile(checkpointer=checkpointer)

# Initial invocation with thread_id
config = {"configurable": {"thread_id": "protocol-123"}}
try:
    result = await graph.ainvoke(initial_state, config)
except Exception:
    # On failure, checkpoint is automatically saved
    pass

# Resume from checkpoint (pass None as input)
result = await graph.ainvoke(None, config)  # Resumes from last successful node
```

### RxNorm Client Pattern (Direct HTTP)

Source: Adapted from UmlsClient in codebase

```python
from dataclasses import dataclass
import httpx
import diskcache
from tenacity import retry, stop_after_attempt, wait_exponential

@dataclass
class RxNormResult:
    rxcui: str
    name: str
    synonym: str
    confidence: float

class RxNormClient:
    """Client for NLM RxNorm API."""

    BASE_URL = "https://rxnav.nlm.nih.gov/REST"

    def __init__(self):
        self._http = httpx.AsyncClient(timeout=10.0)
        self._cache = diskcache.Cache("/tmp/rxnorm-cache")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, min=0.5, max=2))
    async def search(self, drug_name: str, limit: int = 5) -> RxNormResult | None:
        """Search RxNorm for drug by name."""
        cache_key = f"rxnorm:{drug_name.lower()}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        # Try exact match first
        response = await self._http.get(
            f"{self.BASE_URL}/drugs.json",
            params={"name": drug_name}
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("drugGroup", {}).get("conceptGroup"):
                # Parse first result
                for group in data["drugGroup"]["conceptGroup"]:
                    if group.get("conceptProperties"):
                        concept = group["conceptProperties"][0]
                        result = RxNormResult(
                            rxcui=concept["rxcui"],
                            name=concept["name"],
                            synonym=concept.get("synonym", ""),
                            confidence=0.9,
                        )
                        self._cache.set(cache_key, result, expire=7*24*60*60)
                        return result

        # Fallback to approximate match
        response = await self._http.get(
            f"{self.BASE_URL}/approximateTerm.json",
            params={"term": drug_name, "maxEntries": limit}
        )
        # ... parse approximate results ...

        return None
```

### Gemini Structured Output with Pydantic

Source: [Gemini Structured Output Documentation](https://ai.google.dev/gemini-api/docs/structured-output)

```python
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI

class EntityExtraction(BaseModel):
    """Structured entity extraction result."""
    entities: list[ExtractedEntity] = Field(
        default_factory=list,
        description="List of medical entities found in the criterion"
    )

class ExtractedEntity(BaseModel):
    text: str = Field(description="Entity text")
    type: str = Field(description="Entity type: Medication, Condition, etc.")
    span_start: int = Field(default=0, description="Character offset")
    span_end: int = Field(default=0, description="Character offset")

# Create LLM with structured output
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
)

# Pass Pydantic model to response_schema
structured_llm = llm.with_structured_output(EntityExtraction)

# Invoke and get guaranteed valid Pydantic object
result = await structured_llm.ainvoke([
    ("system", "Extract medical entities from the given text."),
    ("user", "Patients must not be taking warfarin or aspirin.")
])

# result is EntityExtraction instance
print(result.entities)  # [ExtractedEntity(text="warfarin", type="Medication", ...), ...]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| MCP subprocess for UMLS | Direct UmlsClient import | Phase 31 | 5-15s latency reduction |
| Manual retry by re-running pipeline | LangGraph checkpoint resume | This phase | Avoid redundant extraction on retry |
| JSON parsing with try/except | Gemini with_structured_output | Gemini 2.0+ (2024) | Guaranteed valid output |
| Single SNOMED code per entity | Multi-terminology codes | This phase | Better interoperability with EHR systems |
| Generic "expert_review" fallback | Specific error messages per API | This phase | Actionable error information |

**Deprecated/outdated:**
- **MCP subprocess pattern for terminology clients**: Adds 5-15s startup overhead, zombie processes. Replaced with direct HTTP clients.
- **MemorySaver for production**: Clears on restart, no cross-process state. Use PostgresSaver for production.
- **Gemini without response_schema**: Requires custom JSON parsing. Use native structured output.

---

## Open Questions

1. **RxNorm API rate limits for batch grounding**
   - What we know: RxNorm API is free and has no documented rate limits
   - What's unclear: Real-world throughput limits (40 entities per batch = 40-80 API calls)
   - Recommendation: Start with 10 req/s limit, monitor 429 responses, increase if stable

2. **LOINC and HPO API authentication**
   - What we know: LOINC Clinical Tables API is free, HPO Monarch API is free
   - What's unclear: Whether API keys are required for production use
   - Recommendation: Test without keys first, add if 401 errors occur

3. **Checkpoint table growth rate**
   - What we know: PostgresSaver creates checkpoint rows per graph superstep
   - What's unclear: How many checkpoints per protocol, retention policy
   - Recommendation: Monitor checkpoint table size, add cleanup job if >10k rows/day

---

## Sources

### Primary (HIGH confidence)

- [LangGraph Persistence Documentation](https://docs.langchain.com/oss/python/langgraph/persistence) - Checkpointing, fault tolerance, resume from checkpoint
- [LangGraph Checkpoint PostgreSQL](https://reference.langchain.com/python/langgraph/checkpoints/) - PostgresSaver API
- [Gemini Structured Output Documentation](https://ai.google.dev/gemini-api/docs/structured-output) - response_schema with Pydantic
- [Gemini API Structured Outputs Blog](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-api-structured-outputs/) - 2026 improvements
- UmlsClient codebase analysis - services/umls-mcp-server/src/umls_mcp_server/umls_api.py
- Entity model codebase analysis - libs/shared/src/shared/models.py

### Secondary (MEDIUM confidence)

- [OMOPHub Python SDK](https://omophub.com/) - Multi-terminology API access (RxNorm, LOINC, ICD-10, HPO)
- [RxNorm API Documentation](https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html) - NLM RxNorm REST API
- [LOINC API Documentation](https://clinicaltables.nlm.nih.gov/apidoc/loinc/v3/doc.html) - NLM Clinical Tables LOINC API
- [Recent Developments in Clinical Terminologies](https://pmc.ncbi.nlm.nih.gov/articles/PMC6115234/) - SNOMED, LOINC, RxNorm integration

### Tertiary (LOW confidence)

- [LangGraph Persistence Guide](https://fast.io/resources/langgraph-persistence/) - Checkpointers overview
- [Understanding Healthcare Terminology Standards](https://www.linkedin.com/pulse/understanding-healthcare-terminology-standards-rxnorm-bhuwan-mittal-hl5jc) - RxNorm, ICD-10, SNOMED, LOINC, CPT

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already in project (SQLModel, httpx, LangGraph, React)
- Architecture: HIGH - LangGraph checkpointing documented, UmlsClient pattern proven
- Pitfalls: HIGH - Based on codebase analysis and official documentation
- Terminology APIs: MEDIUM - RxNorm/LOINC APIs verified, HPO/ICD-10 needs testing

**Research date:** 2026-02-16
**Valid until:** 2026-03-16 (30 days for stable stack, may need updates for LangGraph API changes)
