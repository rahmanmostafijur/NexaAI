"""Application error hierarchy and HTTP error envelope handlers.

Every error returned to clients has the shape
`{"error": {"code": ..., "message": ..., "request_id": ...}}`.
Unexpected exceptions are logged with full detail but only a generic message
is returned, so stack traces never reach end users.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    retryable: bool = False

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    retryable = True

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


class UnsupportedMediaTypeError(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "unsupported_media_type"


class LLMUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "llm_unavailable"
    retryable = True


class EmbeddingError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "embedding_unavailable"
    retryable = True


class DocumentProcessingError(AppError):
    status_code = 422
    code = "document_processing_failed"


class SQLSafetyError(AppError):
    """Generated SQL was rejected by the safety layer."""

    status_code = 422
    code = "unsafe_sql"


class SQLExecutionError(AppError):
    status_code = 422
    code = "sql_execution_failed"

    def __init__(self, message: str, *, code: str | None = None, correctable: bool = True) -> None:
        super().__init__(message, code=code)
        self.correctable = correctable


def _envelope(
    code: str, message: str, http_status: int, headers: dict[str, str] | None = None
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "request_id": request_id_var.get()}}
    return JSONResponse(status_code=http_status, content=body, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = None
        if isinstance(exc, RateLimitedError):
            headers = {"Retry-After": str(exc.retry_after)}
        return _envelope(exc.code, exc.message, exc.status_code, headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        detail = first.get("msg", "invalid input")
        message = f"{location}: {detail}" if location else "Invalid input"
        return _envelope("validation_error", message, 422)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed", 401: "unauthorized"}.get(
            exc.status_code, "http_error"
        )
        return _envelope(code, str(exc.detail), exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", type(exc).__name__)
        return _envelope(
            "internal_error",
            "Something went wrong on our side. Please try again.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
