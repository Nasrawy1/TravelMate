from datetime import date, datetime, timedelta, timezone
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user_id
from app.main import create_app


def request_payload(**overrides) -> dict[str, object]:
    start = datetime.now(timezone.utc).date() + timedelta(days=5)
    payload: dict[str, object] = {
        "departure_city": "Istanbul",
        "destination_city": "Rome",
        "start_date": start.isoformat(),
        "return_date": (start + timedelta(days=3)).isoformat(),
        "adults": 2,
        "budget_usd": 1500,
    }
    payload.update(overrides)
    return payload


def make_client(*, authenticated: bool = False) -> TestClient:
    def configure_api(api: FastAPI) -> None:
        if authenticated:
            api.dependency_overrides[get_current_user_id] = lambda: "test-user-id"

    return TestClient(
        create_app(configure_api=configure_api),
        raise_server_exceptions=False,
    )


@pytest.fixture(autouse=True)
def offline_generation_adapters(monkeypatch) -> None:
    """Keep request-policy tests offline while exercising the real response path."""
    from app.api.routes import trips

    def search(_trip_request, **_kwargs):
        unavailable = {"status": "unavailable", "public_offers": [], "offers": []}
        return {
            "status": "ok", "flights": unavailable, "hotels": unavailable,
            "report_slice": {"flights_data": {}, "hotels_data": []},
            "flight_candidates": [], "hotel_candidates": [], "warnings": [],
        }

    def itinerary(trip_request, *_args, **_kwargs):
        start = date.fromisoformat(trip_request["start_date"])
        nights = (date.fromisoformat(trip_request["return_date"]) - start).days
        days, activities = [], []
        for offset in range(nights + 1):
            current = start + timedelta(days=offset)
            travel_day = offset in (0, nights)
            day_activities = [] if travel_day else [{
                "order": 1, "name": "Museum", "area": "Center",
                "description": "Visit the museum.",
                "cost": {"amount_usd": None, "kind": "unknown", "coverage": None},
            }]
            days.append({
                "date": current.isoformat(), "activities": day_activities,
                "empty_day_reason": "Travel day." if travel_day else None,
            })
            if day_activities:
                activities.append({
                    "label": "Museum", "kind": "unknown", "amount_usd": None,
                    "activity_ref": {"date": current.isoformat(), "order": 1},
                    "basis": "No structured activity price was supplied.",
                })
        return {"status": "ok", "itinerary": days, "budget_activities": activities, "warnings": []}

    monkeypatch.setattr(trips, "search_travel", search)
    monkeypatch.setattr(trips, "generate_itinerary", itinerary)


def assert_error(response, *, status_code: int, code: str) -> dict:
    assert response.status_code == status_code
    body = response.json()
    assert body["error"]["code"] == code
    assert "message" in body["error"]
    assert "details" in body["error"]
    assert body["request_id"] == response.headers["X-Request-ID"]
    return body


def test_valid_request_with_auth_returns_generation_response() -> None:
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(),
            headers={"Authorization": "Bearer test-token"},
        )

    assert response.status_code == 200
    assert response.json()["generation_status"] == "complete"


def test_exactly_one_night_passes() -> None:
    start = date.fromisoformat(request_payload()["start_date"])
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(return_date=(start + timedelta(days=1)).isoformat()),
        )

    assert response.status_code == 200


def test_exactly_seven_nights_passes() -> None:
    start = date.fromisoformat(request_payload()["start_date"])
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(return_date=(start + timedelta(days=7)).isoformat()),
        )

    assert response.status_code == 200


def test_missing_required_adults_returns_validation_error() -> None:
    payload = request_payload()
    del payload["adults"]
    with make_client(authenticated=True) as client:
        response = client.post("/api/v1/trips/generate", json=payload)

    body = assert_error(response, status_code=422, code="VALIDATION_ERROR")
    assert {item["field"] for item in body["error"]["details"]["fields"]} == {"adults"}


@pytest.mark.parametrize("extra", ["trip_type", "one_way", "currency"])
def test_forbidden_extra_fields_return_validation_error(extra: str) -> None:
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(**{extra: "unexpected"}),
        )

    body = assert_error(response, status_code=422, code="VALIDATION_ERROR")
    assert extra in {item["field"] for item in body["error"]["details"]["fields"]}


def test_unrecognized_city_passes_phase1_validation() -> None:
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(destination_city="Atlantis"),
        )

    assert response.status_code == 200


def test_unicode_city_passes_phase1_validation() -> None:
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(destination_city="العلا"),
        )

    assert response.status_code == 200


def test_country_qualifier_city_passes_phase1_validation() -> None:
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(destination_city="Paris, France"),
        )

    assert response.status_code == 200


def test_empty_city_returns_validation_error() -> None:
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(departure_city=""),
        )

    body = assert_error(response, status_code=422, code="VALIDATION_ERROR")
    assert "departure_city" in {
        item["field"] for item in body["error"]["details"]["fields"]
    }


def test_whitespace_only_city_returns_validation_error() -> None:
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(destination_city="   "),
        )

    body = assert_error(response, status_code=422, code="VALIDATION_ERROR")
    assert "destination_city" in {
        item["field"] for item in body["error"]["details"]["fields"]
    }


def test_201_char_city_returns_validation_error() -> None:
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(destination_city="A" * 201),
        )

    body = assert_error(response, status_code=422, code="VALIDATION_ERROR")
    assert "destination_city" in {
        item["field"] for item in body["error"]["details"]["fields"]
    }


def test_200_char_city_passes_phase1_validation() -> None:
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(destination_city="A" * 200),
        )

    assert response.status_code == 200


def test_malformed_date_returns_validation_error() -> None:
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(start_date="2026-13-40"),
        )

    body = assert_error(response, status_code=422, code="VALIDATION_ERROR")
    assert "start_date" in {
        item["field"] for item in body["error"]["details"]["fields"]
    }


def test_past_start_date_returns_400() -> None:
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(
                start_date=yesterday.isoformat(),
                return_date=(yesterday + timedelta(days=3)).isoformat(),
            ),
        )

    assert_error(response, status_code=400, code="INVALID_TRIP_DATES")


def test_return_date_equal_to_start_date_returns_400_zero_nights() -> None:
    start = date.fromisoformat(request_payload()["start_date"])
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(return_date=start.isoformat()),
        )

    assert_error(response, status_code=400, code="INVALID_TRIP_DATES")


def test_return_date_before_start_date_returns_400() -> None:
    start = date.fromisoformat(request_payload()["start_date"])
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(return_date=(start - timedelta(days=1)).isoformat()),
        )

    assert_error(response, status_code=400, code="INVALID_TRIP_DATES")


def test_eight_nights_returns_400() -> None:
    start = date.fromisoformat(request_payload()["start_date"])
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(return_date=(start + timedelta(days=8)).isoformat()),
        )

    assert_error(response, status_code=400, code="INVALID_TRIP_DATES")


@pytest.mark.parametrize(
    "adults",
    [0, 5, 2.5, "2", True],
    ids=["below-range", "above-range", "float", "string", "boolean"],
)
def test_invalid_adults_return_validation_error(adults: object) -> None:
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate", json=request_payload(adults=adults)
        )

    body = assert_error(response, status_code=422, code="VALIDATION_ERROR")
    assert "adults" in {item["field"] for item in body["error"]["details"]["fields"]}


@pytest.mark.parametrize(
    "budget",
    [0, -100],
    ids=["zero", "negative"],
)
def test_invalid_budget_returns_validation_error(budget: object) -> None:
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate", json=request_payload(budget_usd=budget)
        )

    body = assert_error(response, status_code=422, code="VALIDATION_ERROR")
    assert "budget_usd" in {
        item["field"] for item in body["error"]["details"]["fields"]
    }


@pytest.mark.parametrize(
    "budget_literal",
    ["NaN", "Infinity", "0.004"],
    ids=["nan", "infinity", "rounds-to-zero"],
)
def test_nonfinite_or_subcent_budget_returns_validation_error(
    budget_literal: str,
) -> None:
    payload = request_payload()
    raw_json = json.dumps(payload).replace(
        '"budget_usd": 1500', f'"budget_usd": {budget_literal}'
    )
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            content=raw_json,
            headers={"Content-Type": "application/json"},
        )

    body = assert_error(response, status_code=422, code="VALIDATION_ERROR")
    assert "budget_usd" in {
        item["field"] for item in body["error"]["details"]["fields"]
    }


def test_budget_json_string_returns_validation_error() -> None:
    payload = request_payload()
    raw_json = json.dumps(payload).replace(
        '"budget_usd": 1500', '"budget_usd": "1500"'
    )
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            content=raw_json,
            headers={"Content-Type": "application/json"},
        )

    body = assert_error(response, status_code=422, code="VALIDATION_ERROR")
    assert "budget_usd" in {
        item["field"] for item in body["error"]["details"]["fields"]
    }


def test_positive_subcent_budget_rounds_to_cents_and_passes() -> None:
    payload = request_payload()
    raw_json = json.dumps(payload).replace(
        '"budget_usd": 1500', '"budget_usd": 1500.004'
    )
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            content=raw_json,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 200


def test_missing_authorization_returns_401_with_request_id() -> None:
    with make_client() as client:
        response = client.post("/api/v1/trips/generate", json=request_payload())

    assert_error(response, status_code=401, code="UNAUTHORIZED")


def test_malformed_bearer_authorization_returns_401() -> None:
    with make_client() as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(),
            headers={"Authorization": "Bearer"},
        )

    assert_error(response, status_code=401, code="UNAUTHORIZED")


def test_health_still_returns_200() -> None:
    with make_client() as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "travelmate-api"}
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) >= 8
