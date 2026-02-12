"""MLflow request tracing middleware for FastAPI.

Traces every API request with method, path, status code, latency,
and user info. Skips health/ready endpoints to avoid noise.
"""

import logging
import os
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)

# Skip tracing for health/readiness probes
_SKIP_PATHS = {"/health", "/ready", "/"}


class MLflowRequestMiddleware(BaseHTTPMiddleware):
    """Middleware that creates MLflow traces for API requests."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Trace the request to MLflow if configured."""
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()

        try:
            import mlflow

            tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
            if not tracking_uri:
                # MLflow not configured, skip tracing
                return await call_next(request)

            with mlflow.start_span(
                name=f"{request.method} {request.url.path}",
                span_type="HTTP",
            ) as span:
                span.set_inputs({
                    "method": request.method,
                    "path": request.url.path,
                    "query": str(request.query_params),
                })

                response = await call_next(request)
                latency_ms = (time.perf_counter() - start) * 1000

                span.set_outputs({
                    "status_code": response.status_code,
                    "latency_ms": round(latency_ms, 2),
                })

                return response

        except ImportError:
            logger.debug("mlflow not installed, skipping request tracing")
            return await call_next(request)
        except Exception:
            # Never let tracing failure break the request
            logger.debug(
                "MLflow tracing failed, continuing without trace",
                exc_info=True,
            )
            response = await call_next(request)
            return response
