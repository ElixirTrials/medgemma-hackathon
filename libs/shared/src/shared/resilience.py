"""Shared resilience patterns: circuit breakers and retry helpers.

Per-service circuit breakers for GCS, Gemini, UMLS MCP, and Vertex AI.
Each breaker trips after 3 consecutive failures (per CONTEXT.md decision)
and recovers after 60 seconds (Claude's discretion).
"""

import logging

from pybreaker import CircuitBreaker

logger = logging.getLogger(__name__)

# Recovery timeout: 60 seconds per research recommendation
_RECOVERY_TIMEOUT = 60
# Failure threshold: 3 consecutive failures per CONTEXT.md decision
_FAIL_MAX = 3

gemini_breaker = CircuitBreaker(
    fail_max=_FAIL_MAX,
    reset_timeout=_RECOVERY_TIMEOUT,
    name="gemini",
)

umls_breaker = CircuitBreaker(
    fail_max=_FAIL_MAX,
    reset_timeout=_RECOVERY_TIMEOUT,
    name="umls",
)

gcs_breaker = CircuitBreaker(
    fail_max=_FAIL_MAX,
    reset_timeout=_RECOVERY_TIMEOUT,
    name="gcs",
)

vertex_ai_breaker = CircuitBreaker(
    fail_max=_FAIL_MAX,
    reset_timeout=_RECOVERY_TIMEOUT,
    name="vertex_ai",
)
