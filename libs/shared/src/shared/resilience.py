"""Shared resilience patterns: circuit breakers and retry helpers.

Per-service circuit breakers for GCS, Gemini, UMLS MCP, Vertex AI, and MLflow.
Each breaker trips after 3 consecutive failures (per CONTEXT.md decision)
and recovers after 60 seconds (Claude's discretion), except MLflow which
uses a 120-second recovery timeout (per user decision).
"""

import logging
import os

from pybreaker import (
    STATE_CLOSED,
    STATE_HALF_OPEN,
    STATE_OPEN,
    CircuitBreaker,
    CircuitBreakerListener,
    CircuitBreakerState,
)

logger = logging.getLogger(__name__)

# Recovery timeout: 60 seconds per research recommendation
_RECOVERY_TIMEOUT = 60
# MLflow recovery timeout: 120 seconds per user decision (separate from other breakers)
_MLFLOW_RECOVERY_TIMEOUT = 120
# Failure threshold: 3 consecutive failures per CONTEXT.md decision
_FAIL_MAX = 3


class MLflowCircuitBreakerListener(CircuitBreakerListener):
    """Log circuit breaker state changes to MLflow.

    Records when breakers trip (open), recover (half_open -> closed),
    or probe (half_open). Safe no-op if MLflow unavailable.

    Special case: when the mlflow breaker itself changes state, log only to
    the Python logger (avoid recursion — can't log to MLflow if MLflow is down).
    This also implements the user decision for "log a single warning when it
    goes down, then suppress until recovery" since pybreaker fires state_change
    once per transition.
    """

    def state_change(
        self,
        cb: CircuitBreaker,
        old_state: CircuitBreakerState | None,
        new_state: CircuitBreakerState,
    ) -> None:
        """Handle circuit breaker state change by logging to MLflow or Python logger."""
        # MLflow breaker: log to Python logger only (avoid recursion)
        if cb.name == "mlflow":
            state_name = getattr(new_state, "name", str(new_state))
            if state_name == STATE_OPEN:
                logger.warning(
                    "MLflow circuit breaker OPEN - tracing disabled until recovery"
                )
            elif state_name == STATE_HALF_OPEN:
                logger.info("MLflow circuit breaker probing - attempting recovery")
            elif state_name == STATE_CLOSED:
                logger.info("MLflow circuit breaker CLOSED - tracing resumed")
            return

        # Other breakers: log to MLflow
        try:
            import mlflow

            tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
            if not tracking_uri:
                return

            with mlflow.start_span(
                name=f"circuit_breaker_{cb.name}",
                span_type="TOOL",
            ) as span:
                span.set_inputs(
                    {
                        "service": cb.name,
                        "old_state": str(old_state),
                        "new_state": str(new_state),
                        "fail_counter": cb.fail_counter,
                    }
                )
        except Exception:
            logger.debug("MLflow circuit breaker logging failed", exc_info=True)


# Create listener instance
_mlflow_listener = MLflowCircuitBreakerListener()

gemini_breaker = CircuitBreaker(
    fail_max=_FAIL_MAX,
    reset_timeout=_RECOVERY_TIMEOUT,
    name="gemini",
    listeners=[_mlflow_listener],
)

umls_breaker = CircuitBreaker(
    fail_max=_FAIL_MAX,
    reset_timeout=_RECOVERY_TIMEOUT,
    name="umls",
    listeners=[_mlflow_listener],
)

gcs_breaker = CircuitBreaker(
    fail_max=_FAIL_MAX,
    reset_timeout=_RECOVERY_TIMEOUT,
    name="gcs",
    listeners=[_mlflow_listener],
)

vertex_ai_breaker = CircuitBreaker(
    fail_max=_FAIL_MAX,
    reset_timeout=_RECOVERY_TIMEOUT,
    name="vertex_ai",
    listeners=[_mlflow_listener],
)

# ToolUniverse circuit breaker — higher fail threshold (10 vs 3) because
# ToolUniverse wraps multiple APIs and transient failures are more common.
# fail_max=10 per user decision (NOT reusing _FAIL_MAX=3 from other breakers).
tu_breaker = CircuitBreaker(
    fail_max=10,
    reset_timeout=60,
    name="tooluniverse",
    listeners=[_mlflow_listener],
)

# MLflow circuit breaker — 2-minute recovery timeout per user decision.
# Prevents repeated connection attempts to unreachable MLflow server.
# All MLflow operations (tracing, middleware, init) check this breaker.
mlflow_breaker = CircuitBreaker(
    fail_max=_FAIL_MAX,
    reset_timeout=_MLFLOW_RECOVERY_TIMEOUT,
    name="mlflow",
    listeners=[_mlflow_listener],
)


def mlflow_is_available() -> bool:
    """Check if MLflow circuit breaker allows operations.

    Returns True when the breaker is closed (healthy) or half-open (probing).
    Returns False when the breaker is open (MLflow known to be down).
    """
    return str(mlflow_breaker.current_state) != "open"
