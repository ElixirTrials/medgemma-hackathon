"""Extraction workflow state definition for the criteria extraction agent."""

from typing import Any

from typing_extensions import TypedDict


class ExtractionState(TypedDict):
    """State for the criteria extraction workflow.

    Carries data between LangGraph nodes:
    ingest -> extract -> parse -> queue

    Attributes:
        protocol_id: UUID of the protocol being processed.
        file_uri: GCS URI (gs://) or local path (local://) of the PDF.
        title: Protocol title from the upload metadata.
        markdown_content: Parsed PDF markdown (populated by ingest node).
        raw_criteria: Extracted criteria as dicts (populated by extract node).
        criteria_batch_id: ID of the persisted CriteriaBatch (populated by queue node).
        error: Error message if any node fails; enables conditional routing to END.
    """

    protocol_id: str
    file_uri: str
    title: str
    markdown_content: str
    raw_criteria: list[dict[str, Any]]
    criteria_batch_id: str
    error: str | None
