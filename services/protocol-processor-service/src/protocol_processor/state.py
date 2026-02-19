"""Pipeline state definition for the consolidated 5-node protocol processor.

Minimal flat state using JSON strings for complex data to minimize token usage
during LangGraph state serialization between nodes.
"""

from typing import Literal

from typing_extensions import TypedDict


class PipelineState(TypedDict):
    """Minimal state for the protocol processing pipeline.

    Fields are populated on-demand as the pipeline progresses through nodes:
    ingest -> extract -> parse -> ground -> persist

    Attributes:
        protocol_id: UUID of the protocol being processed. Always present.
        file_uri: GCS URI (gs://) or local path (local://) of the PDF.
        title: Protocol title from upload metadata. Always present.
        batch_id: UUID of the CriteriaBatch created by parse. None until then.
        pdf_bytes: Raw PDF bytes. Populated by ingest, consumed by extract.
        extraction_json: JSON string of extracted criteria from extract node.
        entities_json: JSON string of entities for grounding from parse node.
        grounded_entities_json: JSON string of grounded results from ground.
        status: Current pipeline status. Updated by each node.
        error: Fatal error message. Set on unrecoverable failure; routes to END.
        errors: Accumulated non-fatal errors (e.g. individual grounding failures).
            Partial failures are preserved alongside successes per user decision.
    """

    # Input (always present)
    protocol_id: str
    file_uri: str
    title: str

    # Created by parse node
    batch_id: str | None

    # Processing artifacts (populated on-demand)
    pdf_bytes: bytes | None  # Populated by ingest, used by extract
    extraction_json: str | None  # Populated by extract, used by parse
    entities_json: str | None  # Populated by parse/ground
    grounded_entities_json: str | None  # Populated by ground, used by persist

    # Re-extraction context (optional, only present during re-extraction)
    archived_reviewed_criteria: list[dict] | None

    # Ordinal resolution (populated by ordinal_resolve node)
    ordinal_proposals_json: str | None  # JSON of proposed ordinal scale configs

    # Output
    status: Literal["processing", "completed", "failed"]
    error: str | None
    errors: list[str]  # Accumulate partial failures per user decision
