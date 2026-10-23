from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.error_mapping import validate_trip_request
from app.api.schemas.trips import GenerateTripRequest
from app.auth.dependencies import get_current_user_id
from app.errors import error_response

router = APIRouter()


@router.post("/trips/generate")
async def generate_trip(
    payload: GenerateTripRequest,
    request: Request,
    _current_user_id: str = Depends(get_current_user_id),
) -> JSONResponse:
    """Temporary scaffold; NOT_IMPLEMENTED will be replaced by the real 200 response once adapters merge.

    Real orchestration is intentionally deferred until the travel and AI adapters
    are available. This scaffold does not call adapters, BE-04, or persistence.
    """
    validate_trip_request(payload)

    # Temporary scaffold code, not in api-contracts.md §5. Replaced by the real 200 response in Phase 2 when adapters merge.
    return error_response(
        request,
        status_code=501,
        code="NOT_IMPLEMENTED",
        message="Adapter and AI integration pending (API-04 / API-05).",
    )
