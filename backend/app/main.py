"""FastAPI application entrypoint.

Use an app factory so tests can build isolated instances and later
phases can register additional routers cleanly.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat, documents, health, review
from app.core import exceptions
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.log_level)
    init_db()
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in settings.cors_origins.split(",")
            if origin.strip()
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    exceptions.register_exception_handlers(application)
    application.include_router(health.router, prefix="/api")
    application.include_router(documents.router, prefix="/api")
    application.include_router(chat.router, prefix="/api")
    application.include_router(review.router, prefix="/api")

    # Retrieval debug telemetry. Only ever exposed when RETRIEVAL_DEBUG=true
    # (default off, always off in production): it returns extracted chunk text
    # and scores, so it must never be reachable in a deployed deployment.
    if settings.retrieval_debug:
        from app.api.routes import retrieval_debug

        application.include_router(retrieval_debug.router, prefix="/api")

    return application


app = create_app()