"""MLflow request tracing middleware for FastAPI.

Uses a pure ASGI middleware instead of Starlette's BaseHTTPMiddleware to
preserve contextvars propagation (required for MLflow tracing).
BaseHTTPMiddleware runs call_next in a thread pool, which breaks
contextvars and produces malformed trace spans.
"""

import logging
import os
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

# Skip tracing for health/readiness probes
_SKIP_PATHS = {"/health", "/ready", "/"}


class MLflowRequestMiddleware:
    """Pure ASGI middleware that creates MLflow traces for API requests."""

    def __init__(self, app: ASGIApp) -> None:
        """Store the ASGI app to call."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle request and optionally wrap it in an MLflow span."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in _SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
        if not tracking_uri:
            await self.app(scope, receive, send)
            return

        try:
            import mlflow
        except ImportError:
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "?")
        start = time.perf_counter()
        status_code = 500  # default until we see the actual response

        # Capture status code from response headers
        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        app_called = False
        try:
            with mlflow.start_span(
                name=f"{method} {path}",
                span_type="HTTP",
            ) as span:
                query = scope.get("query_string", b"").decode("utf-8", errors="replace")
                span.set_inputs({"method": method, "path": path, "query": query})

                app_called = True
                await self.app(scope, receive, send_wrapper)
                latency_ms = (time.perf_counter() - start) * 1000

                span.set_outputs(
                    {
                        "status_code": status_code,
                        "latency_ms": round(latency_ms, 2),
                    }
                )
        except Exception:
            logger.debug(
                "MLflow tracing failed, continuing without trace",
                exc_info=True,
            )
            if not app_called:
                await self.app(scope, receive, send)
