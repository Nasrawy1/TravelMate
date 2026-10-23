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


def assert_error(response, *, status_code: int, code: str) -> dict:
    assert response.status_code == status_code
    body = response.json()
    assert body["error"]["code"] == code
    assert "message" in body["error"]
    assert "details" in body["error"]
    assert body["request_id"] == response.headers["X-Request-ID"]
    return body


def test_valid_request_with_auth_returns_temporary_501() -> None:
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(),
            headers={"Authorization": "Bearer test-token"},
        )

    body = assert_error(response, status_code=501, code="NOT_IMPLEMENTED")
    assert body["error"]["message"] == (
        "Adapter and AI integration pending (API-04 / API-05)."
    )


def test_exactly_one_night_passes() -> None:
    start = date.fromisoformat(request_payload()["start_date"])
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(return_date=(start + timedelta(days=1)).isoformat()),
        )

    assert_error(response, status_code=501, code="NOT_IMPLEMENTED")


def test_exactly_seven_nights_passes() -> None:
    start = date.fromisoformat(request_payload()["start_date"])
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(return_date=(start + timedelta(days=7)).isoformat()),
        )

    assert_error(response, status_code=501, code="NOT_IMPLEMENTED")


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


def test_unsupported_city_returns_400() -> None:
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(destination_city="Atlantis"),
        )

    assert_error(response, status_code=400, code="UNSUPPORTED_LOCATION")


def test_same_city_returns_400() -> None:
    with make_client(authenticated=True) as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=request_payload(destination_city="Istanbul"),
        )

    assert_error(response, status_code=400, code="UNSUPPORTED_LOCATION")


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

    assert_error(response, status_code=501, code="NOT_IMPLEMENTED")


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
