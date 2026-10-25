from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user_id
from app.main import create_app


def request_payload(**overrides):
    start = datetime.now(timezone.utc).date() + timedelta(days=10)
    payload = {
        "departure_city": "Istanbul",
        "destination_city": "Rome",
        "start_date": start.isoformat(),
        "return_date": (start + timedelta(days=3)).isoformat(),
        "adults": 2,
        "budget_usd": 1500,
    }
    payload.update(overrides)
    return payload


def make_client() -> TestClient:
    def configure_api(api: FastAPI) -> None:
        api.dependency_overrides[get_current_user_id] = lambda: "test-user-id"

    return TestClient(create_app(configure_api=configure_api), raise_server_exceptions=False)


def travel_success(payload):
    start = date.fromisoformat(payload["start_date"])
    end = date.fromisoformat(payload["return_date"])
    flight_id = "flight-1"
    hotel_id = "1001"
    flight_offer = {
        "id": flight_id,
        "source": "test-provider",
        "retrieved_at": "2026-10-24T10:00:00Z",
        "price": {"amount_usd": 400.0, "kind": "provider", "coverage": "entire_trip_all_travelers"},
        "taxes": {"status": "included", "additional_amount_usd": 0.0},
        "airline": "Test Air",
        "departure_airport_code": "IST",
        "arrival_airport_code": "FCO",
        "outbound_departure_at": f"{start.isoformat()}T08:00:00Z",
        "return_departure_at": f"{end.isoformat()}T18:00:00Z",
        "adults": payload["adults"],
    }
    hotel_offer = {
        "id": hotel_id,
        "source": "test-provider",
        "retrieved_at": "2026-10-24T10:00:00Z",
        "price": {"amount_usd": 300.0, "kind": "provider", "coverage": "entire_trip_all_travelers"},
        "taxes": {"status": "included", "additional_amount_usd": 0.0},
        "name": "Test Hotel",
        "area": "Center",
        "check_in": start.isoformat(),
        "check_out": end.isoformat(),
        "occupancy_adults": payload["adults"],
        "room_qty": 1,
    }
    normalized_hotel = {
        "hotel_id": 1001,
        "name": "Test Hotel",
        "star_rating": 4,
        "review_score": 8.5,
        "nights": (end - start).days,
        "base_price_usd": 300,
        "taxes_and_fees_usd": 0,
        "total_price_usd": 300,
        "price_per_night_usd": 100,
        "fits_budget": True,
    }
    return {
        "status": "ok",
        "flights": {
            "status": "available", "public_offers": [flight_offer],
            "selected_offer": {"id": flight_id},
        },
        "hotels": {"status": "available", "public_offers": [hotel_offer]},
        "report_slice": {
            "flights_data": {"selected_outbound_flight": None, "selected_return_flight": None},
            "hotels_data": [normalized_hotel],
        },
        "flight_candidates": [{
            "id": flight_id, "base_usd": 400, "additional_fees_usd": None,
            "included_in_base": True,
        }],
        "hotel_candidates": [{
            "id": hotel_id, "base_usd": 300, "additional_fees_usd": None,
            "included_in_base": True,
        }],
        "warnings": [],
    }


def ai_success(payload):
    start = date.fromisoformat(payload["start_date"])
    nights = (date.fromisoformat(payload["return_date"]) - start).days
    itinerary = []
    budget_activities = []
    for offset in range(nights + 1):
        day_date = start + timedelta(days=offset)
        is_travel_day = offset in (0, nights)
        activities = [] if is_travel_day else [{
            "order": 1,
            "name": "Museum",
            "area": "Center",
            "description": "Visit the museum.",
            "cost": {
                "amount_usd": 25,
                "kind": "estimate",
                "coverage": "entire_trip_all_travelers",
            },
        }]
        itinerary.append({
            "date": day_date.isoformat(),
            "activities": activities,
            "empty_day_reason": "Travel day." if is_travel_day else None,
        })
        if activities:
            budget_activities.append({
                "label": "Museum",
                "kind": "estimate",
                "amount_usd": 25,
                "activity_ref": {"date": day_date.isoformat(), "order": 1},
                "basis": "Test estimate.",
            })
    return {"status": "ok", "itinerary": itinerary, "budget_activities": budget_activities, "warnings": []}


def unavailable_travel():
    empty = {"status": "unavailable", "public_offers": [], "offers": []}
    return {
        "status": "ok", "flights": empty, "hotels": empty,
        "report_slice": {"hotels_data": [], "flights_data": {}},
        "flight_candidates": [], "hotel_candidates": [],
        "warnings": [],
    }


def test_success_returns_contract_shape_and_request_id(monkeypatch):
    payload = request_payload()
    # Route imports the adapter functions directly.
    from app.api.routes import trips
    fake_database = MagicMock(name="fake_database")
    monkeypatch.setattr(trips, "database", fake_database, raising=False)
    monkeypatch.setattr(trips, "search_travel", lambda *a, **k: travel_success(payload))
    monkeypatch.setattr(trips, "generate_itinerary", lambda *a, **k: ai_success(payload))

    with make_client() as client:
        response = client.post("/api/v1/trips/generate", json=payload)

    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    body = response.json()
    assert set(body) == {
        "generation_status", "live_integration_status", "trip", "itinerary",
        "travel_options", "budget", "warnings",
    }
    assert body["generation_status"] == "complete"
    assert body["live_integration_status"] == "price_received"
    assert len(body["itinerary"]) == 4
    assert body["budget"]["cost_items"]
    assert body["budget"]["selected_flight_offer_id"] == "flight-1"
    assert body["budget"]["selected_hotel_offer_id"] == "1001"
    assert "trip_id" not in body
    fake_database.assert_not_called()


def test_partial_success_when_travel_is_unavailable(monkeypatch):
    payload = request_payload()
    from app.api.routes import trips
    monkeypatch.setattr(trips, "search_travel", lambda *a, **k: unavailable_travel())
    monkeypatch.setattr(trips, "generate_itinerary", lambda *a, **k: ai_success(payload))

    with make_client() as client:
        response = client.post("/api/v1/trips/generate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["live_integration_status"] == "no_price"
    assert body["travel_options"]["flights"] == {"status": "unavailable", "offers": []}
    assert body["travel_options"]["hotels"] == {"status": "unavailable", "offers": []}
    assert {warning["code"] for warning in body["warnings"]} >= {
        "FLIGHTS_UNAVAILABLE", "HOTELS_UNAVAILABLE",
    }
    assert body["budget"]["status"] == "uncertain"


@pytest.mark.parametrize(
    ("source", "adapter_code", "status", "public_code"),
    [
        ("travel", "unsupported_search", 400, "UNSUPPORTED_LOCATION"),
        ("travel", "invalid_input", 422, "VALIDATION_ERROR"),
        ("travel", "rate_limited", 429, "RATE_LIMITED"),
        ("travel", "internal_error", 500, "INTERNAL_ERROR"),
        ("ai", "invalid_output", 502, "AI_GENERATION_FAILED"),
        ("ai", "unavailable", 503, "PROVIDER_UNAVAILABLE"),
        ("ai", "timeout", 504, "GENERATION_TIMEOUT"),
    ],
)
def test_errors_have_request_id_and_do_not_leak_secrets(
    monkeypatch, source, adapter_code, status, public_code
):
    payload = request_payload(destination_city="TESTCITY123")
    private_message = "ADAPTER_PRIVATE_ORIGINAL_MESSAGE"
    adapter_error = {
        "status": "error",
        "error": {"code": adapter_code, "message": private_message},
        "diagnostics": {
            "fields": [{"field": "destination_city", "message": "Location is unsupported."}],
            "reason": "ADAPTER_INTERNAL_REASON",
            "supported_cities": ["INTERNAL_CITY_LIST"],
        },
    }
    from app.api.routes import trips
    if source == "travel":
        monkeypatch.setattr(trips, "search_travel", lambda *a, **k: adapter_error)
    else:
        monkeypatch.setattr(trips, "search_travel", lambda *a, **k: travel_success(payload))
        monkeypatch.setattr(trips, "generate_itinerary", lambda *a, **k: adapter_error)

    authorization_secret = "AUTHORIZATION_SECRET_987"
    with make_client() as client:
        response = client.post(
            "/api/v1/trips/generate",
            json=payload,
            headers={"Authorization": f"Bearer {authorization_secret}"},
        )

    assert response.status_code == status
    body = response.json()
    assert body["error"]["code"] == public_code
    assert body["request_id"] == response.headers["X-Request-ID"]
    response_text = response.text + " ".join(response.headers.values())
    for secret in (private_message, authorization_secret, "Bearer", "TESTCITY123", "INTERNAL_CITY_LIST"):
        assert secret not in response_text


@pytest.mark.parametrize(
    "diagnostics",
    [
        None,
        [],
        {"fields": "bad"},
        {"fields": [{"field": "destination_city", "message": "safe", "secret": "DROP_ME"}, "bad"]},
    ],
)
def test_malformed_adapter_diagnostics_are_dropped(monkeypatch, diagnostics):
    payload = request_payload()
    from app.api.routes import trips
    monkeypatch.setattr(trips, "search_travel", lambda *a, **k: {
        "status": "error",
        "error": {"code": "unsupported_search", "message": "private"},
        "diagnostics": diagnostics,
    })
    with make_client() as client:
        response = client.post("/api/v1/trips/generate", json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["details"] is None
    assert "DROP_ME" not in response.text


def test_adapter_diagnostics_copy_only_field_and_message(monkeypatch):
    payload = request_payload()
    from app.api.routes import trips
    monkeypatch.setattr(trips, "search_travel", lambda *a, **k: {
        "status": "error",
        "error": {"code": "unsupported_search", "message": "private"},
        "diagnostics": {
            "fields": [{"field": "destination_city", "message": "Qualify the city.", "secret": "DROP_ME"}],
            "reason": "DROP_REASON",
            "supported_cities": ["DROP_CITIES"],
        },
    })
    with make_client() as client:
        response = client.post("/api/v1/trips/generate", json=payload)
    assert response.json()["error"]["details"] == {
        "fields": [{"field": "destination_city", "message": "Qualify the city."}]
    }
    assert "DROP_ME" not in response.text
    assert "DROP_REASON" not in response.text
    assert "DROP_CITIES" not in response.text


def test_invalid_ai_itinerary_length_returns_sanitized_502(monkeypatch):
    payload = request_payload()
    from app.api.routes import trips
    monkeypatch.setattr(trips, "search_travel", lambda *a, **k: unavailable_travel())
    monkeypatch.setattr(trips, "generate_itinerary", lambda *a, **k: {
        "status": "ok", "itinerary": [], "budget_activities": [],
    })
    with make_client() as client:
        response = client.post("/api/v1/trips/generate", json=payload)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_GENERATION_FAILED"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_invalid_input_copies_diagnostics_fields(monkeypatch):
    payload = request_payload()
    fields = [{
        "field": "destination_city",
        "message": "destination_city must be different from departure_city.",
    }]
    from app.api.routes import trips
    monkeypatch.setattr(trips, "search_travel", lambda *a, **k: {
        "status": "error",
        "error": {"code": "invalid_input"},
        "diagnostics": {"fields": fields},
    })

    with make_client() as client:
        response = client.post("/api/v1/trips/generate", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["fields"] == fields


def test_travel_timeout_returns_504(monkeypatch):
    from app.api.routes import trips
    monkeypatch.setattr(trips, "search_travel", lambda *a, **k: {
        "status": "error", "error": {"code": "timeout"},
    })
    with make_client() as client:
        response = client.post("/api/v1/trips/generate", json=request_payload())
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "GENERATION_TIMEOUT"


def test_travel_unavailable_returns_503(monkeypatch):
    from app.api.routes import trips
    monkeypatch.setattr(trips, "search_travel", lambda *a, **k: {
        "status": "error", "error": {"code": "unavailable"},
    })
    with make_client() as client:
        response = client.post("/api/v1/trips/generate", json=request_payload())
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"


def test_ai_rate_limited_returns_429(monkeypatch):
    payload = request_payload()
    from app.api.routes import trips
    monkeypatch.setattr(trips, "search_travel", lambda *a, **k: travel_success(payload))
    monkeypatch.setattr(trips, "generate_itinerary", lambda *a, **k: {
        "status": "error", "error": {"code": "rate_limited"},
    })
    with make_client() as client:
        response = client.post("/api/v1/trips/generate", json=payload)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


def test_response_trip_echoes_trimmed_cities(monkeypatch):
    payload = request_payload(departure_city="  Istanbul  ", destination_city="Rome")
    from app.api.routes import trips
    monkeypatch.setattr(trips, "search_travel", lambda *a, **k: unavailable_travel())
    monkeypatch.setattr(trips, "generate_itinerary", lambda *a, **k: ai_success(payload))

    with make_client() as client:
        response = client.post("/api/v1/trips/generate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["trip"]["departure_city"] == "Istanbul"
    assert body["trip"]["destination_city"] == "Rome"
    assert "  Istanbul  " not in response.text
    # No live offers are included, so provider-resolved airport metadata is absent too.
    assert "IST" not in response.text


def test_malformed_diagnostics_missing_field_key_returns_null(monkeypatch):
    from app.api.routes import trips
    monkeypatch.setattr(trips, "search_travel", lambda *a, **k: {
        "status": "error",
        "error": {"code": "unsupported_search"},
        "diagnostics": {"fields": [{"message": "no field key"}]},
    })
    with make_client() as client:
        response = client.post("/api/v1/trips/generate", json=request_payload())

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "UNSUPPORTED_LOCATION"
    assert body["error"]["details"] is None


def test_identical_cities_through_endpoint_returns_422(monkeypatch):
    payload = request_payload(
        departure_city="Istanbul",
        destination_city="Istanbul",
    )
    fields = [{
        "field": "destination_city",
        "message": "destination_city must be different from departure_city.",
    }]
    from app.api.routes import trips
    monkeypatch.setattr(trips, "search_travel", lambda *a, **k: {
        "status": "error",
        "error": {"code": "invalid_input"},
        "diagnostics": {"fields": fields},
    })

    with make_client() as client:
        response = client.post("/api/v1/trips/generate", json=payload)

    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["fields"] == fields
    assert response.headers["X-Request-ID"] == body["request_id"]


def test_alias_city_through_endpoint_is_accepted(monkeypatch):
    payload = request_payload(destination_city="NYC")
    from app.api.routes import trips
    monkeypatch.setattr(trips, "search_travel", lambda *a, **k: travel_success(payload))
    monkeypatch.setattr(trips, "generate_itinerary", lambda *a, **k: ai_success(payload))

    with make_client() as client:
        response = client.post("/api/v1/trips/generate", json=payload)

    body = response.json()
    assert response.status_code == 200
    assert body["trip"]["destination_city"] == "NYC"
    assert "NYC" in response.text
    assert "New York" not in response.text
    assert "JFK" not in response.text
    assert "LGA" not in response.text


def test_unsupported_city_returns_400_with_copied_fields(monkeypatch):
    payload = request_payload()
    fields = [{
        "field": "departure_city",
        "message": "departure_city is not a supported city.",
    }]
    from app.api.routes import trips
    monkeypatch.setattr(trips, "search_travel", lambda *a, **k: {
        "status": "error",
        "error": {"code": "unsupported_search"},
        "diagnostics": {"fields": fields},
    })

    with make_client() as client:
        response = client.post("/api/v1/trips/generate", json=payload)

    body = response.json()
    assert response.status_code == 400
    assert body["error"]["code"] == "UNSUPPORTED_LOCATION"
    assert body["error"]["details"]["fields"] == fields
    assert response.headers["X-Request-ID"] == body["request_id"]
