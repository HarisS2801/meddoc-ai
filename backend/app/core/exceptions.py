"""Application error types and JSON exception handlers.

Every service error raised in the app derives from ``AppError`` so that
the API layer can convert it into a consistent ``{"error": {...}}``
response.

Provider failures (Groq unavailable) carry extra metadata
(``success``, ``provider``, ``generation_status``, ``error_code``) that is
merged into the error envelope so clients can show a precise, safe
message instead of a fabricated medical answer.
"""

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Base error with an HTTP status and a stable machine-readable code."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        code: str = "app_error",
        details: dict | None = None,
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "The requested resource was not found.") -> None:
        super().__init__(message, status_code=404, code="not_found")


class ConflictError(AppError):
    def __init__(self, message: str = "The request conflicts with the current state.") -> None:
        super().__init__(message, status_code=409, code="conflict")


class InvalidFileError(AppError):
    def __init__(self, message: str = "The file is invalid or not supported.") -> None:
        super().__init__(message, status_code=422, code="invalid_file")


GROQ_UNAVAILABLE_MESSAGE = (
    "Groq AI is currently unavailable. Please try again later."
)

GROQ_MISSING_KEY_MESSAGE = (
    "GROQ_API_KEY is not set, so AI analysis is unavailable. Configure "
    "GROQ_API_KEY in backend/.env (see .env.example) and restart the server "
    "to enable Groq AI."
)


class GroqUnavailableError(AppError):
    """Groq could not produce an answer (missing key, quota, auth, timeout,
    network, or unreadable output).

    The app never fabricates a medical summary when this happens: the
    client receives a controlled 503 with machine-readable provider
    metadata.
    """

    def __init__(self, message: str = GROQ_UNAVAILABLE_MESSAGE) -> None:
        super().__init__(
            message,
            status_code=503,
            code="groq_unavailable",
            details={
                "success": False,
                "provider": "groq",
                "generation_status": "unavailable",
                "error_code": "GROQ_UNAVAILABLE",
            },
        )


class AIServiceUnavailableError(GroqUnavailableError):
    """Deprecated alias kept for backward compatibility with older callers."""


def to_error_response(error: AppError) -> JSONResponse:
    """Convert an AppError into a JSON error response."""
    body: dict = {"code": error.code, "message": error.message}
    if error.details:
        body.update(error.details)
    return JSONResponse(
        status_code=error.status_code,
        content={"error": body},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach JSON error handlers to the FastAPI application."""

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return to_error_response(exc)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": str(exc.detail)}},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "The request failed validation.",
                    "details": jsonable_encoder(exc.errors()),
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        _request: Request, exc: Exception
    ) -> JSONResponse:
        # Do not leak stack traces or upstream provider error bodies to the
        # client; the server log keeps the full picture.
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Something went wrong while processing the request. Please try again.",
                }
            },
        )