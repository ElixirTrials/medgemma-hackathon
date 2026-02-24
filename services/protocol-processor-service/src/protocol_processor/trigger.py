"""Unified outbox event handler for ProtocolUploaded events.

Replaces the two-service trigger pattern (extraction_service + grounding_service)
with a single consolidated handler that invokes the full 5-node pipeline:
ingest -> extract -> parse -> ground -> persist

Per user decision (v2.0): "Remove criteria_extracted outbox, retain protocol_uploaded"

The handler is synchronous (called by OutboxProcessor.poll_and_process) and
bridges to the async graph via asyncio.run(). This works without event loop
conflicts because the outbox processor runs handlers in a thread executor
via run_in_executor, so there is no existing event loop in the current thread.

Checkpointing: Each invocation generates a unique thread_id (protocol_id:uuid4)
and stores it in protocol.metadata_ so that retry_from_checkpoint can look it up.
This prevents checkpoint collision when re-extracting the same protocol.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from uuid import uuid4

from api_service.storage import engine  # type: ignore[import-untyped]
from shared.exceptions import AuthExpiredError
from shared.models import Protocol
from sqlmodel import Session

logger = logging.getLogger(__name__)


def _cleanup_orphan_traces() -> None:
    """Close stale IN_PROGRESS MLflow traces from previous crashed runs.

    Runs once at module import (service startup). Idempotent -- safe to
    call multiple times. Only closes traces older than 1 hour to avoid
    closing currently-running pipelines.
    """
    import time as _time

    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        return
    try:
        import mlflow

        client = mlflow.MlflowClient()
        cutoff_ms = int((_time.time() - 3600) * 1000)  # 1 hour ago

        # MLflow 3.x: search for traces with IN_PROGRESS status
        try:
            traces = client.search_traces(
                filter_string="status = 'IN_PROGRESS'",
                max_results=50,
            )
        except (AttributeError, TypeError):
            # search_traces may not exist or have different signature
            logger.warning("MLflow search_traces API not available for orphan cleanup")
            return

        closed = 0
        for trace in traces:
            trace_ts = getattr(trace.info, "timestamp_ms", None) or 0
            if trace_ts < cutoff_ms:
                try:
                    client.end_trace(
                        request_id=trace.info.request_id,
                        status="ERROR",
                    )
                    closed += 1
                except Exception:
                    logger.debug(
                        "Trace %s already closed, skipping",
                        trace.info.request_id,
                    )
        if closed:
            logger.info(
                "Startup orphan cleanup: closed %d stale IN_PROGRESS trace(s)",
                closed,
            )
    except Exception:
        logger.warning("Orphan trace cleanup failed (non-fatal)", exc_info=True)


# Run once at startup to clean up orphaned traces from previous crashes
_cleanup_orphan_traces()


_mlflow_experiment_name: str | None = None


def _get_experiment_name() -> str:
    """Return MLflow experiment name: one per day so all runs share it."""
    global _mlflow_experiment_name
    if _mlflow_experiment_name is None:
        from datetime import datetime, timezone

        # Date only: one experiment per day; avoids one per process/restart.
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        _mlflow_experiment_name = f"protocol-processing-{date_str}"
    return _mlflow_experiment_name


def _ensure_mlflow() -> bool:
    """Ensure MLflow tracking is configured in the current thread.

    Uses one experiment per day (protocol-processing-YYYYMMDD) so all runs
    and workers share the same experiment in the MLflow UI.
    """
    try:
        import mlflow

        tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
            client = mlflow.MlflowClient()

            # Restore the Default experiment (id "0") if deleted.
            try:
                default_exp = client.get_experiment("0")
                if default_exp and default_exp.lifecycle_stage == "deleted":
                    client.restore_experiment("0")
            except Exception:
                # Non-fatal: default experiment restore is best-effort
                logger.debug(
                    "Could not restore default MLflow experiment",
                    exc_info=True,
                )

            experiment_name = _get_experiment_name()
            try:
                mlflow.set_experiment(experiment_name)
            except mlflow.exceptions.MlflowException:
                # Experiment in deleted state — restore and reuse.
                exp = client.get_experiment_by_name(experiment_name)
                if exp and exp.lifecycle_stage == "deleted":
                    client.restore_experiment(exp.experiment_id)
                    mlflow.set_experiment(experiment_name)
                else:
                    raise
            return True
    except ImportError:
        logger.warning("mlflow not installed — tracing disabled")
    except Exception:
        logger.warning("MLflow setup failed — tracing disabled", exc_info=True)
    return False


def _is_auth_expired_error(e: BaseException) -> bool:
    """Return True if the exception is or was caused by credential refresh failure.

    Checks the exception and its __cause__ chain so gRPC-wrapped RefreshErrors
    are detected. Used to avoid retries and to raise AuthExpiredError for the outbox.
    """
    try:
        from google.auth.exceptions import RefreshError
    except ImportError:
        return False
    exc: BaseException | None = e
    while exc is not None:
        if isinstance(exc, RefreshError):
            return True
        exc = getattr(exc, "__cause__", None)
    return False


def _categorize_pipeline_error(e: Exception) -> str:
    """Convert exception to human-readable pipeline error reason.

    Combines extraction and grounding error categorization from both
    the old extraction_service and grounding_service triggers.

    Args:
        e: The exception that occurred during pipeline execution.

    Returns:
        Human-readable error message for the user.
    """
    if isinstance(e, DependencyCheckError):
        return f"Infrastructure dependency unavailable: {e}"

    error_str = str(e).lower()

    # PDF / extraction errors
    if "pdf" in error_str or "pymupdf" in error_str:
        return "PDF text quality too low or file corrupted"
    if "gcs" in error_str or "storage" in error_str or "bucket" in error_str:
        return "File storage service unavailable"

    # Auth / credential errors (do not retry — trigger login in UI)
    if "credential" in error_str or "auth" in error_str or "refresherror" in error_str:
        return "Google credentials expired — sign in again"

    # UMLS / grounding errors
    if "mcp" in error_str or "subprocess" in error_str:
        return "UMLS grounding service unavailable"
    if "concept_linking" in error_str or "concept_search" in error_str:
        return "UMLS terminology service unavailable"

    # Generic transient errors
    if "circuit" in error_str:
        return "AI service temporarily unavailable"
    if "timeout" in error_str or "timed out" in error_str:
        return "Processing timed out"
    if "parse" in error_str:
        return "Protocol parsing failed"

    return f"Pipeline failed: {type(e).__name__}"


def _update_protocol_failed(
    protocol_id: str,
    reason: str,
    error_category: str,
    exception_type: str,
) -> None:
    """Update protocol status to extraction_failed with error metadata.

    Args:
        protocol_id: Protocol ID to update.
        reason: Human-readable error reason.
        error_category: Short category string for the error type.
        exception_type: Python exception class name.
    """
    try:
        with Session(engine) as session:
            protocol = session.get(Protocol, protocol_id)
            if protocol:
                protocol.status = "extraction_failed"
                protocol.error_reason = reason
                protocol.metadata_ = {
                    **protocol.metadata_,
                    "error": {
                        "category": error_category,
                        "reason": reason,
                        "exception_type": exception_type,
                    },
                }
                session.add(protocol)
                session.commit()
    except Exception:
        logger.exception(
            "Failed to update protocol %s status to extraction_failed",
            protocol_id,
        )


async def _run_pipeline(
    initial_state: dict[str, Any],
    config: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Run the pipeline graph with MLflow tracing inside the async context.

    MLflow ContextVars must be created in the same async context as the
    LangGraph invocation. asyncio.run() creates an isolated context, so
    we initialize MLflow tracing HERE (inside asyncio.run) rather than
    in the sync caller.

    Each pipeline node creates its own separate MLflow trace tagged with
    protocol_id and run_id, so traces appear in the MLflow UI as they
    complete rather than waiting for the entire pipeline. Filter by the
    run_id tag to see all traces from a single pipeline invocation.
    """
    from protocol_processor.graph import get_graph
    from protocol_processor.tracing import set_pipeline_run_id

    graph = await get_graph()

    # MLflow tracing: do NOT enable langchain.autolog() here.
    # Autolog wraps the entire ainvoke() in a single trace that only
    # appears in MLflow after the full pipeline completes.  Instead,
    # each node creates its own independent trace via pipeline_span()
    # so traces appear in real-time as nodes finish.
    # MLflow for this thread is set by handle_protocol_uploaded() via
    # _ensure_mlflow() (protocol-processing-YYYYMMDD). Do not call
    # _ensure_mlflow() again here.

    # Set run_id so every node's pipeline_span() tags its trace with the
    # same identifier.  Uses the thread_id which is "{protocol_id}:{uuid4}".
    thread_id = config.get("configurable", {}).get("thread_id", "")
    if thread_id:
        set_pipeline_run_id(thread_id)

    return await graph.ainvoke(initial_state, config)


class DependencyCheckError(RuntimeError):
    """Raised when a required infrastructure dependency is unreachable."""


def _preflight_check() -> None:
    """Verify infrastructure dependencies are reachable before starting the pipeline.

    Checks: PostgreSQL (main DB), OMOP vocabulary DB, and MLflow tracking server.
    Raises DependencyCheckError on the first failure so the pipeline never starts
    and no API calls (Gemini, ToolUniverse, etc.) are wasted.
    """
    import urllib.request

    from sqlalchemy import text

    # 1. Main database (required for persist, parse, etc.)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise DependencyCheckError(
            f"Main database (DATABASE_URL) is not reachable: {exc}"
        ) from exc

    # 2. OMOP vocabulary database (required for dual grounding)
    try:
        from protocol_processor.tools.omop_mapper import _get_omop_engine

        omop_engine = _get_omop_engine()
        with omop_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise DependencyCheckError(
            f"OMOP vocabulary database (OMOP_VOCAB_URL) is not reachable: {exc}"
        ) from exc

    # 3. MLflow tracking server (required for observability)
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        raise DependencyCheckError(
            "MLFLOW_TRACKING_URI environment variable is not set"
        )
    try:
        req = urllib.request.Request(f"{tracking_uri}/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status >= 400:
                raise DependencyCheckError(
                    f"MLflow health check returned HTTP {resp.status}"
                )
    except DependencyCheckError:
        raise
    except Exception as exc:
        raise DependencyCheckError(
            f"MLflow tracking server ({tracking_uri}) is not reachable: {exc}"
        ) from exc

    logger.info("Pre-flight checks passed: DB, OMOP, MLflow all reachable")


def handle_protocol_uploaded(payload: dict[str, Any]) -> None:
    """Handle a ProtocolUploaded event by running the full pipeline.

    Constructs the initial PipelineState from the event payload and
    invokes the consolidated 5-node LangGraph workflow via asyncio.run().

    Uses protocol_id as the LangGraph thread_id so that retry_from_checkpoint
    can locate the saved checkpoint by protocol_id alone.

    Replaces both extraction_service.trigger.handle_protocol_uploaded and
    grounding_service.trigger.handle_criteria_extracted from the v1.x
    two-service architecture.

    Args:
        payload: Event payload dict containing protocol_id, file_uri, and title.

    Raises:
        DependencyCheckError: If DB, OMOP, or MLflow is unreachable.
        Exception: Re-raised after logging to let the outbox processor
            mark the event as failed for retry.
    """
    # Pre-flight: verify all infrastructure dependencies are up before
    # spending any Gemini/ToolUniverse API calls.
    _preflight_check()

    # Set MLflow experiment for this worker thread (protocol-processing-YYYYMMDD).
    # Without this, the thread would use default experiment ID 0, which may be deleted.
    _ensure_mlflow()
    # So pipeline spans carry the experiment ID and export works from any thread.
    try:
        import mlflow

        from protocol_processor.tracing import set_pipeline_experiment_id

        exp = mlflow.get_experiment_by_name(_get_experiment_name())
        if exp:
            set_pipeline_experiment_id(exp.experiment_id)
        else:
            set_pipeline_experiment_id(None)
    except Exception:
        logger.debug("Could not set pipeline experiment ID for tracing", exc_info=True)

    protocol_id = payload.get("protocol_id", "unknown")
    logger.info(
        "Handling ProtocolUploaded event for protocol %s (consolidated pipeline)",
        protocol_id,
    )

    try:
        # Generate unique thread_id per pipeline run to prevent checkpoint collision
        # on re-extraction (same protocol_id would resume old completed checkpoint)
        thread_id = f"{protocol_id}:{uuid4()}"

        initial_state: dict[str, Any] = {
            "protocol_id": payload["protocol_id"],
            "file_uri": payload["file_uri"],
            "title": payload["title"],
            "batch_id": None,
            "pdf_bytes": None,
            "extraction_json": None,
            "entities_json": None,
            "grounded_entities_json": None,
            "archived_reviewed_criteria": payload.get("archived_reviewed_criteria"),
            "status": "processing",
            "error": None,
            "errors": [],
        }

        # Store thread_id in protocol metadata for retry_from_checkpoint lookup
        try:
            with Session(engine) as session:
                protocol = session.get(Protocol, protocol_id)
                if protocol:
                    meta = protocol.metadata_ or {}
                    protocol.metadata_ = {
                        **meta,
                        "pipeline_thread_id": thread_id,
                    }
                    session.add(protocol)
                    session.commit()
        except Exception:
            logger.warning(
                "Failed to store pipeline_thread_id for protocol %s",
                protocol_id,
            )

        config = {"configurable": {"thread_id": thread_id}}

        asyncio.run(_run_pipeline(initial_state, config, payload))

        logger.info(
            "Protocol pipeline completed for protocol %s",
            protocol_id,
        )

    except Exception as e:
        logger.exception(
            "Protocol pipeline failed for protocol %s",
            protocol_id,
        )
        reason = _categorize_pipeline_error(e)
        # Auth expiry: do not retry; outbox marks dead_letter, UI shows login.
        is_auth_expired = _is_auth_expired_error(e)
        category = "auth_expired" if is_auth_expired else "pipeline_failed"
        _update_protocol_failed(
            protocol_id,
            reason,
            category,
            type(e).__name__,
        )
        if is_auth_expired:
            raise AuthExpiredError("Google credentials expired — sign in again") from e
        raise


async def retry_from_checkpoint(protocol_id: str) -> dict[str, Any]:
    """Resume pipeline from last checkpoint for a failed protocol.

    Passes None as the input state to graph.ainvoke, which tells LangGraph
    to resume from the last saved checkpoint for the given thread_id instead
    of starting from scratch. Reads thread_id from protocol.metadata_ where
    it was stored during the original pipeline invocation.

    Args:
        protocol_id: Protocol ID — used to look up thread_id from metadata.

    Returns:
        Final pipeline state dict after resuming from checkpoint.
    """
    with Session(engine) as session:
        protocol = session.get(Protocol, protocol_id)
        if not protocol:
            raise ValueError(f"Protocol {protocol_id} not found")
        thread_id = (protocol.metadata_ or {}).get("pipeline_thread_id", protocol_id)

    from protocol_processor.graph import get_graph

    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    # Pass None as input — LangGraph resumes from last checkpoint
    result = await graph.ainvoke(None, config)
    return result
