"""MLflow tracing helpers for pipeline nodes.

Provides a safe context manager that creates MLflow traces when available
and falls back to a no-op when MLflow is not configured or installed.

Each node creates its own separate top-level trace (not a child span),
tagged with protocol_id so traces from the same pipeline run can be
grouped and filtered in the MLflow UI.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any


@contextmanager
def pipeline_span(
    name: str,
    span_type: str = "CHAIN",
    protocol_id: str = "",
):
    """Create a separate MLflow trace for a pipeline node.

    Each call creates its own top-level trace tagged with protocol_id,
    so individual node traces appear in MLflow as they complete rather
    than waiting for the entire pipeline to finish.

    Args:
        name: Trace/span name (e.g., "ingest_node", "ground_node").
        span_type: MLflow span type (default "CHAIN").
        protocol_id: Protocol ID to tag the trace with for session grouping.

    Yields:
        MLflow span object or a no-op wrapper.
    """
    try:
        import mlflow

        if os.getenv("MLFLOW_TRACKING_URI"):
            with mlflow.start_span(name=name, span_type=span_type) as span:
                if protocol_id:
                    try:
                        mlflow.update_current_trace(
                            tags={"protocol_id": protocol_id},
                        )
                    except Exception:
                        pass  # Tag failure is non-fatal
                yield span
                return
    except ImportError:
        pass
    except Exception:
        pass

    # Fallback: no-op span
    yield _NoOpSpan()


class _NoOpSpan:
    """No-op span that silently accepts MLflow span API calls."""

    def set_inputs(self, inputs: dict[str, Any]) -> None:
        pass

    def set_outputs(self, outputs: dict[str, Any]) -> None:
        pass

    def set_status(self, status: str) -> None:
        pass
