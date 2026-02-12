"""Shared resilience patterns: circuit breakers and retry helpers.

Per-service circuit breakers for GCS, Gemini, UMLS MCP, and Vertex AI.
Each breaker trips after 3 consecutive failures (per CONTEXT.md decision)
and recovers after 60 seconds (Claude's discretion).
"""

import logging
import os

from pybreaker import CircuitBreaker, CircuitBreakerListener

logger = logging.getLogger(__name__)

# Recovery timeout: 60 seconds per research recommendation
_RECOVERY_TIMEOUT = 60
# Failure threshold: 3 consecutive failures per CONTEXT.md decision
_FAIL_MAX = 3


class MLflowCircuitBreakerListener(CircuitBreakerListener):
    """Log circuit breaker state changes to MLflow.

    Records when breakers trip (open), recover (half_open -> closed),
    or probe (half_open). Safe no-op if MLflow unavailable.
    """

    def state_change(self, cb, old_state, new_state):  # type: ignore[override]
        """Handle circuit breaker state change by logging to MLflow."""
        try:
            import mlflow

            tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
            if not tracking_uri:
                return

            with mlflow.start_span(
                name=f"circuit_breaker_{cb.name}",
                span_type="TOOL",
            ) as span:
                span.set_inputs({
                    "service": cb.name,
                    "old_state": str(old_state),
                    "new_state": str(new_state),
                    "fail_counter": cb.fail_counter,
                })
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
