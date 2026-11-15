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


# ---- API-06 (#36): structured food, transport and activity costs (QA-01 #30 reproduction, SIMULATED AI output) ----
API06_EXAMPLE = Path(__file__).resolve().parent / "evidence" / "api06-cost-breakdown-example.json"
API06_REQUEST = {"departure_city": "Istanbul", "destination_city": "Baghdad", "start_date": "2026-11-11",
                 "return_date": "2026-11-17", "adults": 2, "budget_usd": 2000}  # QA: SAW -> BGW
API06_DATES = ["2026-11-11", "2026-11-12", "2026-11-13", "2026-11-14", "2026-11-15", "2026-11-16", "2026-11-17"]
API06_POLICY = {"id": "api06-test-v1", "food": "Per person per day, three local meals at mid-range prices.",
                "local_transport": "Per group per day, taxi or ride-hailing inside Baghdad on days with outings."}


def api06_activity(order, name, amount, kind="estimate", category="culture", cost_type="priced",
                   includes_transport=False):
    return {"order": order, "name": name, "area": "Baghdad", "description": f"{name}.", "category": category,
            "cost": {"amount_usd": amount, "kind": kind}, "cost_type": cost_type,
            "includes_transport": includes_transport}


def api06_ai_json(ancillary="default"):
    if ancillary == "default":
        ancillary = {
            "food": {"unit_amount_usd": 25, "unit_low_usd": 20, "unit_high_usd": 35, "per": "person", "period": "day",
                     "covered_dates": API06_DATES, "basis": "Three local meals per person per day at mid-range prices."},
            "local_transport": {"unit_amount_usd": 15, "unit_low_usd": 10, "unit_high_usd": 20, "per": "group",
                                "period": "day", "covered_dates": API06_DATES[1:6],
                                "basis": "Taxi or ride-hailing inside Baghdad for the group on outing days."}}
    activities = {
        "2026-11-12": [api06_activity(1, "Iraq Museum", None, kind="unknown", cost_type="unknown"),
                       api06_activity(2, "Dinner on Abu Nuwas Street", 40, category="meal", cost_type="meal")],
        "2026-11-13": [api06_activity(1, "Babylon guided day trip", 120, includes_transport=True)],
        "2026-11-14": [api06_activity(1, "Al-Shorja Market", 0, category="shopping", cost_type="free"),
                       api06_activity(2, "Souvenir shopping", 50, category="shopping", cost_type="discretionary")],
        "2026-11-15": [api06_activity(1, "Baghdad Zoo", 0, category="nature", cost_type="priced")],
        "2026-11-16": [api06_activity(1, "Al-Mutanabbi Street walk", 0, cost_type="free")]}
    days = [{"date": d, "activities": activities.get(d, []),
             "empty_day_reason": None if d in activities else "Travel and hotel check-in/out."} for d in API06_DATES]
    return json.dumps({"itinerary": days, "ancillary_estimates": ancillary, "price_explanation": "Prices unavailable."})


def api06_generate(monkeypatch, content, policy=API06_POLICY):
    monkeypatch.setenv("TRAVELMATE_APPROVED_POLICY_IDS", API06_POLICY["id"])
    monkeypatch.setattr(tm, "_get_groq_client", lambda timeout: FakeGroq(content))
    result = generate_itinerary(dict(API06_REQUEST), {"flight": None, "hotel": None},
                                {"flights": "unavailable", "hotels": "unavailable"}, policy, request_id="tm-api06-example")
    assert result["status"] == "ok"
    return result


def test_api06_two_adult_food_and_transport_units_produce_whole_trip(monkeypatch):
    result = api06_generate(monkeypatch, api06_ai_json())
    food, transport = result["cost_breakdown"]["food"], result["cost_breakdown"]["local_transport"]
    assert (food["kind"], food["currency"], food["per"], food["period"]) == ("estimate", "USD", "person", "day")
    assert (food["covered_dates"], food["covered_travelers"]) == (API06_DATES, 2)
    assert food["whole_trip_usd"] == 350.0  # 25 USD x 7 days x 2 travelers
    assert food["whole_trip_range_usd"] == {"low_usd": 280.0, "high_usd": 490.0}
    assert food["calculation"] == "25.0 USD per person per day x 7 day(s) x 2 traveler(s) = 350.0 USD"
    assert food["included_activity_refs"] == [{"date": "2026-11-12", "order": 2}]  # Dinner allocated to food
    # Babylon day trip includes its own transport: 2026-11-13 is not charged again as local transport
    assert transport["covered_dates"] == ["2026-11-12", "2026-11-14", "2026-11-15", "2026-11-16"]
    assert transport["excluded_activity_refs"] == [{"date": "2026-11-13", "order": 1}]
    assert transport["whole_trip_usd"] == 60.0  # 15 USD x 4 days x 1 group
    assert result["ancillary_estimates"]["food"] == {"amount_usd": 350.0, "kind": "estimate", "policy_id": "api06-test-v1",
                                                     "basis": "Three local meals per person per day at mid-range prices."}
    assert result["ancillary_estimates"]["local_transport"]["amount_usd"] == 60.0
    assert result["cost_breakdown"]["provider_prices_included"] is False

    budget = calculate_budget(BudgetInput.model_validate({
        "budget_usd": 2000, "flights_data": {"selected_outbound_flight": None, "selected_return_flight": None},
        "selected_hotel": None, "activities": result["budget_activities"],
        "food": result["ancillary_estimates"]["food"]["amount_usd"],
        "local_transport": result["ancillary_estimates"]["local_transport"]["amount_usd"]}))
    assert budget.estimated_subtotal_usd == Decimal("580.00")  # Activities 120 + 50, food 350, transport 60; meal once
    assert "activities" in budget.missing_categories  # Iraq Museum and Baghdad Zoo prices stay unknown


def test_api06_activities_distinguish_meal_priced_free_discretionary_and_unknown(monkeypatch):
    result = api06_generate(monkeypatch, api06_ai_json())
    by_name = {a["label"]: a for a in result["cost_breakdown"]["activities"]}
    assert (by_name["Dinner on Abu Nuwas Street"]["cost_type"], by_name["Dinner on Abu Nuwas Street"]["allocated_to"],
            by_name["Dinner on Abu Nuwas Street"]["amount_usd"]) == ("meal", "food", 0.0)
    assert (by_name["Iraq Museum"]["cost_type"], by_name["Iraq Museum"]["amount_usd"]) == ("unknown", None)
    assert (by_name["Baghdad Zoo"]["cost_type"], by_name["Baghdad Zoo"]["kind"]) == ("unknown", "unknown")  # 0 not free
    assert (by_name["Al-Shorja Market"]["cost_type"], by_name["Al-Shorja Market"]["amount_usd"]) == ("free", 0.0)
    assert (by_name["Souvenir shopping"]["cost_type"], by_name["Souvenir shopping"]["amount_usd"]) == ("discretionary", 50.0)
    assert (by_name["Babylon guided day trip"]["cost_type"], by_name["Babylon guided day trip"]["includes_transport"]) == \
        ("priced", True)
    assert {a["source"] for a in result["cost_breakdown"]["activities"]} == {"ai_estimate"}
    codes = [w["code"] for w in result["warnings"]]
    assert "ZERO_COST_UNCONFIRMED" in codes and "MEAL_COST_REASSIGNED" in codes
    for day in result["itinerary"]:  # Public day / activity schema is unchanged
        for activity in day["activities"]:
            assert set(activity) == {"order", "name", "area", "description", "cost"}


def test_api06_missing_inputs_stay_unknown_with_reason(monkeypatch):
    no_policy = api06_generate(monkeypatch, api06_ai_json(), policy=None)["cost_breakdown"]
    assert (no_policy["food"]["kind"], no_policy["food"]["whole_trip_usd"]) == ("unknown", None)
    assert no_policy["local_transport"]["reason"] == "No approved estimation policy."

    partial = api06_generate(monkeypatch, api06_ai_json({
        "food": {"unit_amount_usd": 25, "period": "day", "basis": "No traveler scope."},
        "local_transport": {"unit_amount_usd": 15, "per": "group", "period": "day", "covered_dates": ["2026-12-01"],
                            "basis": "Date outside the trip."}}))
    assert partial["cost_breakdown"]["food"]["reason"] == \
        "AI did not return a valid food unit (unit_amount_usd, per, period)."
    assert partial["cost_breakdown"]["local_transport"]["reason"] == "local_transport covered_dates must be itinerary dates."
    assert partial["ancillary_estimates"]["food"]["kind"] == "unknown"
    assert "ESTIMATE_UNAVAILABLE" in [w["code"] for w in partial["warnings"]]

    missing = api06_generate(monkeypatch, api06_ai_json(None))["cost_breakdown"]
    assert missing["food"]["reason"] == "AI did not return a food basis under policy api06-test-v1."


def test_api06_sanitized_example_is_reproducible(monkeypatch):
    result = api06_generate(monkeypatch, api06_ai_json())
    example = json.loads(API06_EXAMPLE.read_text(encoding="utf-8"))
    assert example["trip_request"] == API06_REQUEST
    assert example["ancillary_estimates"] == result["ancillary_estimates"]
    assert example["cost_breakdown"] == result["cost_breakdown"]
