"""MLflow tracing helpers for pipeline nodes.

Provides a safe context manager that creates MLflow traces when available
and falls back to a no-op when MLflow is not configured or installed.

Each node creates its own separate top-level trace (not a child span),
tagged with protocol_id and run_id so traces from the same pipeline run
can be grouped and filtered in the MLflow UI.

IMPORTANT: ``mlflow.langchain.autolog()`` must NOT be enabled.  Autolog
wraps ``graph.ainvoke()`` in a single parent trace and all node spans
become children — producing one constantly-updating trace that only
appears after the full pipeline finishes.  Without autolog, each call to
``mlflow.start_span()`` inside a node creates an independent root trace
that is flushed to MLflow as soon as the context manager exits.

Grouping tags set on every trace:
    protocol_id  – groups all runs for a given protocol
    run_id       – groups all node traces from the same pipeline invocation
    node         – the node name (for easy filtering)
"""

from __future__ import annotations

import contextvars
import logging
import os
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

# ContextVar set once per pipeline invocation in trigger._run_pipeline().
# Every node's pipeline_span() reads it to tag traces with a shared run_id.
_pipeline_run_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "pipeline_run_id", default=""
)


def set_pipeline_run_id(run_id: str) -> None:
    """Set the current pipeline run_id (call before graph.ainvoke)."""
    _pipeline_run_id.set(run_id)


@contextmanager
def pipeline_span(
    name: str,
    span_type: str = "CHAIN",
    protocol_id: str = "",
):
    """Create a separate MLflow trace for a pipeline node.

    Each call creates its own top-level trace tagged with protocol_id
    and run_id, so individual node traces appear in MLflow as they
    complete rather than waiting for the entire pipeline to finish.

    Filter in MLflow UI:
        tags.protocol_id = "<id>"       – all runs for a protocol
        tags.run_id      = "<run_id>"   – single pipeline invocation

    Args:
        name: Trace/span name (e.g., "ingest_node", "ground_node").
        span_type: MLflow span type (default "CHAIN").
        protocol_id: Protocol ID to tag the trace with for session grouping.

    Yields:
        MLflow Span object or a no-op wrapper.
    """
    try:
        import mlflow

        if os.getenv("MLFLOW_TRACKING_URI"):
            with mlflow.start_span(name=name, span_type=span_type) as span:
                # Tag the trace for grouping/filtering in the MLflow UI.
                tags: dict[str, str] = {"node": name}
                if protocol_id:
                    tags["protocol_id"] = protocol_id
                run_id = _pipeline_run_id.get()
                if run_id:
                    tags["run_id"] = run_id
                try:
                    mlflow.update_current_trace(tags=tags)
                except Exception:
                    logger.warning("MLflow tag update failed", exc_info=True)
                yield span
                return
    except ImportError:
        logger.warning("mlflow not installed — tracing disabled")
    except Exception:
        logger.warning(
            "MLflow span creation failed, falling back to no-op", exc_info=True
        )

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
