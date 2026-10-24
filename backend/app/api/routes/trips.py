"""Authenticated orchestration for non-persisted trip generation.

The travel adapter may write its local ``travelmate_cache.json`` even when
``save_report=False``. That cache side effect is outside the trip-persistence
boundary. Generation does not write trips to Supabase.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.adapters.travelmate import generate_itinerary, search_travel
from app.api.error_mapping import validate_trip_request
from app.api.schemas.trips import GenerateTripRequest
from app.auth.dependencies import get_current_user_id
from app.errors import error_response
from app.services.budget import calculate_budget, select_offer
from app.services.models import BudgetInput, OfferCandidate

router = APIRouter()

GENERATION_TIMEOUT_SECONDS = 60
AI_RESERVE_SECONDS = 25
ESTIMATION_POLICY = {"id": None, "food": None, "local_transport": None}


def _error(
    request: Request, status_code: int, code: str, message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return error_response(
        request,
        status_code=status_code,
        code=code,
        message=message,
        details=details,
    )


def _safe_adapter_fields(diagnostics: object) -> dict[str, Any] | None:
    """Allow only well-formed field/message pairs from adapter diagnostics."""
    if not isinstance(diagnostics, dict):
        return None
    fields = diagnostics.get("fields")
    if not isinstance(fields, list):
        return None
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("field"), str)
        or not isinstance(item.get("message"), str)
        for item in fields
    ):
        return None
    return {
        "fields": [
            {"field": item["field"], "message": item["message"]}
            for item in fields
        ]
    }


def _map_adapter_error(request: Request, result: object, *, source: str) -> JSONResponse:
    if not isinstance(result, dict):
        return _error(request, 500, "INTERNAL_ERROR", "An unexpected error occurred.")
    error = result.get("error")
    code = error.get("code") if isinstance(error, dict) else None
    diagnostics = result.get("diagnostics")

    if source == "travel":
        if code == "unsupported_search":
            return _error(
                request, 400, "UNSUPPORTED_LOCATION",
                "One or more locations are not supported.",
                _safe_adapter_fields(diagnostics),
            )
        if code == "invalid_input":
            return _error(
                request, 422, "VALIDATION_ERROR", "The request is invalid.",
                _safe_adapter_fields(diagnostics),
            )
        mappings = {
            "timeout": (504, "GENERATION_TIMEOUT", "Trip generation timed out."),
            "unavailable": (503, "PROVIDER_UNAVAILABLE", "Travel providers are unavailable."),
            "rate_limited": (429, "RATE_LIMITED", "A travel provider is rate limited."),
        }
    else:
        mappings = {
            "timeout": (504, "GENERATION_TIMEOUT", "Trip generation timed out."),
            "invalid_output": (502, "AI_GENERATION_FAILED", "The itinerary could not be validated."),
            "unavailable": (503, "PROVIDER_UNAVAILABLE", "The itinerary service is unavailable."),
            "rate_limited": (429, "RATE_LIMITED", "The itinerary service is rate limited."),
        }

    status, public_code, message = mappings.get(
        code, (500, "INTERNAL_ERROR", "An unexpected error occurred.")
    )
    return _error(request, status, public_code, message)


def _candidate_list(value: object) -> list[OfferCandidate]:
    if not isinstance(value, list):
        raise ValueError("Adapter candidate list is malformed")
    return [OfferCandidate.model_validate(item) for item in value]


def _select_context(
    travel: dict[str, Any],
) -> tuple[list[OfferCandidate], list[OfferCandidate], dict[str, Any] | None, dict[str, Any] | None]:
    flight_candidates = _candidate_list(travel.get("flight_candidates", []))
    hotel_candidates = _candidate_list(travel.get("hotel_candidates", []))

    selected_flight, _ = select_offer(flight_candidates, "flight")
    selected_hotel, _ = select_offer(hotel_candidates, "hotel")

    flight_context = None
    if selected_flight is not None:
        flights = travel.get("flights")
        offers = flights.get("public_offers", []) if isinstance(flights, dict) else []
        flight_context = next(
            (offer for offer in offers
             if isinstance(offer, dict) and offer.get("id") == selected_flight.id),
            None,
        )
        if flight_context is None:
            raise ValueError("Selected flight candidate has no matching public offer")

    hotel_context = None
    if selected_hotel is not None:
        report_slice = travel.get("report_slice")
        hotels = report_slice.get("hotels_data", []) if isinstance(report_slice, dict) else []
        hotel_context = next(
            (offer for offer in hotels
             if isinstance(offer, dict) and str(offer.get("hotel_id")) == selected_hotel.id),
            None,
        )
        if hotel_context is None:
            raise ValueError("Selected hotel candidate has no matching normalized hotel offer")

    return flight_candidates, hotel_candidates, flight_context, hotel_context


def _valid_itinerary(itinerary: object, payload: GenerateTripRequest) -> bool:
    if not isinstance(itinerary, list):
        return False
    nights = (payload.return_date - payload.start_date).days
    expected_dates = [
        (payload.start_date + timedelta(days=offset)).isoformat()
        for offset in range(nights + 1)
    ]
    if len(itinerary) != len(expected_dates):
        return False

    for index, (day, expected_date) in enumerate(zip(itinerary, expected_dates)):
        if not isinstance(day, dict) or set(day) != {"date", "activities", "empty_day_reason"}:
            return False
        if day.get("date") != expected_date or not isinstance(day.get("activities"), list):
            return False
        activities = day["activities"]
        reason = day.get("empty_day_reason")
        if activities:
            if reason is not None:
                return False
        elif index not in (0, len(expected_dates) - 1) or not isinstance(reason, str) or not reason.strip():
            return False
        for order, activity in enumerate(activities, start=1):
            if not isinstance(activity, dict) or set(activity) != {
                "order", "name", "area", "description", "cost"
            }:
                return False
            activity_order = activity.get("order")
            if isinstance(activity_order, bool) or not isinstance(activity_order, int) or activity_order != order:
                return False
            if any(not isinstance(activity.get(field), str) or not activity[field].strip()
                   for field in ("name", "area", "description")):
                return False
            cost = activity.get("cost")
            if not isinstance(cost, dict) or set(cost) != {"amount_usd", "kind", "coverage"}:
                return False
            amount, kind, coverage = cost.get("amount_usd"), cost.get("kind"), cost.get("coverage")
            if kind not in {"provider", "estimate", "unknown"}:
                return False
            if kind == "unknown":
                if amount is not None or coverage is not None:
                    return False
            elif (
                isinstance(amount, bool)
                or not isinstance(amount, (int, float, Decimal))
                or amount < 0
                or coverage not in {"entire_trip_all_travelers", "all_travelers"}
            ):
                return False
    return True


def _valid_budget_activities(budget_activities: object, itinerary: list[dict[str, Any]]) -> bool:
    if not isinstance(budget_activities, list):
        return False
    expected: dict[tuple[str, int], dict[str, Any]] = {}
    for day in itinerary:
        for activity in day["activities"]:
            expected[(day["date"], activity["order"])] = activity
    if len(budget_activities) != len(expected):
        return False
    seen: set[tuple[str, int]] = set()
    for item in budget_activities:
        if not isinstance(item, dict) or not isinstance(item.get("activity_ref"), dict):
            return False
        ref = item["activity_ref"]
        if (
            not isinstance(ref.get("date"), str)
            or isinstance(ref.get("order"), bool)
            or not isinstance(ref.get("order"), int)
        ):
            return False
        key = (ref.get("date"), ref.get("order"))
        activity = expected.get(key)
        if activity is None or key in seen:
            return False
        seen.add(key)
        cost = activity["cost"]
        if (
            item.get("label") != activity["name"]
            or item.get("kind") != cost["kind"]
            or item.get("amount_usd") != cost["amount_usd"]
            or not isinstance(item.get("basis"), str)
        ):
            return False
    return seen == set(expected)


def _warnings(*sources: object) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for source in sources:
        if not isinstance(source, list):
            continue
        for warning in source:
            if (isinstance(warning, dict)
                    and isinstance(warning.get("code"), str)
                    and isinstance(warning.get("message"), str)):
                result.append({"code": warning["code"], "message": warning["message"]})
    return result


@router.post("/trips/generate")
async def generate_trip(
    payload: GenerateTripRequest,
    request: Request,
    _current_user_id: str = Depends(get_current_user_id),
) -> JSONResponse:
    """Generate a validated itinerary and deterministic budget without persisting a trip."""
    validate_trip_request(payload)
    request_id = request.state.request_id
    overall_deadline = datetime.now(timezone.utc) + timedelta(seconds=GENERATION_TIMEOUT_SECONDS)
    travel_deadline = overall_deadline - timedelta(seconds=AI_RESERVE_SECONDS)
    trip_request = {
        "departure_city": payload.departure_city,
        "destination_city": payload.destination_city,
        "start_date": payload.start_date.isoformat(),
        "return_date": payload.return_date.isoformat(),
        "adults": payload.adults,
        "budget_usd": float(payload.budget_usd),
    }

    travel = await run_in_threadpool(
        search_travel,
        trip_request,
        deadline_at=travel_deadline,
        request_id=request_id,
    )
    if datetime.now(timezone.utc) >= overall_deadline:
        return _error(request, 504, "GENERATION_TIMEOUT", "Trip generation timed out.")
    if not isinstance(travel, dict) or travel.get("status") == "error":
        return _map_adapter_error(request, travel, source="travel")
    if travel.get("status") != "ok":
        return _error(request, 500, "INTERNAL_ERROR", "An unexpected error occurred.")

    try:
        flight_candidates, hotel_candidates, flight_context, hotel_context = _select_context(travel)
    except (ValidationError, ValueError, TypeError):
        return _error(request, 500, "INTERNAL_ERROR", "An unexpected error occurred.")

    flights_result = travel.get("flights")
    hotels_result = travel.get("hotels")
    flights_available = (
        isinstance(flights_result, dict)
        and flights_result.get("status") == "available"
        and bool(flights_result.get("public_offers"))
    )
    hotels_available = (
        isinstance(hotels_result, dict)
        and hotels_result.get("status") == "available"
        and bool(hotels_result.get("public_offers"))
    )
    travel_availability = {
        "flights": "live" if flights_available else "unavailable",
        "hotels": "live" if hotels_available else "unavailable",
    }

    ai = await run_in_threadpool(
        generate_itinerary,
        trip_request,
        {"flight": flight_context, "hotel": hotel_context},
        travel_availability,
        ESTIMATION_POLICY,
        deadline_at=overall_deadline,
        request_id=request_id,
    )
    if datetime.now(timezone.utc) >= overall_deadline:
        return _error(request, 504, "GENERATION_TIMEOUT", "Trip generation timed out.")
    if not isinstance(ai, dict) or ai.get("status") == "error":
        return _map_adapter_error(request, ai, source="ai")
    if ai.get("status") != "ok" or not _valid_itinerary(ai.get("itinerary"), payload):
        return _error(
            request, 502, "AI_GENERATION_FAILED", "The itinerary could not be validated."
        )
    if not _valid_budget_activities(ai.get("budget_activities"), ai["itinerary"]):
        return _error(request, 502, "AI_GENERATION_FAILED", "The itinerary could not be validated.")

    try:
        budget_input = BudgetInput(
            budget_usd=payload.budget_usd,
            flights_data={"selected_outbound_flight": None, "selected_return_flight": None},
            selected_hotel=None,
            activities=ai.get("budget_activities", []),
            food=None,
            local_transport=None,
            flight_candidates=[candidate.model_dump() for candidate in flight_candidates],
            hotel_candidates=[candidate.model_dump() for candidate in hotel_candidates],
        )
        budget = calculate_budget(budget_input)
    except (ValidationError, ValueError, TypeError):
        return _error(request, 502, "AI_GENERATION_FAILED", "The itinerary could not be validated.")

    flight_offers = flights_result.get("public_offers", []) if flights_available else []
    hotel_offers = hotels_result.get("public_offers", []) if hotels_available else []
    if not isinstance(flight_offers, list) or not isinstance(hotel_offers, list):
        return _error(request, 500, "INTERNAL_ERROR", "An unexpected error occurred.")
    warnings = _warnings(travel.get("warnings"), ai.get("warnings"))
    if not flights_available and not any(item["code"] == "FLIGHTS_UNAVAILABLE" for item in warnings):
        warnings.append({"code": "FLIGHTS_UNAVAILABLE", "message": "No eligible live flight offers are available."})
    if not hotels_available and not any(item["code"] == "HOTELS_UNAVAILABLE" for item in warnings):
        warnings.append({"code": "HOTELS_UNAVAILABLE", "message": "No eligible live hotel offers are available."})

    body = {
        "generation_status": "complete",
        "live_integration_status": "price_received" if flights_available or hotels_available else "no_price",
        "trip": {
            "departure_city": payload.departure_city,
            "destination_city": payload.destination_city,
            "start_date": payload.start_date.isoformat(),
            "return_date": payload.return_date.isoformat(),
            "nights": (payload.return_date - payload.start_date).days,
            "adults": payload.adults,
        },
        "itinerary": ai["itinerary"],
        "travel_options": {
            "flights": {"status": "live" if flights_available else "unavailable", "offers": flight_offers},
            "hotels": {"status": "live" if hotels_available else "unavailable", "offers": hotel_offers},
        },
        "budget": budget.model_dump(mode="python"),
        "warnings": warnings,
    }
    return JSONResponse(status_code=200, content=jsonable_encoder(body))
