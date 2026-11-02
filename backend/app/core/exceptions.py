from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import correlation_id_var, get_logger

logger = get_logger(__name__)


class DomainError(Exception):
    """Base class for expected, user-facing failures.

    ``status`` and ``code`` are stable so the frontend can branch on ``code``
    instead of parsing messages.
    """

    status: int = HTTPStatus.BAD_REQUEST
    code: str = "domain_error"

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        # Carried separately so a rate-limited response can advertise when to
        # retry instead of leaving the client to guess.
        self.headers = headers or {}


class NotFoundError(DomainError):
    status = HTTPStatus.NOT_FOUND
    code = "not_found"


class ConflictError(DomainError):
    status = HTTPStatus.CONFLICT
    code = "conflict"


class TooManyRequestsError(DomainError):
    status = HTTPStatus.TOO_MANY_REQUESTS
    code = "rate_limited"


class AuthenticationError(DomainError):
    status = HTTPStatus.UNAUTHORIZED
    code = "authentication_failed"

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message)


class PermissionDeniedError(DomainError):
    status = HTTPStatus.FORBIDDEN
    code = "permission_denied"


class ValidationFailedError(DomainError):
    status = HTTPStatus.UNPROCESSABLE_ENTITY
    code = "validation_failed"


class SourceUnavailableError(DomainError):
    """A discovery source failed or is restricted.

    Reported to the user as-is. Never replaced with invented data.
    """

    status = HTTPStatus.BAD_GATEWAY
    code = "source_unavailable"

    def __init__(self, source_slug: str, reason: str) -> None:
        super().__init__(
            f"Source '{source_slug}' could not complete the request",
            details={"source": source_slug, "reason": reason},
        )


class JobStateError(DomainError):
    status = HTTPStatus.CONFLICT
    code = "invalid_job_state"


def _error_payload(
    code: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "correlation_id": correlation_id_var.get(),
        }
    }
    if details:
        payload["error"]["details"] = details
    return payload


_HTTP_ERROR_CODES: dict[int, str] = {
    int(HTTPStatus.UNAUTHORIZED): "authentication_failed",
    int(HTTPStatus.FORBIDDEN): "permission_denied",
    int(HTTPStatus.NOT_FOUND): "not_found",
    int(HTTPStatus.METHOD_NOT_ALLOWED): "method_not_allowed",
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content=_error_payload(exc.code, exc.message, exc.details),
            headers=exc.headers or None,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        # Unmatched routes and framework-level rejections arrive as
        # HTTPException. They must use the same envelope as domain errors,
        # otherwise the client needs two response-shape code paths.
        code = _HTTP_ERROR_CODES.get(exc.status_code, "request_failed")
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_payload(code, str(exc.detail)),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            content=_error_payload(
                "validation_failed",
                "Request payload did not validate",
                {"errors": exc.errors()},
            ),
        )

    @app.exception_handler(SQLAlchemyError)
    async def _handle_database_error(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
        # The driver message can contain connection strings; log it, never return it.
        logger.error("database_error", error_type=type(exc).__name__)
        return JSONResponse(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            content=_error_payload("database_error", "The request could not be completed"),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_error", error_type=type(exc).__name__)
        return JSONResponse(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            content=_error_payload("internal_error", "An unexpected error occurred"),
        )
