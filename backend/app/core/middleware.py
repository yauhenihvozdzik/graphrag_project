"""Custom middleware for GraphRAG platform.

Includes metrics tracking, logging context, request profiling, and rate limiting.
Adapted from FastAPI-LangGraph template.
"""

import time
from typing import Callable

from aiolimiter import AsyncLimiter
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import settings
from app.core.logging import bind_context, clear_context, logger
from app.core.metrics import http_request_duration_seconds, http_requests_total


class MetricsMiddleware(BaseHTTPMiddleware):
    """Track HTTP request metrics."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            raise
        finally:
            duration = time.time() - start_time
            http_requests_total.labels(
                method=request.method,
                endpoint=request.url.path,
                status=status_code,
            ).inc()
            http_request_duration_seconds.labels(
                method=request.method,
                endpoint=request.url.path,
            ).observe(duration)
        return response


class LoggingContextMiddleware(BaseHTTPMiddleware):
    """Bind request context to structured logs."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("x-request-id", "")
        bind_context(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else "unknown",
        )
        try:
            response = await call_next(request)
            return response
        finally:
            clear_context()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using token-bucket algorithm via aiolimiter.

    Ограничивает количество запросов с одного IP-адреса.
    Формат rate_limit: ``60/minute`` или ``100/second``.
    """

    def __init__(self, app, rate_limit: str | None = None):
        super().__init__(app)
        rate_limit_str = rate_limit or settings.RATE_LIMIT
        self.limiter = self._parse_rate_limit(rate_limit_str)

    @staticmethod
    def _parse_rate_limit(rate_limit: str) -> AsyncLimiter:
        """Парсит строку формата ``count/period`` в ``AsyncLimiter``."""
        count, period = rate_limit.split("/")
        count = int(count)
        if period == "second":
            return AsyncLimiter(count, 1)
        return AsyncLimiter(count, 60)  # minute

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        try:
            async with self.limiter:
                return await call_next(request)
        except Exception as exc:
            # Ловим ТОЛЬКО исключения самого limiter'а (aiolimiter),
            # все остальные пробрасываем дальше в обработчики FastAPI
            if "aiolimiter" in type(exc).__module__:
                logger.warning("rate_limit_exceeded", client_ip=client_ip, path=request.url.path)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too Many Requests", "code": "RATE_LIMIT_EXCEEDED"},
                )
            raise
