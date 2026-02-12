---
phase: 16-multimodal-pdf-extraction
plan: 01
subsystem: extraction-service
tags: [multimodal, pdf-extraction, gemini, refactor]
dependency_graph:
  requires: [pymupdf4llm-removal, base64-encoding, langchain-multimodal]
  provides: [native-pdf-vision, improved-extraction-quality]
  affects: [ingest-node, extract-node, state-schema, prompts]
tech_stack:
  added: [langchain-core-messages, base64-pdf-encoding]
  patterns: [multimodal-content-parts, pdf-data-uri]
key_files:
  created: []
  modified:
    - services/extraction-service/src/extraction_service/state.py
    - services/extraction-service/src/extraction_service/nodes/ingest.py
    - services/extraction-service/src/extraction_service/nodes/extract.py
    - services/extraction-service/src/extraction_service/prompts/user.jinja2
    - services/extraction-service/src/extraction_service/trigger.py
decisions:
  - decision: Use base64 PDF data URIs with image_url content type for Gemini multimodal input
    rationale: Gemini 2.5 Flash accepts PDFs via image_url content parts with data:application/pdf;base64 URIs
    alternatives: [file-upload-api, separate-pdf-endpoint]
  - decision: Remove pymupdf4llm markdown conversion entirely
    rationale: Native PDF vision preserves layout, tables, and formatting better than lossy markdown conversion
    alternatives: [hybrid-approach, fallback-markdown]
  - decision: Add 18MB warning threshold before 20MB Gemini limit
    rationale: Provides operational visibility for large PDFs approaching token limits
    alternatives: [hard-reject, compression]
metrics:
  duration_minutes: 7
  tasks_completed: 2
  files_modified: 5
  tests_passing: 5
  completed_at: "2026-02-12T18:11:00Z"
---

# Phase 16 Plan 01: Multimodal PDF Extraction Summary

**One-liner:** Refactored extraction pipeline to send raw PDF bytes to Gemini as multimodal input, eliminating pymupdf4llm markdown conversion for improved extraction quality.

## What Was Built

Transformed the extraction pipeline from text-based (markdown) to multimodal (native PDF) by:

1. **State Schema Refactor**: Replaced `markdown_content: str` with `pdf_bytes: bytes` in ExtractionState
2. **Ingest Simplification**: Removed pymupdf4llm dependency from ingest_node, returning raw PDF bytes directly
3. **Extract Multimodal**: Refactored extract_node to send PDFs as base64-encoded multimodal content parts via HumanMessage
4. **Prompt Update**: Updated user.jinja2 to reference "the attached PDF document" instead of embedding markdown content
5. **Trigger Update**: Fixed initial state construction in trigger.py to use pdf_bytes

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Issue] trigger.py state initialization used old field**
- **Found during:** Task 2 verification
- **Issue:** trigger.py was initializing state with `markdown_content: ""` instead of `pdf_bytes: b""`
- **Fix:** Updated trigger.py line 76 to use `pdf_bytes: b""`
- **Files modified:** services/extraction-service/src/extraction_service/trigger.py
- **Commit:** 829078b

This was blocking because the state initialization would cause type errors when the graph tried to read pdf_bytes from state in extract_node.

## Implementation Details

### Task 1: State and Ingest Refactor
- Modified ExtractionState TypedDict to replace markdown_content with pdf_bytes field
- Simplified ingest_node to remove parse_pdf_to_markdown call and return raw bytes
- Updated user.jinja2 prompt to reference "attached PDF document" with only {{ title }} variable
- **Commit:** 5c1dbd4

### Task 2: Extract Node Multimodal Implementation
- Added base64 import and langchain_core.messages imports (HumanMessage, SystemMessage)
- Refactored _invoke_gemini signature to accept `list[SystemMessage | HumanMessage]` for multimodal support
- Implemented PDF base64 encoding with data URI construction (`data:application/pdf;base64,{pdf_base64}`)
- Added 18MB size warning (before 20MB Gemini limit)
- Constructed multimodal HumanMessage with content array: text prompt + PDF data URI
- Updated trigger.py state initialization to use pdf_bytes
- **Commit:** 829078b

### Key Technical Decisions

**Multimodal Content Structure:**
```python
HumanMessage(
    content=[
        {"type": "text", "text": user_prompt},
        {"type": "image_url", "image_url": {"url": pdf_data_uri}},
    ]
)
```

This structure is the correct LangChain format for passing PDFs to Gemini 2.5 Flash's multimodal API. The `image_url` type with PDF data URI is documented in LangChain's multimodal guide.

**Size Warning Threshold:**
Set at 18MB (90% of 20MB limit) to provide operational visibility before hitting Gemini's hard limit.

## Verification Results

### Lint & Type Checks
- ✅ `uv run ruff check services/extraction-service/` - All checks passed
- ✅ `uv run mypy` - Pre-existing import-untyped warnings only (api_service.storage, inference.factory, shared.resilience)

### Tests
- ✅ All 5 extraction graph tests passing
- ✅ Graph compilation, node routing, singleton pattern all verified

### Field Verification
- ✅ `pdf_bytes: bytes` exists in state.py
- ✅ `base64.b64encode` present in extract.py
- ✅ "attached PDF document" in user.jinja2
- ✅ No `markdown_content` references in src/ (excluding __pycache__)
- ✅ No `parse_pdf_to_markdown` references in nodes/
- ✅ parse.py, graph.py, schemas/criteria.py unchanged by my commits

### Unchanged Files Confirmed
The plan required these files remain untouched (they work with ExtractionResult schema unchanged):
- services/extraction-service/src/extraction_service/nodes/parse.py
- services/extraction-service/src/extraction_service/nodes/queue.py
- services/extraction-service/src/extraction_service/graph.py
- services/extraction-service/src/extraction_service/schemas/criteria.py

**Note:** queue.py has pre-existing changes from prior work (DetachedInstanceError fix) visible in git status, but no changes from this plan's commits.

## Impact Assessment

### Quality Improvements
- **Layout Preservation:** Native PDF vision analyzes text, tables, and formatting together
- **Table Extraction:** Gemini can see table structure directly instead of markdown approximation
- **Formatting Context:** Original document layout provides semantic hints for criteria identification

### Performance
- **Ingestion Speed:** Removed pymupdf4llm parsing step (faster ingestion)
- **Size Consideration:** Base64 encoding adds ~33% overhead, but most protocols under 5MB raw = ~6.6MB encoded (well under 20MB limit)

### Operational Monitoring
- Added size warning at 18MB to flag large PDFs before they hit Gemini limits
- Existing error handling, circuit breakers, and retry logic preserved

## Success Criteria Met

- ✅ ExtractionState uses `pdf_bytes: bytes` instead of `markdown_content: str`
- ✅ ingest_node returns PDF bytes without markdown conversion
- ✅ extract_node sends PDF as multimodal base64 content part alongside text prompt
- ✅ user.jinja2 references "the attached PDF document"
- ✅ system.jinja2 unchanged (already generic)
- ✅ parse_node, queue_node, graph.py, and schemas/criteria.py unchanged
- ✅ All existing tests pass
- ✅ ruff and mypy pass (baseline maintained)

## Next Steps

1. **Integration Testing:** Test with real clinical trial protocols to validate extraction quality improvements
2. **Size Monitoring:** Monitor encoded PDF sizes in production to validate 18MB threshold effectiveness
3. **Quality Comparison:** A/B test extraction accuracy between markdown and native PDF approaches
4. **Documentation:** Update API docs and developer guides to reflect multimodal architecture

## Self-Check: PASSED

**Files created:** None (refactor only)

**Files modified - all exist:**
- ✅ /Users/noahdolevelixir/Code/medgemma-hackathon/services/extraction-service/src/extraction_service/state.py
- ✅ /Users/noahdolevelixir/Code/medgemma-hackathon/services/extraction-service/src/extraction_service/nodes/ingest.py
- ✅ /Users/noahdolevelixir/Code/medgemma-hackathon/services/extraction-service/src/extraction_service/nodes/extract.py
- ✅ /Users/noahdolevelixir/Code/medgemma-hackathon/services/extraction-service/src/extraction_service/prompts/user.jinja2
- ✅ /Users/noahdolevelixir/Code/medgemma-hackathon/services/extraction-service/src/extraction_service/trigger.py

**Commits exist:**
- ✅ 5c1dbd4 (Task 1: state, ingest, prompts refactor)
- ✅ 829078b (Task 2: extract multimodal implementation)
