import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.error_mapping import validation_error_fields

logger = logging.getLogger("travelmate.errors")


def error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
            },
            "request_id": request_id,
        },
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return error_response(
        request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed.",
        details={"fields": validation_error_fields(exc)},
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    mappings = {
        400: ("INVALID_TRIP_DATES", "The request is invalid."),
        401: ("UNAUTHORIZED", "Authentication is required."),
        403: ("FORBIDDEN", "This request is not allowed."),
        404: ("NOT_FOUND", "The requested resource was not found."),
        429: ("RATE_LIMITED", "Too many requests."),
    }
    code, message = mappings.get(
        exc.status_code,
        ("INTERNAL_ERROR", "The request could not be completed."),
    )
    return error_response(
        request,
        status_code=exc.status_code,
        code=code,
        message=message,
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    # Do not log exception details or tracebacks, which could contain secrets.
    logger.error(
        "Unhandled server exception request_id=%s",
        getattr(request.state, "request_id", "unknown"),
    )
    return error_response(
        request,
        status_code=500,
        code="INTERNAL_ERROR",
        message="An unexpected error occurred.",
    )
