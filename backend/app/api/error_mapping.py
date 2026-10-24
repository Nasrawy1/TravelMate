from datetime import datetime, timezone

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.schemas.trips import GenerateTripRequest


def validation_error_fields(
    exc: ValidationError | RequestValidationError,
) -> list[dict[str, str]]:
    """Convert Pydantic errors to the public field/message shape, without input values."""
    # Never include error["input"] — it may contain client-supplied secrets.
    return [
        {
            "field": ".".join(
                str(part) for part in error["loc"] if part != "body"
            ),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]


class TripRequestError(Exception):
    """Trip policy error; register it with FastAPI's exception handler to map its envelope."""

    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def validate_trip_request(payload: GenerateTripRequest) -> None:
    """Raise contract-mapped errors for well-typed date policy failures."""
    # Validation reference is UTC calendar date per api-contracts.md §2.
    today_utc = datetime.now(timezone.utc).date()
    if payload.start_date <= today_utc:
        raise TripRequestError(
            status_code=400,
            code="INVALID_TRIP_DATES",
            message="Start date must be later than today's UTC calendar date.",
        )

    nights = (payload.return_date - payload.start_date).days
    if nights < 1 or nights > 7:
        raise TripRequestError(
            status_code=400,
            code="INVALID_TRIP_DATES",
            message="Return date must be 1 to 7 nights after start date.",
        )

async def trip_request_error_handler(
    request: Request, exc: TripRequestError
) -> JSONResponse:
    # Import here to keep error_response as the common envelope without a module cycle.
    from app.errors import error_response

    return error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
    )
