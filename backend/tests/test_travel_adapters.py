"""
Backend-path tests for the TravelMate adapters (PR #25 review, item 3).

They import the adapters exactly as BE-03 will (app.adapters.*), make no network call and use no API quota.
The full offline suite (120 tests) is prototypes/travel-adapter/test_travelmate_adapters.py; the end-to-end test
below reuses its recorded provider responses when the repository folder is present.
"""
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters import travelmate as tm
from app.adapters.ai import GROQ_MODEL, generate_itinerary
from app.adapters.flights import search_flights
from app.adapters.hotels import search_hotels
from app.services.budget import calculate_budget
from app.services.models import BudgetInput, ZiyadReportSlice

FIXTURES = Path(__file__).resolve().parents[2] / "prototypes" / "travel-adapter" / "tests" / "fixtures"
REQUEST = {"departure_city": "Istanbul", "destination_city": "Cairo", "start_date": "2026-11-20",
           "return_date": "2026-11-23", "adults": 2, "budget_usd": 1500}
TRIP_DATES = ["2026-11-20", "2026-11-21", "2026-11-22", "2026-11-23"]
KEY_PREFIXES = ("GOOGLE_FLIGHTS_RAPIDAPI_KEY", "BOOKING_RAPIDAPI_KEY", "SKYSCANNER_RAPIDAPI_KEY", "GROQ_API_KEY")


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.headers = {}
        self.text = json.dumps(body)

    def json(self):
        return self._body


class FakeGroq:
    """SIMULATED Groq client returning a fixed JSON itinerary."""
    def __init__(self, content):
        self.calls = 0
        client = self

        class Raw:
            headers = {}

            def parse(self):
                message = type("M", (), {"content": content})()
                return type("R", (), {"choices": [type("C", (), {"message": message})()], "usage": None})()

        class WithRaw:
            @staticmethod
            def create(**kwargs):
                client.calls += 1
                return Raw()

        self.chat = type("Chat", (), {"completions": type("Comp", (), {"with_raw_response": WithRaw})()})()


def itinerary_json():
    days = []
    for i, day in enumerate(TRIP_DATES):
        travel_day = i in (0, len(TRIP_DATES) - 1)
        days.append({"date": day, "empty_day_reason": "Travel and hotel check-in/out." if travel_day else None,
                     "activities": [] if travel_day else [{
                         "order": 1, "name": "Egyptian Museum", "area": "Tahrir", "description": "Museum visit.",
                         "category": "culture", "cost": {"amount_usd": 30, "kind": "estimate"}}]})
    return json.dumps({"itinerary": days, "ancillary_estimates": None, "price_explanation": "Live prices."})


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """No real key, no local file, no network: every provider call must be explicitly routed by a test."""
    for name in list(os.environ):
        if name.startswith(KEY_PREFIXES):
            monkeypatch.delenv(name)
    for attr, value in (("CACHE_FILE", tmp_path / "cache.json"), ("REPORT_FILE", tmp_path / "report.json"),
                        ("ENV_FILE", tmp_path / ".env"), ("EXHAUSTED_KEYS_FILE", tmp_path / ".env.exhausted")):
        monkeypatch.setattr(tm, attr, str(value))
    monkeypatch.setattr(tm, "LOCAL_KEY_ROTATION", False)
    monkeypatch.setattr(tm, "PRUNE_DEAD_KEYS", False)
    monkeypatch.setattr(tm, "FLIGHT_MODE", "live")
    monkeypatch.setattr(tm, "_today_utc", lambda: date(2026, 10, 20))
    monkeypatch.setattr(tm, "_sleep", lambda seconds: None)

    def no_network(*args, **kwargs):
        raise AssertionError("unexpected network call")
    monkeypatch.setattr(tm.requests, "get", no_network)


def assert_category(category, status, reason_code):
    assert (category["status"], category["reason_code"]) == (status, reason_code)
    if status == "unavailable":
        assert category["offers"] == [] and category["public_offers"] == []


def test_wrappers_return_both_categories_explicitly():
    flights_only = search_flights(dict(REQUEST), cache_mode="off")
    assert_category(flights_only["flights"], "unavailable", "not_configured")  # No Google Flights key configured
    assert_category(flights_only["hotels"], "unavailable", "not_requested")
    hotels_only = search_hotels(dict(REQUEST), cache_mode="off")
    assert_category(hotels_only["flights"], "unavailable", "not_requested")
    assert_category(hotels_only["hotels"], "unavailable", "not_configured")  # No Booking key configured
    ZiyadReportSlice.model_validate(dict(hotels_only["report_slice"], ai_recommendation_report=""))


def test_invalid_request_is_rejected_before_any_call():
    result = search_flights(dict(REQUEST, trip_type="one_way"), cache_mode="off")
    assert result["status"] == "error"
    assert result["error"]["code"] == "invalid_input"
    assert set(result["error"]) == {"code", "message"}


def test_ai_without_key_is_unavailable():
    result = generate_itinerary(dict(REQUEST), {"flight": None, "hotel": None},
                                {"flights": "unavailable", "hotels": "unavailable"})
    assert (result["status"], result["error"]["code"]) == ("error", "unavailable")
    assert GROQ_MODEL == "openai/gpt-oss-120b"


def test_ai_itinerary_feeds_be04(monkeypatch):
    fake = FakeGroq(itinerary_json())
    monkeypatch.setattr(tm, "_get_groq_client", lambda timeout: fake)
    result = generate_itinerary(dict(REQUEST), {"flight": None, "hotel": None},
                                {"flights": "unavailable", "hotels": "unavailable"})
    assert result["status"] == "ok"
    assert [day["date"] for day in result["itinerary"]] == TRIP_DATES
    assert fake.calls == 1  # Single attempt, never retried
    budget = calculate_budget(BudgetInput.model_validate({
        "budget_usd": 1500, "flights_data": {"selected_outbound_flight": None, "selected_return_flight": None},
        "selected_hotel": None, "activities": result["budget_activities"]}))
    assert budget.status == "uncertain"  # No flight or hotel price: never presented as complete


@pytest.mark.skipif(not FIXTURES.is_dir(), reason="recorded provider responses are in prototypes/travel-adapter")
def test_live_search_to_itinerary_to_be04(monkeypatch):
    """Recorded Google Flights + Booking.com responses; hotel dates SIMULATED onto the recorded flight dates."""
    load = lambda name: json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    google = {"/m/09949m": load("google_flights_oneway_ist_cai_2026-11-20_2a"),
              "/m/01w2v": load("google_flights_oneway_cai_ist_2026-11-23_2a")}
    hotels_text = json.dumps(load("hotels_cairo_2a1r")).replace("2026-11-01", "2026-11-20").replace("2026-11-05", "2026-11-23")
    hotels = json.loads(hotels_text.replace("Price for 4 nights", "Price for 3 nights"))

    def router(url, headers=None, params=None, timeout=None):
        if "google-flights2" in url:
            return FakeResponse(200, google[params["departure_id"]])
        if "searchHotels" in url:
            return FakeResponse(200, hotels)
        raise AssertionError(f"unexpected call: {url}")

    monkeypatch.setenv("GOOGLE_FLIGHTS_RAPIDAPI_KEYS", "fakegooglekey01eeee")
    monkeypatch.setenv("BOOKING_RAPIDAPI_KEYS", "fakebookkey001cccc")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_FAKEFAKEFAKEFAKEFAKEFAKE00")
    monkeypatch.setattr(tm.requests, "get", router)
    monkeypatch.setattr(tm, "_get_groq_client", lambda timeout: FakeGroq(itinerary_json()))

    travel = tm.search_travel(dict(REQUEST), categories=("flights", "hotels"), cache_mode="off")
    flights, hotel_offers = travel["flights"], travel["hotels"]["offers"]
    assert_category(flights, "available", None)
    assert_category(travel["hotels"], "available", None)
    ZiyadReportSlice.model_validate(dict(travel["report_slice"], ai_recommendation_report=""))

    ai = generate_itinerary(dict(REQUEST), {"flight": {"selected_outbound_flight": flights["selected_outbound_flight"],
                                                       "selected_return_flight": flights["selected_return_flight"],
                                                       "schedule": flights["schedule"]},
                                            "hotel": hotel_offers[0]},
                            {"flights": "live", "hotels": "live"}, request_id=travel["request_id"])
    assert ai["status"] == "ok"

    budget = calculate_budget(BudgetInput.model_validate({
        "budget_usd": REQUEST["budget_usd"], "flights_data": travel["report_slice"]["flights_data"],
        "selected_hotel": hotel_offers[0], "activities": ai["budget_activities"]}))
    flight_line = next(item for item in budget.cost_items if item.category == "flights")
    assert flight_line.amount_usd == Decimal(str(flights["selected_offer"]["price"]["amount_usd"]))
    entry = next(e for e in travel["provenance"] if e.get("offer_id") == flights["selected_offer"]["id"])
    assert budget.selected_flight_offer_id == entry["be04_flight_offer_id"]  # Adapter ID <-> BE-04 synthetic ID
