# Extraction Service

## Purpose
This service implements the criteria extraction workflow using Google's Gemini model. It processes clinical trial protocol PDFs to extract structured eligibility criteria using a LangGraph-based workflow.

## Architecture

The service uses a 4-node LangGraph workflow:

1. **Ingest**: Fetch PDF from GCS and parse to markdown
2. **Extract**: Call Gemini with structured output for criteria extraction
3. **Parse**: Post-process criteria with assertion refinement and deduplication
4. **Queue**: Persist CriteriaBatch and Criteria records to database

## Implementation

### State
The workflow uses `ExtractionState` TypedDict defined in `src/extraction_service/state.py`:
```python
class ExtractionState(TypedDict):
    protocol_id: str
    file_uri: str
    title: str
    markdown_content: str
    raw_criteria: list[dict[str, Any]]
    criteria_batch_id: str
    error: str | None
```

### Graph
The graph is defined in `src/extraction_service/graph.py` with conditional error routing:
```python
from langgraph.graph import StateGraph, START, END

workflow = StateGraph(ExtractionState)
workflow.add_node("ingest", ingest_node)
workflow.add_node("extract", extract_node)
workflow.add_node("parse", parse_node)
workflow.add_node("queue", queue_node)
```

## Running the Service
The service is triggered via the outbox pattern when a `ProtocolUploaded` event is published. The trigger handler is registered in `api-service/main.py` and invokes the graph asynchronously.
