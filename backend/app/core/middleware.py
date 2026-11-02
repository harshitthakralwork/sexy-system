from __future__ import annotations

import time
import uuid
from typing import Any

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import correlation_id_var
from app.shared.url_safety import CORRELATION_ID_PATTERN

CORRELATION_HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware:
    """Bind one id to a request and echo it back, so a user report maps to logs.

    Pure ASGI rather than ``BaseHTTPMiddleware``: background jobs need the same
    context propagation and this keeps it off the streaming path.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        incoming = headers.get(CORRELATION_HEADER.lower())
        # The header is attacker-controlled. Length alone is not enough: escape
        # sequences survive JSON encoding and reach a terminal log viewer, and the
        # value is echoed back in a response header. Anything unexpected is
        # discarded and a fresh id is minted.
        correlation_id = (
            incoming
            if incoming and CORRELATION_ID_PATTERN.fullmatch(incoming)
            else uuid.uuid4().hex
        )
        token = correlation_id_var.set(correlation_id)

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                mutable = list(message.get("headers", []))
                mutable.append((CORRELATION_HEADER.lower().encode(), correlation_id.encode()))
                message = {**message, "headers": mutable}
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            correlation_id_var.reset(token)


class RequestResponseLoggingMiddleware:
    """One structured log line per request, tagged with the correlation id."""

    def __init__(self, app: ASGIApp, logger: Any | None = None) -> None:
        self.app = app
        self.logger = logger or structlog.get_logger("sparkxflow.http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        observed_status = {"status": 0}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                observed_status["status"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            self.logger.info(
                "request_completed",
                method=scope.get("method"),
                path=scope.get("path"),
                status=observed_status["status"],
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
