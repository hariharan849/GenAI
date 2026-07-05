import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from api.metrics import ERROR_COUNTER, REQUEST_COUNTER, REQUEST_LATENCY, REQUEST_LATENCY_SIMPLE

logger = logging.getLogger(__name__)

SERVICE_NAME = "rag-api"


class MetricsMiddleware(BaseHTTPMiddleware):
    """Logs every request with method, path, status code, and duration."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        should_record = request.url.path != "/metrics"

        try:
            response = await call_next(request)
        except Exception:
            duration_seconds = time.perf_counter() - start
            if should_record:
                self._record_request(request, 500, duration_seconds)
                logger.exception(
                    "request",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "endpoint": self._endpoint_label(request),
                        "status_code": 500,
                        "duration_ms": round(duration_seconds * 1000, 2),
                    },
                )
            raise

        duration_seconds = time.perf_counter() - start

        if should_record:
            self._record_request(request, response.status_code, duration_seconds)
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "endpoint": self._endpoint_label(request),
                    "status_code": response.status_code,
                    "duration_ms": round(duration_seconds * 1000, 2),
                },
            )

        return response

    @staticmethod
    def _endpoint_label(request: Request) -> str:
        route = request.scope.get("route")
        return getattr(route, "path", None) or request.url.path

    def _record_request(self, request: Request, status_code: int, duration_seconds: float) -> None:
        endpoint = self._endpoint_label(request)
        status = str(status_code)

        REQUEST_COUNTER.labels(SERVICE_NAME, request.method, endpoint, status).inc()
        REQUEST_LATENCY.labels(SERVICE_NAME, request.method, endpoint, status).observe(duration_seconds)
        REQUEST_LATENCY_SIMPLE.observe(duration_seconds)

        if 400 <= status_code < 500:
            ERROR_COUNTER.labels(SERVICE_NAME, "warning").inc()
        elif status_code >= 500:
            ERROR_COUNTER.labels(SERVICE_NAME, "critical").inc()
