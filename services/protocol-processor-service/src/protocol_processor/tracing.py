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
from typing import Any, Generator, cast

logger = logging.getLogger(__name__)

# ContextVar set once per pipeline invocation in trigger._run_pipeline().
# Every node's pipeline_span() reads it to tag traces with a shared run_id.
_pipeline_run_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "pipeline_run_id", default=""
)

# Experiment ID for pipeline traces. Set by trigger after _ensure_mlflow() so
# spans carry the experiment ID; export then uses it even from another thread.
_pipeline_experiment_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "pipeline_experiment_id", default=None
)


def set_pipeline_run_id(run_id: str) -> None:
    """Set the current pipeline run_id (call before graph.ainvoke)."""
    _pipeline_run_id.set(run_id)


def set_pipeline_experiment_id(experiment_id: str | None) -> None:
    """Set experiment ID for pipeline traces (after _ensure_mlflow in trigger)."""
    _pipeline_experiment_id.set(experiment_id)


@contextmanager
def pipeline_span(
    name: str,
    span_type: str = "CHAIN",
    protocol_id: str = "",
) -> Generator[Any, None, None]:
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
        from mlflow.entities.trace_location import MlflowExperimentLocation

        if os.getenv("MLFLOW_TRACKING_URI"):
            # Pass experiment_id on span so export uses it even from another thread.
            exp_id = _pipeline_experiment_id.get()
            trace_destination = (
                MlflowExperimentLocation(experiment_id=exp_id) if exp_id else None
            )
            with mlflow.start_span(
                name=name,
                span_type=span_type,
                trace_destination=trace_destination,
            ) as span:
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
                yield cast(Any, span)
                return
    except ImportError:
        logger.warning("mlflow not installed — tracing disabled")
    except Exception:
        logger.warning(
            "MLflow span creation failed, falling back to no-op", exc_info=True
        )

    # Fallback: no-op span
    yield cast(Any, _NoOpSpan())


class _NoOpSpan:
    """No-op span that silently accepts MLflow span API calls."""

    def set_inputs(self, inputs: dict[str, Any]) -> None:
        pass

    def set_outputs(self, outputs: dict[str, Any]) -> None:
        pass

    def set_status(self, status: str) -> None:
        pass


# ---------------------------------------------------------------------------
# LLM-level child span helpers
# ---------------------------------------------------------------------------

_TRUNCATE_LEN = 10_000


def _truncate(text: str, max_len: int = _TRUNCATE_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"... [truncated, {len(text)} total chars]"


class _LLMSpanCtx:
    """Wraps an MLflow span and exposes set_request / set_response helpers."""

    def __init__(self, span: Any, model_name: str) -> None:
        self._span = span
        self._model_name = model_name
        self._finalized = False

    def set_request(self, prompt_text: str) -> None:
        """Record the LLM request (prompt + model) as span inputs."""
        self._span.set_inputs(
            {
                "model": self._model_name,
                "prompt": _truncate(prompt_text),
            }
        )

    def set_response(
        self,
        response_text: str,
        usage: dict[str, int] | None = None,
    ) -> None:
        """Record the LLM response and optional token counts as span outputs."""
        outputs: dict[str, Any] = {"response": _truncate(response_text)}
        if usage:
            outputs.update(usage)
        self._span.set_outputs(outputs)
        self._finalized = True

    def _finalize(self) -> None:
        """Ensure outputs are set even if set_response was never called."""
        if not self._finalized:
            self._span.set_outputs({"response": "(not captured)"})


class _NoOpLLMSpan:
    """No-op replacement when MLflow is unavailable."""

    def set_request(self, prompt_text: str) -> None:
        pass

    def set_response(
        self,
        response_text: str,
        usage: dict[str, int] | None = None,
    ) -> None:
        pass


@contextmanager
def llm_span(name: str, model_name: str = "") -> Generator[Any, None, None]:
    """Create an MLflow child span for an individual LLM call.

    When called inside an active ``pipeline_span()``, this automatically
    becomes a child span (MLflow 3.x nests ``start_span`` calls).
    When MLflow is unavailable the context manager yields a no-op object.

    Args:
        name: Span name (e.g. ``"gemini_extraction"``).
        model_name: Model identifier to record in span inputs.

    Yields:
        ``_LLMSpanCtx`` (or ``_NoOpLLMSpan``) with ``set_request`` /
        ``set_response`` helpers.
    """
    try:
        import mlflow

        if os.getenv("MLFLOW_TRACKING_URI"):
            with mlflow.start_span(name=name, span_type="LLM") as span:
                ctx = _LLMSpanCtx(span, model_name)
                yield cast(Any, ctx)
                ctx._finalize()
                return
    except ImportError:
        pass  # mlflow is an optional dependency; fall through to no-op span
    except Exception:
        logger.debug("llm_span creation failed, falling back to no-op", exc_info=True)

    yield cast(Any, _NoOpLLMSpan())
