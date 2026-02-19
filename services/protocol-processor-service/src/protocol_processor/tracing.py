"""MLflow tracing helpers for pipeline nodes.

Provides a safe context manager that creates MLflow spans when available
and falls back to a no-op when MLflow is not configured or installed.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any


@contextmanager
def pipeline_span(name: str, span_type: str = "CHAIN"):
    """Create an MLflow span if MLflow is configured, otherwise no-op.

    Yields a span-like object. If MLflow is unavailable, yields a simple
    dict that silently accepts set_inputs/set_outputs calls.

    Args:
        name: Span name (e.g., "ingest_node", "ground_node").
        span_type: MLflow span type (default "CHAIN").

    Yields:
        MLflow span object or a no-op wrapper.
    """
    try:
        import mlflow

        if os.getenv("MLFLOW_TRACKING_URI"):
            with mlflow.start_span(name=name, span_type=span_type) as span:
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
