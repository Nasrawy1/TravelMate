import logging
import os
from collections.abc import Callable

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.error_mapping import TripRequestError, trip_request_error_handler
from app.api.routes.health import router as health_router
from app.api.routes.auth_probe import router as auth_probe_router
from app.api.routes.trips import router as trips_router
from app.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.middleware import RequestLoggingMiddleware

DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


class SuppressUvicornTracebacks(logging.Filter):
    """Drop Uvicorn error records carrying exception or traceback details."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.exc_info is None and record.exc_text is None


def configure_application_logging() -> None:
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    for logger_name in ("travelmate.request", "travelmate.errors"):
        app_logger = logging.getLogger(logger_name)
        app_logger.setLevel(logging.INFO)
        app_logger.propagate = False
        if not app_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            app_logger.addHandler(handler)

    uvicorn_error_logger = logging.getLogger("uvicorn.error")
    if not any(
        isinstance(existing_filter, SuppressUvicornTracebacks)
        for existing_filter in uvicorn_error_logger.filters
    ):
        uvicorn_error_logger.addFilter(SuppressUvicornTracebacks())

    # Use the sanitized request logger instead; Uvicorn's access format can
    # include query parameters.
    logging.getLogger("uvicorn.access").disabled = True


configure_application_logging()


def create_app(
    configure_api: Callable[[FastAPI], None] | None = None,
) -> CORSMiddleware:
    api = FastAPI()

    api.add_exception_handler(StarletteHTTPException, http_exception_handler)
    api.add_exception_handler(RequestValidationError, validation_exception_handler)
    api.add_exception_handler(Exception, unhandled_exception_handler)
    api.add_exception_handler(TripRequestError, trip_request_error_handler)

    api.include_router(health_router, prefix="/api/v1")
    api.include_router(trips_router, prefix="/api/v1")

    if os.getenv("ENABLE_AUTH_PROBE", "false").strip().lower() == "true":
        api.include_router(auth_probe_router, prefix="/api/v1")

    if configure_api is not None:
        configure_api(api)

    cors_origins = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", ",".join(DEFAULT_CORS_ORIGINS)
        ).split(",")
        if origin.strip()
    ]

    request_logged_api = RequestLoggingMiddleware(api)
    return CORSMiddleware(
        app=request_logged_api,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID"],
    )


app = create_app()
