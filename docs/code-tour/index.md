# Code Tour

A linear walkthrough of the key code paths in ElixirTrials, from upload to review. Each "slide" covers one critical module.

---

## Slide 1: Upload Dialog

> **As a researcher**, I want to upload a protocol PDF so the system can extract its eligibility criteria.

**File**: `apps/hitl-ui/src/components/ProtocolUploadDialog.tsx`

```tsx
const uploadMutation = useUploadProtocol();

const handleUpload = useCallback(async () => {
    if (!selectedFile) return;
    try {
        await uploadMutation.mutateAsync({ file: selectedFile });
        setSelectedFile(null);
        onOpenChange(false);
    } catch (err) {
        setError(err instanceof Error ? err.message : 'Upload failed');
    }
}, [selectedFile, uploadMutation, onOpenChange]);
```

**Why this matters**: The upload dialog is the entry point for all protocol processing. It validates PDF type and 50 MB size limit client-side before hitting the API. The `useUploadProtocol` hook handles the two-step signed URL flow (upload → confirm).

---

## Slide 2: Protocol Upload API

> **As the API**, I create a protocol record and generate a signed URL for direct browser-to-storage upload.

**File**: `services/api-service/src/api_service/protocols.py:136`

```python
@router.post("/upload", response_model=UploadResponse)
def upload_protocol(body: UploadRequest, db: Session = Depends(get_db)):
    signed_url, gcs_path = generate_upload_url(
        filename=body.filename, content_type=body.content_type,
    )
    protocol = Protocol(title=title, file_uri=gcs_path, status="uploaded")
    db.add(protocol)
    db.commit()
    return UploadResponse(protocol_id=protocol.id, upload_url=signed_url, ...)
```

**Why this matters**: The upload is a two-phase process. Phase 1 creates the DB record and returns a signed URL. Phase 2 (`confirm-upload`) triggers processing via the outbox. This prevents processing a file that was never actually uploaded.

---

## Slide 3: Outbox Wiring

> **As the API service**, I connect the outbox processor to the pipeline trigger at startup.

**File**: `services/api-service/src/api_service/main.py:81-93`

```python
processor = OutboxProcessor(
    engine=engine,
    handlers={
        "protocol_uploaded": [handle_protocol_uploaded],
    },
)
task = asyncio.create_task(processor.start())
```

**Why this matters**: This is the bridge between the synchronous API world and the async pipeline. The outbox pattern ensures at-least-once delivery — if the API crashes after writing the outbox event but before the handler runs, the event will be picked up on restart. Note: `criteria_extracted` was removed in v2.0; `protocol_uploaded` is the only event.

---

## Slide 4: Pipeline Trigger

> **As the outbox processor**, I dispatch events to the LangGraph pipeline.

**File**: `services/protocol-processor-service/src/protocol_processor/trigger.py:214`

```python
def handle_protocol_uploaded(payload: dict[str, Any]) -> None:
    thread_id = f"{protocol_id}:{uuid4()}"
    initial_state = {
        "protocol_id": payload["protocol_id"],
        "file_uri": payload["file_uri"],
        "title": payload["title"],
        "status": "processing",
        "error": None,
        "errors": [],
        ...
    }
    config = {"configurable": {"thread_id": thread_id}}
    asyncio.run(_run_pipeline(initial_state, config, payload))
```

**Why this matters**: The trigger bridges sync (outbox handler) to async (LangGraph) via `asyncio.run()`. Each run gets a unique `thread_id` (protocol_id + uuid4) to prevent checkpoint collision on re-extraction. The thread_id is stored in protocol metadata for retry support.

---

## Slide 5: Ingest Node

> **As the first pipeline node**, I fetch the PDF bytes from storage.

**File**: `services/protocol-processor-service/src/protocol_processor/nodes/ingest.py`

```python
async def ingest_node(state: PipelineState) -> dict[str, Any]:
    pdf_bytes = await fetch_pdf_bytes(state["file_uri"])
    # Update protocol status in DB
    with Session(engine) as session:
        protocol = session.get(Protocol, state["protocol_id"])
        protocol.status = "extracting"
        session.commit()
    return {"pdf_bytes": pdf_bytes, "status": "processing"}
```

**Why this matters**: Ingest is the first node with external I/O (storage fetch). If the file doesn't exist or storage is down, this is where it fails — with a clear `error` that routes the pipeline to END.

---

## Slide 6: Extract Node

> **As the extract node**, I send the PDF to Gemini and get structured criteria back.

**File**: `services/protocol-processor-service/src/protocol_processor/nodes/extract.py`

```python
async def extract_node(state: PipelineState) -> dict[str, Any]:
    result = await extract_criteria_structured(
        pdf_bytes=state["pdf_bytes"],
        protocol_title=state["title"],
    )
    return {
        "extraction_json": json.dumps(result),
        "pdf_bytes": None,  # Clear to reduce checkpoint size
        "status": "processing",
    }
```

**Why this matters**: This is the core AI step — Gemini 2.5 Flash reads the PDF and returns structured JSON with inclusion/exclusion criteria, categories, and confidence scores. The `pdf_bytes` are explicitly cleared after extraction to keep LangGraph checkpoints small.

---

## Slide 7: Parse Node

> **As the parse node**, I create database records and decompose criteria into entities.

**File**: `services/protocol-processor-service/src/protocol_processor/nodes/parse.py`

```python
# Phase A: Create batch and criteria records
batch = CriteriaBatch(protocol_id=protocol_id)
session.add(batch)
for item in criteria_list:
    criterion = Criteria(batch_id=batch.id, text=item["text"], ...)
    session.add(criterion)

# Phase B: Async entity decomposition (outside DB session)
tasks = [decompose_entities_from_criterion(c) for c in criteria]
results = await asyncio.gather(*tasks)
```

**Why this matters**: Parse separates DB persistence (fast, transactional) from LLM decomposition (slow, parallelized). Entity decomposition runs with a semaphore of 4 to limit concurrent Gemini calls. The DB session is closed before LLM calls to avoid holding connections during I/O.

---

## Slide 8: Ground Node

> **As the ground node**, I link entities to standard terminologies using dual grounding.

**File**: `services/protocol-processor-service/src/protocol_processor/nodes/ground.py`

```python
async def _ground_entity_with_retry(entity, semaphore):
    async with semaphore:
        # Dual grounding: UMLS + OMOP in parallel
        umls_result, omop_result = await asyncio.gather(
            terminology_router.search(entity),
            omop_mapper.resolve(entity),
        )
        result = _reconcile_dual_grounding(umls_result, omop_result)

        # Agentic retry if confidence < 0.5
        if result.confidence < 0.5:
            for attempt in range(3):
                # MedGemma reasoning loop
                ...
```

**Why this matters**: Grounding is the most complex node — dual sourcing, reconciliation, and agentic retries. Error accumulation means one failed entity doesn't block the others. This is where the system gets the SNOMED, LOINC, RxNorm, and OMOP codes needed for export.

---

## Slide 9: Structure Node

> **As the structure node**, I build expression trees from grounded criteria.

**File**: `services/protocol-processor-service/src/protocol_processor/nodes/structure.py`

```python
tree = await build_expression_tree(
    criterion_text=criterion.text,
    field_mappings=field_mappings,
    criterion_id=criterion.id,
    protocol_id=protocol_id,
    inclusion_exclusion=inclusion_exclusion,
    session=session,
)
criterion.structured_criterion = tree.model_dump()
```

**Why this matters**: Structure transforms flat criteria into queryable expression trees. Gemini detects AND/OR/NOT logic, then the builder creates `AtomicCriterion`, `CompositeCriterion`, and `CriterionRelationship` records. These trees power the CIRCE and FHIR exports.

---

## Slide 10: Review Page

> **As a clinician**, I review extracted criteria side-by-side with the source PDF.

**File**: `apps/hitl-ui/src/screens/ReviewPage.tsx`

```tsx
<PanelGroup direction="horizontal">
    <Panel defaultSize={50}>
        <PdfViewer
            url={pdfData.url}
            targetPage={activeCriterion?.page_number ?? null}
            highlightText={activeCriterion?.text ?? null}
        />
    </Panel>
    <PanelResizeHandle />
    <Panel defaultSize={50}>
        {inclusionCriteria.map((c) => (
            <CriterionCard
                criterion={c}
                onAction={handleAction}
                onCriterionClick={handleCriterionClick}
                isActive={activeCriterion?.id === c.id}
            />
        ))}
    </Panel>
</PanelGroup>
```

**Why this matters**: The review page is where human judgment meets AI output. Clicking a criterion scrolls the PDF to the source page and highlights the text. Criteria are grouped by inclusion/exclusion with pending items sorted first. The progress bar shows overall review completion.
