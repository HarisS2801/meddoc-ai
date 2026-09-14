"""Application error types and JSON exception handlers.

Every service error raised in the app derives from ``AppError`` so that
the API layer can convert it into a consistent ``{"error": {...}}``
response.
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
    ) -> None:
        self.message = message
        self.status_code = status_code
        self.code = code
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


def to_error_response(error: AppError) -> JSONResponse:
    """Convert an AppError into a JSON error response."""
    return JSONResponse(
        status_code=error.status_code,
        content={"error": {"code": error.code, "message": error.message}},
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