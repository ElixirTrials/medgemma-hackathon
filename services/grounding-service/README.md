# Grounding Service

## Purpose
This service implements an entity grounding workflow that links extracted medical entities to standardized UMLS concepts and SNOMED-CT codes using MedGemma and the UMLS MCP server.

## Implementation Guide

### 1. Define State
Create a typed state in `src/grounding_service/state.py`:
```python
from typing import TypedDict

class GroundingState(TypedDict):
    batch_id: str
    protocol_id: str
    criteria_ids: list[str]
    criteria_texts: list[dict]
    raw_entities: list[dict]
    grounded_entities: list[dict]
    entity_ids: list[str]
    error: str | None
```

### 2. Define Nodes
Create node functions in `src/grounding_service/nodes/`:
- `extract_entities.py` - Extract medical entities using MedGemma
- `ground_to_umls.py` - Link entities to UMLS concepts via MCP
- `map_to_snomed.py` - Map UMLS CUIs to SNOMED-CT codes
- `validate_confidence.py` - Validate and persist entities

### 3. Build Graph
Assemble the graph in `src/grounding_service/graph.py`.

## Running the Service
The grounding service is triggered automatically by the CriteriaExtracted event. It can be tested via the integration tests or by running the full extraction-grounding pipeline.
