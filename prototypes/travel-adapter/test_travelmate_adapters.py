"""
TravelMate adapter tests and live evidence generator.

  python test_travelmate_adapters.py                 -> offline unit tests (no network, no API quota)
  python test_travelmate_adapters.py --live-evidence -> ONE real run that writes a sanitized evidence chain to
                                                        evidence/<request_id>/ (uses real keys from .env)

Offline tests use real provider responses recorded on 2026-10-17 (tests/fixtures/) plus explicitly SIMULATED
failures (HTTP errors, malformed AI output, exchange rates). Simulated data is labeled in each test.
When the repository backend is available, outputs are also validated with Adel's BE-04 models
(backend/app/services/models.py) and run through calculate_budget; when jsonschema is installed, public offers and
itinerary days are validated against docs/contracts/api-v0.4.schema.json.
"""
import os
import sys
import json
import copy
import math
import time
import shutil
import hashlib
import logging
import tempfile
import threading
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(BASE_DIR, "..", ".."))
FIXTURES_DIR = os.path.join(BASE_DIR, "tests", "fixtures")
SCHEMA_FILE = os.path.join(REPO_ROOT, "docs", "contracts", "api-v0.4.schema.json")
sys.path.insert(0, BASE_DIR)

import httpx
import groq
import travalmate as tm

# Optional: Adel's BE-04 models and calculator (present when this folder lives inside the repository)
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))
try:
    from app.services.models import ZiyadReportSlice, BudgetInput, HotelOffer, OfferCandidate, SelectedFlight
    from app.services.budget import calculate_budget
    BE04_AVAILABLE = True
except ImportError:
    BE04_AVAILABLE = False

# Optional: JSON Schema validation of public shapes
try:
    import jsonschema
    with open(SCHEMA_FILE, "r", encoding="utf-8") as _f:
        CONTRACT_SCHEMA = json.load(_f)
except (ImportError, OSError):
    jsonschema, CONTRACT_SCHEMA = None, None

FAKE_ENV = {
    "GOOGLE_FLIGHTS_RAPIDAPI_KEYS": "fakegooglekey01eeee",
    "SKYSCANNER_RAPIDAPI_KEYS": "fakeskykey0001aaaa,fakeskykey0002bbbb",
    "BOOKING_RAPIDAPI_KEYS": "fakebookkey001cccc,fakebookkey002dddd",
    "GROQ_API_KEY": "gsk_FAKEFAKEFAKEFAKEFAKEFAKE00",
    "TRAVELMATE_APPROVED_POLICY_IDS": "policy-test-v1"
}
FROZEN_TODAY_UTC = date(2026, 10, 20)  # Fixtures were recorded for a 2026-11-01 -> 2026-11-05 stay
FIRST_BOOKING_KEY, SECOND_BOOKING_KEY = "fakebookkey001cccc", "fakebookkey002dddd"

BASE_REQUEST = {
    "departure_city": "Istanbul",
    "destination_city": "Cairo",
    "start_date": "2026-11-01",
    "return_date": "2026-11-05",
    "adults": 2,
    "budget_usd": 2000
}
TRIP_DATES = ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"]

def load_fixture(name):
    with open(os.path.join(FIXTURES_DIR, f"{name}.json"), "r", encoding="utf-8") as f:
        return json.load(f)

def simulated_fx_payload():
    """SIMULATED exchange-rate response (fixed GBP rate) so offline tests are deterministic."""
    return {"result": "success", "time_last_update_unix": time.time() - 3600,
            "time_last_update_utc": "SIMULATED", "rates": {"USD": 1, "GBP": 0.75, "EUR": 0.9}}

def schema_errors(defname, obj):
    sub = {"$schema": CONTRACT_SCHEMA.get("$schema"), "$defs": CONTRACT_SCHEMA["$defs"], "$ref": f"#/$defs/{defname}"}
    validator = jsonschema.Draft202012Validator(sub, format_checker=jsonschema.FormatChecker())
    return [e.message for e in validator.iter_errors(obj)]

class FakeResponse:
    def __init__(self, status_code, body=None, headers=None, text=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self.text = text if text is not None else json.dumps(body)

    def json(self):
        if self._body is None:
            raise ValueError("No JSON body")
        return self._body

class FakeProviderRouter:
    """Routes mocked requests.get calls to recorded fixtures or simulated failures."""
    def __init__(self):
        self.flights = {"ist": load_fixture("flights_ist_cai"), "cai": load_fixture("flights_cai_ist")}
        self.hotels = {"1": load_fixture("hotels_cairo_2a1r"), "2": load_fixture("hotels_cairo_2a2r")}
        self.fx = simulated_fx_payload()
        # Real one-way searches recorded 2026-10-21 (2 adults): IST->CAI on 11-20 and CAI->IST on 11-23
        self.google = {"IST": load_fixture("google_flights_oneway_ist_cai_2026-11-20_2a"),
                       "CAI": load_fixture("google_flights_oneway_cai_ist_2026-11-23_2a")}
        self.overrides = {}  # service -> callable(params, headers) returning FakeResponse
        self.calls = []

    def __call__(self, url, headers=None, params=None, timeout=None):
        if "google-flights2" in url:
            service = "gflights"
        else:
            service = ("fx" if "open.er-api.com" in url else "flights" if "/skyscanner/route" in url
                       else "hotels" if "searchHotels" in url else "destination")
        self.calls.append({"service": service, "key": (headers or {}).get("x-rapidapi-key"), "params": params,
                           "timeout": timeout})
        if service in self.overrides:
            return self.overrides[service](params, headers)
        if service == "gflights":
            return FakeResponse(200, self.google[params["departure_id"]], {"X-RateLimit-Requests-Remaining": "130"})
        if service == "fx":
            return FakeResponse(200, self.fx)
        if service == "flights":
            return FakeResponse(200, self.flights[params["origin"]], {"x-ratelimit-requests-remaining": "99"})
        if service == "hotels":
            return FakeResponse(200, self.hotels[params["room_qty"]], {"x-ratelimit-requests-remaining": "99"})
        return FakeResponse(200, {"status": True, "data": []})

    def calls_for(self, service):
        return [c for c in self.calls if c["service"] == service]

    def with_exact_date_flights(self):
        """SIMULATED: move the first recorded quote of each direction onto the requested dates."""
        self.flights["ist"]["data"]["deals"][0]["legs"][0]["date"] = "2026-11-01"
        self.flights["cai"]["data"]["deals"][0]["legs"][0]["date"] = "2026-11-05"

def activity(order, name, amount=20, kind="estimate", category="culture"):
    return {"order": order, "name": name, "area": "Downtown", "description": f"{name} visit.", "category": category,
            "cost": {"amount_usd": amount, "kind": kind}}

def valid_ai_output(dates=None, explanation="Flight prices are not available for these dates.", ancillary=None):
    dates = dates or TRIP_DATES
    days = []
    for i, d in enumerate(dates):
        travel_day = i in (0, len(dates) - 1)
        days.append({"date": d, "activities": [] if travel_day else [activity(1, "Egyptian Museum")],
                     "empty_day_reason": "Travel and hotel check-in/out." if travel_day else None})
    return {"itinerary": days, "ancillary_estimates": ancillary, "price_explanation": explanation}

class FakeGroqClient:
    """SIMULATED Groq client. Records every call so tests can prove there is no automatic retry."""
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.calls = 0
        self.last_kwargs = None
        client = self

        class _Raw:
            headers = {"x-ratelimit-remaining-requests": "999"}

            def parse(self):
                message = type("M", (), {"content": client.content})()
                choice = type("C", (), {"message": message})()
                return type("R", (), {"choices": [choice], "usage": None})()

        class _WithRaw:
            @staticmethod
            def create(**kwargs):
                client.calls += 1
                client.last_kwargs = kwargs
                if client.error:
                    raise client.error
                return _Raw()

        self.chat = type("Chat", (), {"completions": type("Comp", (), {"with_raw_response": _WithRaw})()})()

def groq_status_error(error_class, status):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return error_class("simulated", response=httpx.Response(status, request=request), body=None)

class AdapterTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="travelmate_test_")
        self.env = mock.patch.dict(os.environ, FAKE_ENV)
        self.env.start()
        self.patches = [
            mock.patch.object(tm, "CACHE_FILE", os.path.join(self.temp_dir, "cache.json")),
            mock.patch.object(tm, "REPORT_FILE", os.path.join(self.temp_dir, "report.json")),
            mock.patch.object(tm, "ENV_FILE", os.path.join(self.temp_dir, ".env")),  # No real .env is ever touched
            mock.patch.object(tm, "EXHAUSTED_KEYS_FILE", os.path.join(self.temp_dir, ".env.exhausted")),
            mock.patch.object(tm, "LOCAL_KEY_ROTATION", False),
            mock.patch.object(tm, "_today_utc", lambda: FROZEN_TODAY_UTC),
            mock.patch.object(tm, "_sleep", mock.Mock()),
            mock.patch.object(tm, "FLIGHT_MODE", "disabled"),
            mock.patch.object(tm, "PRUNE_DEAD_KEYS", False),
        ]
        for p in self.patches:
            p.start()
        self.router = FakeProviderRouter()
        self.requests_patch = mock.patch.object(tm.requests, "get", side_effect=self.router)
        self.requests_get = self.requests_patch.start()
        self.groq_client = FakeGroqClient(content=json.dumps(valid_ai_output()))
        self.groq_patch = mock.patch.object(tm, "_get_groq_client", lambda timeout: self.groq_client)
        self.groq_patch.start()

    def tearDown(self):
        self.groq_patch.stop()
        self.requests_patch.stop()
        for p in reversed(self.patches):
            p.stop()
        self.env.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def run_engine(self, request=None, **kwargs):
        return tm.run_travelmate_engine(dict(BASE_REQUEST, **(request or {})), cache_mode="off", **kwargs)

    def indicative_flights(self):
        return mock.patch.object(tm, "FLIGHT_MODE", "indicative")

    def assert_be04_accepts(self, result):
        """Validates the engine output with Adel's BE-04 models and returns calculate_budget's output."""
        if not BE04_AVAILABLE:
            self.skipTest("BE-04 backend models not available")
        ZiyadReportSlice.model_validate(result["report_slice"])
        return calculate_budget(BudgetInput.model_validate(result["be04_budget_input"]))

# ==========================================
# 1. INVALID INPUT (validated BEFORE any external call)
# ==========================================
class TestInvalidInput(AdapterTestCase):
    def assert_invalid(self, field, **overrides):
        result = self.run_engine(overrides)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "invalid_input")
        self.assertEqual(set(result["error"]), {"code", "message"})  # Contract error shape
        self.assertIn(field, [f["field"] for f in result["diagnostics"]["fields"]])
        self.assertEqual(self.requests_get.call_count, 0, "No provider call may happen for invalid input")
        self.assertEqual(self.groq_client.calls, 0)

    def test_start_date_must_be_after_today_utc(self):
        self.assert_invalid("start_date", start_date="2026-10-20")
        self.assert_invalid("start_date", start_date="2026-10-19")

    def test_return_date_must_be_after_start_date(self):
        self.assert_invalid("return_date", return_date="2026-11-01")

    def test_stay_cannot_exceed_seven_nights(self):
        self.assert_invalid("return_date", return_date="2026-11-09")

    def test_wrong_date_format(self):
        self.assert_invalid("start_date", start_date="01/11/2026")

    def test_adults_contract_range_and_type(self):
        for value in (0, 5, True, 1.5, "2"):
            self.assert_invalid("adults", adults=value)

    def test_budget_must_stay_positive_after_rounding(self):
        for value in (0.004, float("nan"), float("inf"), -10, "1500"):
            self.assert_invalid("budget_usd", budget_usd=value)

    def test_city_names_must_be_text(self):
        self.assert_invalid("destination_city", destination_city="12345")
        self.assert_invalid("departure_city", departure_city=None)

    def test_unknown_public_fields_are_rejected(self):
        self.assert_invalid("rooms", rooms=2)
        self.assert_invalid("origin", origin="IST")

    def test_same_city_is_invalid(self):
        self.assert_invalid("destination_city", destination_city="Istanbul")

    def test_unsupported_city_is_not_invalid_input(self):
        result = self.run_engine({"destination_city": "Atlantis"})
        self.assertEqual(result["error"]["code"], "unsupported_search")
        self.assertEqual(self.requests_get.call_count, 0)

    def test_internal_airport_override_must_be_three_letters(self):
        with self.assertRaises(tm.TravelMateError) as ctx:
            tm.validate_request(dict(BASE_REQUEST), destination_airport="CAIR")
        self.assertEqual(ctx.exception.code, "invalid_input")

    def test_trip_request_echo_has_only_public_fields(self):
        result = self.run_engine()
        self.assertEqual(set(result["trip_request"]), set(tm.PUBLIC_REQUEST_FIELDS))

# ==========================================
# 2. PROVIDER FAILURES, RETRIES & SINGLE-KEY USE (SIMULATED HTTP errors)
# ==========================================
class TestProviderFailures(AdapterTestCase):
    def test_provider_error_is_retried_once_and_generation_continues(self):
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(500, {"message": "Internal error"})
        result = self.run_engine()
        self.assertEqual(len(self.router.calls_for("hotels")), 2)  # 1 attempt + exactly 1 retry
        self.assertEqual(result["travel"]["hotels"]["status"], "unavailable")
        self.assertEqual(result["travel"]["hotels"]["reason_code"], "provider_error")
        self.assertEqual(result["status"], "success")  # Travel errors alone never fail generation
        self.assertEqual(result["live_integration_status"], "no_price")

    def test_rate_limited_uses_only_the_first_key(self):
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(
            429, {"message": "You have exceeded the MONTHLY quota for Requests on your current plan"})
        result = self.run_engine()
        self.assertEqual(result["travel"]["hotels"]["reason_code"], "rate_limited")
        self.assertEqual([c["key"] for c in self.router.calls_for("hotels")], [FIRST_BOOKING_KEY])
        self.assertIn("TRAVEL_RATE_LIMITED", [w["code"] for w in result["warnings"]])

    def test_auth_error_does_not_fail_over_to_another_key(self):
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(403, {"message": "You are not subscribed to this API."})
        result = self.run_engine()
        self.assertEqual(result["travel"]["hotels"]["reason_code"], "auth_error")
        self.assertEqual([c["key"] for c in self.router.calls_for("hotels")], [FIRST_BOOKING_KEY])

    def test_retry_after_is_honored_once_within_deadline(self):
        responses = [FakeResponse(429, {"message": "Too many requests"}, {"Retry-After": "2"})]
        self.router.overrides["hotels"] = lambda p, h: responses.pop(0) if responses else FakeResponse(200, self.router.hotels["1"])
        result = self.run_engine()
        self.assertEqual(result["travel"]["hotels"]["status"], "available")
        tm._sleep.assert_any_call(2.0)

    def test_never_more_than_one_retry(self):
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(429, {"message": "Too many requests"}, {"Retry-After": "1"})
        self.run_engine()
        self.assertEqual(len(self.router.calls_for("hotels")), 2)

    def test_invalid_response_for_non_json_body(self):
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(200, None, text="<html>")
        self.assertEqual(self.run_engine()["travel"]["hotels"]["reason_code"], "invalid_response")

    def test_hidden_error_inside_200_response(self):
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(200, {"status": False, "message": "Something went wrong"})
        self.assertEqual(self.run_engine()["travel"]["hotels"]["reason_code"], "provider_error")

    def test_unsupported_search_for_rejected_parameters(self):
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(422, {"message": "Invalid dest_id"})
        self.assertEqual(self.run_engine()["travel"]["hotels"]["reason_code"], "unsupported_search")

    def test_timeout_when_deadline_already_passed(self):
        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        result = self.run_engine(deadline_at=past)
        self.assertEqual(result["travel"]["hotels"]["reason_code"], "timeout")
        self.assertEqual(result["error"]["code"], "timeout")  # AI also has no time left
        self.assertFalse(self.router.calls_for("hotels"))
        self.assertEqual(self.groq_client.calls, 0)

    def test_missing_credentials(self):
        with mock.patch.dict(os.environ, {"BOOKING_RAPIDAPI_KEYS": ""}):
            result = tm.search_travel(dict(BASE_REQUEST), cache_mode="off")
        self.assertEqual(result["hotels"]["reason_code"], "auth_error")

    def test_flights_disabled_by_default_makes_no_flight_calls(self):
        result = self.run_engine()
        self.assertEqual(result["travel"]["flights"]["status"], "unavailable")
        self.assertEqual(result["travel"]["flights"]["reason_code"], "not_configured")
        self.assertFalse(self.router.calls_for("flights"))
        self.assertIn("FLIGHTS_UNAVAILABLE", [w["code"] for w in result["warnings"]])

# ==========================================
# 3. FLIGHT DATE CONSISTENCY & EXCLUSION (indicative mode)
# ==========================================
class TestFlightDates(AdapterTestCase):
    def all_flight_legs(self, flights):
        legs = flights["offers"]["outbound"] + flights["offers"]["return"]
        legs += flights["alternative_date_offers"]["outbound"] + flights["alternative_date_offers"]["return"]
        return legs + [l for l in (flights["selected_outbound_flight"], flights["selected_return_flight"]) if l]

    def test_flight_date_match_flag_consistency(self):
        # Recorded data has no quote on the requested dates
        with self.indicative_flights():
            result = self.run_engine()
        flights = result["travel"]["flights"]
        legs = self.all_flight_legs(flights)
        self.assertTrue(legs)
        for leg in legs:
            self.assertEqual(leg["date_matches_request"], leg["flight_date"] == leg["requested_date"])
            expected_days = (date.fromisoformat(leg["flight_date"]) - date.fromisoformat(leg["requested_date"])).days
            self.assertEqual(leg["days_from_requested_date"], expected_days)
            if BE04_AVAILABLE:
                SelectedFlight.model_validate(leg)  # BE-04 date-flag validator
        self.assertEqual(flights["offers"]["outbound"], [])
        self.assertTrue(all(not l["date_matches_request"] for l in flights["alternative_date_offers"]["outbound"]))
        self.assertIsNone(flights["selected_outbound_flight"])
        self.assertIsNone(flights["selected_return_flight"])
        self.assertEqual(flights["reason_code"], "no_results")
        self.assertIsNone(result["selected_offers"]["selected_flight_offer_id"])
        self.assertEqual(result["travel"]["flight_candidates"], [])
        if BE04_AVAILABLE:
            self.assertIsNone(self.assert_be04_accepts(result).selected_flight_offer_id)

    def test_exact_date_flights_are_selected_with_true_flag(self):
        self.router.with_exact_date_flights()
        with self.indicative_flights():
            result = self.run_engine()
        flights = result["travel"]["flights"]
        self.assertEqual(flights["status"], "available")
        for leg in (flights["selected_outbound_flight"], flights["selected_return_flight"]):
            self.assertTrue(leg["date_matches_request"])
            self.assertEqual(leg["days_from_requested_date"], 0)
            self.assertEqual(leg["total_price_usd"], tm.round_money(leg["price_per_person_usd"] * 2))
        self.assertIn("FLIGHT_PRICES_INDICATIVE", [w["code"] for w in result["warnings"]])
        if BE04_AVAILABLE:
            budget = self.assert_be04_accepts(result)
            self.assertEqual(budget.selected_flight_offer_id, result["selected_offers"]["selected_flight_offer_id"])
            self.assertIn(budget.selected_flight_offer_id, [c["id"] for c in result["travel"]["flight_candidates"]])

    def test_selected_alternative_date_flight_is_rejected_by_ai_adapter(self):
        with self.indicative_flights():
            result = self.run_engine()
        alternative = result["travel"]["flights"]["alternative_date_offers"]["outbound"][0]
        ai = tm.generate_itinerary(dict(BASE_REQUEST), {"flight": {"selected_outbound_flight": alternative,
                                                                   "selected_return_flight": alternative}}, {})
        self.assertEqual(ai["status"], "ok")
        self.assertIn("FLIGHT_DATE_MISMATCH_EXCLUDED", [w["code"] for w in ai["warnings"]])
        self.assertIn('"selected_flights": null', self.groq_client.last_kwargs["messages"][1]["content"])

    def test_inconsistent_flag_is_never_trusted(self):
        with self.indicative_flights():
            result = self.run_engine()
        tampered = dict(result["travel"]["flights"]["alternative_date_offers"]["outbound"][0], date_matches_request=True)
        ai = tm.generate_itinerary(dict(BASE_REQUEST), {"flight": {"selected_outbound_flight": tampered,
                                                                   "selected_return_flight": tampered}}, {})
        self.assertIn("FLIGHT_DATE_MISMATCH_EXCLUDED", [w["code"] for w in ai["warnings"]])

    def test_unconvertible_flight_currency_is_excluded_with_warning(self):
        self.router.overrides["fx"] = lambda p, h: FakeResponse(503, None, text="down")  # SIMULATED outage
        with self.indicative_flights():
            result = self.run_engine()
        coverage = result["travel"]["flights"]["coverage"]["outbound"]
        self.assertEqual(coverage["excluded"]["unconvertible_currency"], coverage["deals_returned"])
        self.assertIn("CURRENCY_UNAVAILABLE", [w["code"] for w in result["warnings"]])

    def test_flight_conversion_provenance_uses_contract_fields(self):
        self.router.with_exact_date_flights()
        with self.indicative_flights():
            result = self.run_engine()
        entry = next(p for p in result["travel"]["provenance"] if p["category"] == "flights")
        self.assertEqual(set(entry["conversion"]) >= {"source", "rate_to_usd", "converted_at"}, True)
        self.assertAlmostEqual(entry["conversion"]["rate_to_usd"], 1 / 0.75, places=6)
        self.assertEqual(entry["airport_timezones"], {"departure": "Europe/Istanbul", "destination": "Africa/Cairo"})

# ==========================================
# 3.1 LIVE FLIGHTS (GOOGLE FLIGHTS, recorded real responses from 2026-10-21)
# ==========================================
LIVE_REQUEST = {"departure_city": "Istanbul", "destination_city": "Cairo", "start_date": "2026-11-20",
                "return_date": "2026-11-23", "adults": 2, "budget_usd": 2000}
LIVE_AI_DATES = ["2026-11-20", "2026-11-21", "2026-11-22", "2026-11-23"]

class TestLiveFlights(AdapterTestCase):
    """Google Flights live mode. Fixtures: real one-way searches recorded 2026-10-21 (IST->CAI 11-20, CAI->IST 11-23)."""
    def setUp(self):
        super().setUp()
        self.mode = mock.patch.object(tm, "FLIGHT_MODE", "live")
        self.mode.start()
        self.groq_client.content = json.dumps(valid_ai_output(dates=LIVE_AI_DATES))

    def tearDown(self):
        self.mode.stop()
        super().tearDown()

    def run_live(self, request=None, **kwargs):
        return tm.run_travelmate_engine(dict(LIVE_REQUEST, **(request or {})), cache_mode="off", **kwargs)

    def google_calls(self):
        return self.router.calls_for("gflights")

    def options(self, airport):
        it = self.router.google[airport]["data"]["itineraries"]
        return it["topFlights"] + it["otherFlights"]

    def test_round_trip_uses_two_parallel_one_way_searches(self):
        self.run_live()
        calls = sorted(self.google_calls(), key=lambda c: c["params"]["departure_id"])
        self.assertEqual([(c["params"]["departure_id"], c["params"]["arrival_id"], c["params"]["outbound_date"]) for c in calls],
                         [("CAI", "IST", "2026-11-23"), ("IST", "CAI", "2026-11-20")])
        for call in calls:
            self.assertNotIn("return_date", call["params"])  # One-way searches: each leg has its own real price
            self.assertEqual(call["params"]["adults"], "2")

    def test_live_legs_carry_real_provider_totals(self):
        result = self.run_live()
        legs = result["report_slice"]["flights_data"]
        outbound, returning = legs["selected_outbound_flight"], legs["selected_return_flight"]
        self.assertEqual(outbound["total_price_usd"], min(o["price"] for o in self.options("IST")))  # $272, provider total
        self.assertEqual(returning["total_price_usd"], min(o["price"] for o in self.options("CAI")))  # $223, provider total
        for leg in (outbound, returning):
            self.assertTrue(leg["date_matches_request"])
            self.assertEqual(leg["date_matches_request"], leg["flight_date"] == leg["requested_date"])
            self.assertEqual(leg["travelers"], 2)
            self.assertEqual(leg["price_per_person_usd"], tm.round_money(leg["total_price_usd"] / 2))
            if BE04_AVAILABLE:
                SelectedFlight.model_validate(leg)
        self.assertEqual(result["travel"]["flights"]["selected_offer"]["price"]["amount_usd"], 495.0)

    def test_live_be04_prices_the_real_legs(self):
        result = self.run_live()
        be04 = result["be04_budget_input"]
        self.assertNotIn("flight_candidates", be04)  # Round trips use the real legs, not candidate mode
        selected_id = result["selected_offers"]["selected_flight_offer_id"]
        self.assertEqual(selected_id, tm.round_trip_offer_id(be04["flights_data"]["selected_outbound_flight"],
                                                             be04["flights_data"]["selected_return_flight"]))
        if BE04_AVAILABLE:
            budget = self.assert_be04_accepts(result)
            line = next(c for c in budget.cost_items if c.category == "flights")
            self.assertEqual((line.kind, float(line.amount_usd), line.source_offer_id), ("provider", 495.0, selected_id))
            self.assertFalse([c for c in budget.cost_items if c.id == "flight-taxes-fees"])
            self.assertEqual(budget.selected_flight_offer_id, selected_id)

    def test_round_trip_public_offers_match_schema_and_local_dates(self):
        result = self.run_live()
        offers = result["travel"]["flights"]["round_trip_offers"]
        self.assertTrue(offers)
        self.assertEqual(len({o["id"] for o in offers}), len(offers))  # Unique offer IDs
        self.assertEqual([o["id"] for o in offers], [c["id"] for c in result["travel"]["flight_candidates"]])
        for offer in offers:
            self.assertEqual(tm.utc_to_local_date(offer["outbound_departure_at"], offer["departure_airport_code"]), "2026-11-20")
            self.assertEqual(tm.utc_to_local_date(offer["return_departure_at"], offer["arrival_airport_code"]), "2026-11-23")
            self.assertEqual(offer["taxes"], {"status": "included", "additional_amount_usd": 0.0})
            if CONTRACT_SCHEMA is not None:
                self.assertEqual(schema_errors("flight", offer), [])

    def test_one_way_trip(self):
        result = self.run_live({"trip_type": "one_way"})
        self.assertEqual([c["params"]["departure_id"] for c in self.google_calls()], ["IST"])  # 1 call only
        legs = result["report_slice"]["flights_data"]
        self.assertIsNone(legs["selected_return_flight"])
        self.assertEqual(legs["selected_outbound_flight"]["total_price_usd"], 272.0)
        offer = result["travel"]["flights"]["selected_offer"]
        self.assertIsNone(offer["return_departure_at"])  # Needs a contract extension (v0.4 is round trip only)
        self.assertEqual(result["trip_request"]["trip_type"], "one_way")
        if BE04_AVAILABLE:
            budget = self.assert_be04_accepts(result)  # Candidate mode for one-way trips
            line = next(c for c in budget.cost_items if c.category == "flights")
            self.assertEqual((line.kind, float(line.amount_usd)), ("provider", 272.0))
        self.assertEqual(result["status"], "success")

    def test_invalid_trip_type_is_rejected(self):
        result = self.run_live({"trip_type": "multi_city"})
        self.assertEqual(result["error"]["code"], "invalid_input")
        self.assertFalse(self.google_calls())

    def test_duplicate_flights_are_deduplicated(self):
        top = self.router.google["IST"]["data"]["itineraries"]["topFlights"]
        top.append(dict(copy.deepcopy(top[0]), price=top[0]["price"] + 40))  # SIMULATED same flight, other fare
        result = self.run_live()
        outbound = result["travel"]["flights"]["offers"]["outbound"]
        self.assertEqual(len({tm.flight_leg_id(l) + str(l["total_price_usd"]) for l in outbound}), len(outbound))
        self.assertEqual(outbound[0]["total_price_usd"], 272.0)
        self.assertGreaterEqual(result["travel"]["flights"]["coverage"]["outbound"]["excluded"]["duplicate"], 1)

    def test_unpadded_provider_dates_are_normalized(self):
        option = copy.deepcopy(self.options("IST")[0])
        option["flights"][0]["departure_airport"]["time"] = "2026-11-1 9:35"   # Seen live: unpadded day and hour
        option["flights"][-1]["arrival_airport"]["time"] = "2026-11-1 10:40"
        summary, problem = tm.summarize_google_option(option, ["IST"], ["CAI"], "2026-11-01")
        self.assertIsNone(problem)
        self.assertEqual(summary["departure_local"], "2026-11-01 09:35")
        self.assertEqual(summary["departure_date"], "2026-11-01")

    def test_live_times_converted_to_utc(self):
        schedule = self.run_live()["travel"]["flights"]["schedule"]
        self.assertEqual(schedule["outbound"]["departure_utc"], "2026-11-20T09:15:00Z")  # SM 304 12:15 Istanbul (UTC+3)
        self.assertEqual(schedule["return"]["departure_utc"], "2026-11-23T21:20:00Z")    # MS 745 23:20 Cairo (UTC+2)

    def test_live_stops_counted_from_segments(self):
        option = next(o for o in self.options("IST") if len(o["flights"]) > 1)
        self.assertEqual(option["stops"], 0)  # Recorded provider value is wrong
        summary, problem = tm.summarize_google_option(option, ["IST", "SAW"], ["CAI"], "2026-11-20")
        self.assertIsNone(problem)
        self.assertEqual(summary["stops"], len(option["flights"]) - 1)
        self.assertEqual(summary["transit_airports"], [option["flights"][0]["arrival_airport"]["airport_code"]])

    def test_live_excludes_date_route_self_transfer_and_bad_prices(self):
        top = self.router.google["IST"]["data"]["itineraries"]["topFlights"]
        top[0]["flights"][0]["departure_airport"]["time"] = "2026-11-21 12:15"   # SIMULATED date mismatch
        top[1]["flights"][-1]["arrival_airport"]["airport_code"] = "DXB"         # SIMULATED route mismatch
        top[2]["self_transfer"] = True                                            # SIMULATED separate tickets
        top[3]["price"] = float("nan")                                            # SIMULATED invalid price
        excluded = self.run_live()["travel"]["flights"]["coverage"]["outbound"]["excluded"]
        for reason in ("date_mismatch", "route_mismatch", "self_transfer", "invalid_price"):
            self.assertGreaterEqual(excluded[reason], 1, reason)

    def test_return_leg_failure_gives_no_partial_round_trip(self):
        self.router.overrides["gflights"] = lambda p, h: (
            FakeResponse(500, {"message": "down"}) if p["departure_id"] == "CAI"
            else FakeResponse(200, self.router.google["IST"]))
        result = self.run_live()
        flights = result["travel"]["flights"]
        self.assertEqual((flights["status"], flights["reason_code"]), ("unavailable", "provider_error"))
        self.assertIsNone(flights["selected_outbound_flight"])  # Never a half round trip
        self.assertEqual(result["travel"]["flight_candidates"], [])
        self.assertEqual(result["status"], "success")

    def test_google_timeout_is_not_retried(self):
        def slow(params, headers):
            raise tm.requests.Timeout("SIMULATED slow provider")
        self.router.overrides["gflights"] = slow
        result = self.run_live()
        self.assertEqual(result["travel"]["flights"]["reason_code"], "timeout")
        self.assertEqual(len(self.google_calls()), 2)  # One attempt per direction, no retry
        self.assertTrue(self.router.calls_for("hotels"))  # Hotels still searched in parallel
        self.assertEqual(result["status"], "success")

    def test_flight_timeout_value(self):
        self.run_live()
        for call in self.google_calls():
            self.assertLessEqual(call["timeout"], tm.GOOGLE_FLIGHTS_TIMEOUT_SECONDS)

    def test_ai_time_is_reserved_within_deadline(self):
        deadline = datetime.now(timezone.utc) + timedelta(seconds=45)
        result = self.run_live(deadline_at=deadline)
        for call in self.google_calls() + self.router.calls_for("hotels"):
            self.assertLessEqual(call["timeout"], 45 - tm.AI_RESERVED_SECONDS + 0.5)
        self.assertEqual(self.groq_client.calls, 1)
        self.assertEqual(result["status"], "success")

    def test_ai_receives_live_flight_local_times(self):
        self.run_live()
        context = self.groq_client.last_kwargs["messages"][1]["content"]
        self.assertIn('"outbound_departure_local": "2026-11-20 12:15"', context)
        self.assertIn('"return_departure_local": "2026-11-23 23:20"', context)

    def test_ai_rejects_tampered_leg(self):
        result = self.run_live()
        legs = dict(result["report_slice"]["flights_data"])
        legs["selected_outbound_flight"] = dict(legs["selected_outbound_flight"], flight_date="2026-11-21")
        ai = tm.generate_itinerary(dict(LIVE_REQUEST), {"flight": legs, "hotel": None}, {})
        self.assertIn("FLIGHT_DATE_MISMATCH_EXCLUDED", [w["code"] for w in ai["warnings"]])

    def test_live_cache_hit_uses_no_flight_calls(self):
        tm.run_travelmate_engine(dict(LIVE_REQUEST))
        calls = len(self.google_calls())
        tm.run_travelmate_engine(dict(LIVE_REQUEST))
        self.assertEqual(len(self.google_calls()), calls)

# ==========================================
# 4. HOTEL ELIGIBILITY, FEES & OFFER IDS
# ==========================================
class TestHotels(AdapterTestCase):
    def hotels_with(self, mutate, fixture="1"):
        data = copy.deepcopy(self.router.hotels[fixture])
        mutate(data["data"]["hotels"])
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(200, data)
        return data

    def test_hotel_and_flight_included_in_base_fees(self):
        def fees(hotels):
            hotels[0]["property"]["priceBreakdown"]["excludedPrice"]["value"] = 0  # SIMULATED all-inclusive price
            del hotels[1]["property"]["priceBreakdown"]["excludedPrice"]          # SIMULATED unknown fees
        data = self.hotels_with(fees)
        self.router.with_exact_date_flights()
        with self.indicative_flights():
            result = self.run_engine()
        travel = result["travel"]
        by_id = {c["id"]: c for c in travel["hotel_candidates"]}
        public = {o["id"]: o for o in travel["hotels"]["public_offers"]}
        included_id, unknown_id = (str(h["hotel_id"]) for h in data["data"]["hotels"][:2])

        self.assertEqual(by_id[included_id], {"id": included_id, "base_usd": by_id[included_id]["base_usd"],
                                              "additional_fees_usd": None, "included_in_base": True})
        self.assertEqual(public[included_id]["taxes"], {"status": "included", "additional_amount_usd": 0.0})
        self.assertFalse(by_id[unknown_id]["included_in_base"])
        self.assertIsNone(by_id[unknown_id]["additional_fees_usd"])
        self.assertEqual(public[unknown_id]["taxes"]["status"], "unknown")
        for candidate in travel["hotel_candidates"]:
            if candidate["id"] not in (included_id, unknown_id):
                self.assertFalse(candidate["included_in_base"])
                self.assertGreater(candidate["additional_fees_usd"], 0)
        for candidate in travel["flight_candidates"]:
            self.assertTrue(candidate["included_in_base"])
            self.assertIsNone(candidate["additional_fees_usd"])

        if BE04_AVAILABLE:
            for candidate in travel["hotel_candidates"] + travel["flight_candidates"]:
                OfferCandidate.model_validate(candidate)
            budget = calculate_budget(BudgetInput.model_validate({
                "budget_usd": 5000, "flights_data": {}, "selected_hotel": None,
                "hotel_candidates": [by_id[included_id]], "flight_candidates": travel["flight_candidates"][:1]}))
            fee_lines = [c for c in budget.cost_items if c.category == "taxes_fees" and c.source_offer_id is not None]
            self.assertEqual(fee_lines, [], "All-inclusive offers must not produce a fee line")

    def test_hotel_offer_id_is_string_and_matches_source(self):
        result = self.run_engine()
        travel = result["travel"]
        hotel_ids = [h["hotel_id"] for h in travel["hotels"]["offers"]]
        self.assertTrue(all(isinstance(i, int) for i in hotel_ids))  # BE-04 HotelOffer.hotel_id is an int
        for key in ("hotel_candidates",):
            self.assertEqual([c["id"] for c in travel[key]], [str(i) for i in hotel_ids])
        self.assertEqual([o["id"] for o in travel["hotels"]["public_offers"]], [str(i) for i in hotel_ids])
        self.assertTrue(all(isinstance(c["id"], str) for c in travel["hotel_candidates"]))
        selected_id = result["selected_offers"]["selected_hotel_offer_id"]
        self.assertIsInstance(selected_id, str)
        self.assertIn(selected_id, [p["offer_id"] for p in travel["provenance"]])
        if BE04_AVAILABLE:
            budget = self.assert_be04_accepts(result)
            self.assertEqual(budget.selected_hotel_offer_id, selected_id)
            accommodation = next(c for c in budget.cost_items if c.category == "accommodation")
            self.assertEqual(accommodation.source_offer_id, selected_id)
            candidate_budget = calculate_budget(BudgetInput.model_validate({
                "budget_usd": 5000, "flights_data": {}, "selected_hotel": None,
                "hotel_candidates": travel["hotel_candidates"]}))
            self.assertIn(candidate_budget.selected_hotel_offer_id, [c["id"] for c in travel["hotel_candidates"]])

    def test_known_taxes_are_added_exactly_once(self):
        result = self.run_engine()
        for hotel in result["travel"]["hotels"]["offers"]:
            self.assertEqual(hotel["total_price_usd"], tm.round_money(hotel["base_price_usd"] + hotel["taxes_and_fees_usd"]))
            if BE04_AVAILABLE:
                HotelOffer.model_validate(hotel)  # BE-04 total == base + taxes validator

    def test_missing_taxes_stay_unknown_never_zero(self):
        data = self.hotels_with(lambda hotels: hotels[0]["property"]["priceBreakdown"].pop("excludedPrice"))
        result = self.run_engine()
        hotel = next(h for h in result["travel"]["hotels"]["offers"] if h["hotel_id"] == data["data"]["hotels"][0]["hotel_id"])
        self.assertIsNone(hotel["taxes_and_fees_usd"])
        self.assertIsNone(hotel["total_price_usd"])
        self.assertIn("TAXES_UNKNOWN", [w["code"] for w in result["warnings"]])

    def test_negative_nan_and_infinity_prices_are_rejected(self):
        def corrupt(hotels):
            hotels[0]["property"]["priceBreakdown"]["grossPrice"]["value"] = -50
            hotels[1]["property"]["priceBreakdown"]["grossPrice"]["value"] = float("nan")
            hotels[2]["property"]["priceBreakdown"]["grossPrice"]["value"] = float("inf")
            hotels[3]["property"]["priceBreakdown"]["excludedPrice"]["value"] = -1
        self.hotels_with(corrupt)
        result = self.run_engine()
        self.assertEqual(result["travel"]["hotels"]["coverage"]["excluded"]["invalid_price"], 4)

    def test_occupancy_and_date_mismatches_are_excluded(self):
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(200, self.router.hotels["2"])  # Answers for 2 rooms
        result = self.run_engine()
        self.assertEqual(result["travel"]["hotels"]["reason_code"], "no_results")
        self.assertGreater(result["travel"]["hotels"]["coverage"]["excluded"]["occupancy_mismatch"], 0)
        result = self.run_engine({"adults": 3})
        self.assertEqual(result["travel"]["hotels"]["reason_code"], "no_results")
        result = self.run_engine({"return_date": "2026-11-06"})
        self.assertGreater(result["travel"]["hotels"]["coverage"]["excluded"]["date_mismatch"], 0)

    def test_hotel_far_from_city_is_excluded(self):
        self.hotels_with(lambda hotels: hotels[0]["property"].update(latitude=21.4))  # SIMULATED: moved to Jeddah
        self.assertEqual(self.run_engine()["travel"]["hotels"]["coverage"]["excluded"]["destination_mismatch"], 1)

    def test_unreviewed_hotel_has_null_review_score(self):
        data = self.hotels_with(lambda hotels: hotels[0]["property"].update(reviewScore=0, reviewCount=0))
        hotel = next(h for h in self.run_engine()["travel"]["hotels"]["offers"]
                     if h["hotel_id"] == data["data"]["hotels"][0]["hotel_id"])
        self.assertIsNone(hotel["review_score"])

    def test_unverified_occupancy_is_excluded(self):
        self.hotels_with(lambda hotels: hotels[0].update(accessibilityLabel="Some hotel. 900 USD."))
        self.assertEqual(self.run_engine()["travel"]["hotels"]["coverage"]["excluded"]["occupancy_unverified"], 1)

    def test_no_results_when_provider_returns_no_hotels(self):
        self.hotels_with(lambda hotels: hotels.clear())
        result = self.run_engine()
        self.assertEqual(result["travel"]["hotels"], result["travel"]["hotels"] | {"status": "unavailable", "reason_code": "no_results", "offers": []})
        self.assertIn("HOTELS_UNAVAILABLE", [w["code"] for w in result["warnings"]])

    @unittest.skipIf(CONTRACT_SCHEMA is None, "jsonschema or contract schema not available")
    def test_public_hotel_offers_match_v04_schema(self):
        for offer in self.run_engine()["travel"]["hotels"]["public_offers"]:
            self.assertEqual(schema_errors("hotel", offer), [])

    def test_hotel_provenance_has_contract_fields(self):
        required = {"offer_id", "original_currency", "original_amount", "quote_timestamp", "conversion",
                    "provider_query", "coverage_evidence", "airport_timezones"}
        for entry in self.run_engine()["travel"]["provenance"]:
            self.assertTrue(required <= set(entry))
            self.assertTrue(entry["coverage_evidence"])
            self.assertIsNone(entry["airport_timezones"])

# ==========================================
# 5. AI OUTPUT VALIDATION, MEALS & RESILIENCE (SIMULATED AI responses)
# ==========================================
class TestAIOutput(AdapterTestCase):
    def ai_result(self, content=None, error=None, **engine_kwargs):
        self.groq_client.content = content
        self.groq_client.error = error
        return self.run_engine(**engine_kwargs)

    def assert_invalid_output(self, result):
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "invalid_output")
        self.assertNotIn("itinerary", result["ai_itinerary"])
        self.assertIsNone(result["be04_budget_input"])

    def test_valid_itinerary_is_published(self):
        result = self.ai_result(json.dumps(valid_ai_output()))
        itinerary = result["ai_itinerary"]["itinerary"]
        self.assertEqual(result["ai_itinerary"]["status"], "ok")
        self.assertEqual([d["date"] for d in itinerary], TRIP_DATES)
        self.assertEqual(self.groq_client.last_kwargs["temperature"], 0.1)
        if CONTRACT_SCHEMA is not None:
            for day in itinerary:
                self.assertEqual(schema_errors("day", day), [])
        if BE04_AVAILABLE:
            self.assert_be04_accepts(result)

    def test_malformed_json_fails_safely(self):
        self.assert_invalid_output(self.ai_result("Here is your trip: {not json"))

    def test_wrong_number_of_days_fails(self):
        self.assert_invalid_output(self.ai_result(json.dumps(valid_ai_output(dates=TRIP_DATES[:2]))))

    def test_wrong_date_order_fails(self):
        output = valid_ai_output()
        output["itinerary"][1]["date"], output["itinerary"][2]["date"] = TRIP_DATES[2], TRIP_DATES[1]
        self.assert_invalid_output(self.ai_result(json.dumps(output)))

    def test_empty_middle_day_fails(self):
        output = valid_ai_output()
        output["itinerary"][2]["activities"] = []
        self.assert_invalid_output(self.ai_result(json.dumps(output)))

    def test_empty_travel_day_without_reason_fails(self):
        output = valid_ai_output()
        output["itinerary"][0]["empty_day_reason"] = None
        self.assert_invalid_output(self.ai_result(json.dumps(output)))

    def test_non_contiguous_order_fails(self):
        output = valid_ai_output()
        output["itinerary"][1]["activities"][0]["order"] = 2
        self.assert_invalid_output(self.ai_result(json.dumps(output)))

    def test_blank_strings_between_activities_are_removed(self):
        # Real artifact from the 2026-10-21 live run: "" items between valid activity objects
        output = valid_ai_output()
        output["itinerary"][1]["activities"] = [activity(1, "Egyptian Museum"), "", activity(2, "Nile walk"), "  "]
        result = self.ai_result(json.dumps(output))
        self.assertEqual(result["status"], "success")
        self.assertEqual([a["order"] for a in result["ai_itinerary"]["itinerary"][1]["activities"]], [1, 2])
        self.assertIn("AI_OUTPUT_NORMALIZED", [w["code"] for w in result["warnings"]])

    def test_estimate_without_amount_becomes_unknown(self):
        # Real artifact from the 2026-10-21 live run: {"amount_usd": null, "kind": "estimate"}
        output = valid_ai_output()
        output["itinerary"][1]["activities"][0]["cost"] = {"amount_usd": None, "kind": "estimate"}
        result = self.ai_result(json.dumps(output))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["ai_itinerary"]["itinerary"][1]["activities"][0]["cost"],
                         {"amount_usd": None, "kind": "unknown", "coverage": None})
        self.assertIn("AI_OUTPUT_NORMALIZED", [w["code"] for w in result["warnings"]])

    def test_invalid_estimate_amount_still_fails(self):
        output = valid_ai_output()
        output["itinerary"][1]["activities"][0]["cost"] = {"amount_usd": -5, "kind": "estimate"}
        self.assert_invalid_output(self.ai_result(json.dumps(output)))

    def test_non_blank_non_object_activity_still_fails(self):
        output = valid_ai_output()
        output["itinerary"][1]["activities"].append("Visit a museum")
        self.assert_invalid_output(self.ai_result(json.dumps(output)))

    def test_incomplete_activity_fails(self):
        output = valid_ai_output()
        output["itinerary"][1]["activities"][0] = {"order": 1, "name": "Museum", "cost": {"kind": "estimate"}}
        self.assert_invalid_output(self.ai_result(json.dumps(output)))

    def test_ai_activity_rejects_provider_cost_kind(self):
        output = valid_ai_output()
        output["itinerary"][1]["activities"][0]["cost"]["kind"] = "provider"
        result = self.ai_result(json.dumps(output))
        self.assert_invalid_output(result)
        self.assertTrue(any("'provider'" in p for p in result["diagnostics"]["problems"]))
        # Valid runs never contain "provider" anywhere in activities or BE-04 activity items
        valid = self.ai_result(json.dumps(valid_ai_output()))
        kinds = {a["cost"]["kind"] for d in valid["ai_itinerary"]["itinerary"] for a in d["activities"]}
        self.assertTrue(kinds <= {"estimate", "unknown"})
        self.assertTrue({a["kind"] for a in valid["be04_budget_input"]["activities"]} <= {"estimate", "unknown"})

    def test_unknown_cost_with_amount_fails(self):
        output = valid_ai_output()
        output["itinerary"][1]["activities"][0]["cost"] = {"amount_usd": 15, "kind": "unknown"}
        self.assert_invalid_output(self.ai_result(json.dumps(output)))

    def test_meal_cost_deduplication(self):
        output = valid_ai_output(ancillary={"food": {"amount_usd": 400, "basis": "40 USD per person per day"},
                                            "local_transport": {"amount_usd": 100, "basis": "10 USD per person per day"}})
        output["itinerary"][1]["activities"].append(activity(2, "Dinner on the Nile", amount=60, category="meal"))
        output["itinerary"][2]["activities"].append(activity(2, "Lunch at a local restaurant", amount=30, category="other"))
        policy = {"id": "policy-test-v1", "food": "40 USD per person per day", "local_transport": "10 USD per person per day"}
        result = self.ai_result(json.dumps(output), estimation_policy=policy)
        ai = result["ai_itinerary"]
        meals = [a for d in ai["itinerary"] for a in d["activities"] if a["name"].startswith(("Dinner", "Lunch"))]
        self.assertEqual([m["cost"] for m in meals], [{"amount_usd": 0.0, "kind": "estimate", "coverage": "all_travelers"}] * 2)
        self.assertNotIn("category", meals[0])  # Internal hint never leaks into the public activity
        self.assertEqual(ai["ancillary_estimates"]["food"], {"amount_usd": 400.0, "kind": "estimate",
                                                             "basis": "40 USD per person per day", "policy_id": "policy-test-v1"})
        self.assertIn("MEAL_COST_REASSIGNED", [w["code"] for w in result["warnings"]])
        activity_total = sum(a["amount_usd"] or 0 for a in result["be04_budget_input"]["activities"])
        self.assertEqual(activity_total, 60.0)  # 3 museum visits x 20; meals add nothing
        if BE04_AVAILABLE:
            budget = self.assert_be04_accepts(result)
            self.assertEqual(budget.estimated_subtotal_usd, 60 + 400 + 100)  # Meals counted once, inside food

    def test_food_and_transport_unknown_without_approved_policy(self):
        output = valid_ai_output(ancillary={"food": {"amount_usd": 400, "basis": "invented"}})
        result = self.ai_result(json.dumps(output), estimation_policy={"id": "not-reviewed", "food": "x", "local_transport": None})
        estimates = result["ai_itinerary"]["ancillary_estimates"]
        self.assertEqual(estimates["food"], {"amount_usd": None, "kind": "unknown",
                                             "basis": "No approved estimation policy.", "policy_id": None})
        self.assertEqual(estimates["local_transport"]["kind"], "unknown")
        self.assertIsNone(result["be04_budget_input"]["food"])
        self.assertIn("POLICY_NOT_APPROVED", [w["code"] for w in result["warnings"]])

    def test_ai_itinerary_resilience_when_travel_offers_unavailable(self):
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(500, {"message": "down"})  # SIMULATED outage
        result = self.run_engine()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["live_integration_status"], "no_price")
        self.assertEqual(result["report_slice"]["hotels_data"], [])
        self.assertEqual(result["report_slice"]["flights_data"], {"selected_outbound_flight": None, "selected_return_flight": None})
        self.assertEqual(len(result["ai_itinerary"]["itinerary"]), 5)
        context = self.groq_client.last_kwargs["messages"][1]["content"]
        self.assertIn('"selected_hotel": null', context)
        self.assertIn('"selected_flights": null', context)
        if BE04_AVAILABLE:
            self.assertEqual(self.assert_be04_accepts(result).status, "uncertain")
        direct = tm.generate_itinerary(dict(BASE_REQUEST), {"flight": None, "hotel": None},
                                       {"flights": "unavailable", "hotels": "unavailable"})
        self.assertEqual(direct["status"], "ok")

    def test_ai_is_never_retried_automatically(self):
        result = self.ai_result(error=groq_status_error(groq.InternalServerError, 500))
        self.assertEqual(self.groq_client.calls, 1)
        self.assertEqual(result["error"]["code"], "unavailable")
        self.assertEqual(result["ai_itinerary"]["provenance"]["automatic_retries"], 0)

    def test_ai_error_mapping_uses_contract_codes(self):
        self.assertEqual(self.ai_result(error=groq_status_error(groq.RateLimitError, 429))["error"]["code"], "rate_limited")
        self.assertEqual(self.ai_result(error=groq_status_error(groq.AuthenticationError, 401))["error"]["code"], "unavailable")

    def test_ai_skipped_when_deadline_too_short(self):
        result = tm.generate_itinerary(dict(BASE_REQUEST), {}, {}, deadline_at=datetime.now(timezone.utc) + timedelta(seconds=2))
        self.assertEqual(result["error"]["code"], "timeout")
        self.assertEqual(self.groq_client.calls, 0)

    def test_missing_ai_key_is_unavailable(self):
        self.groq_patch.stop()
        try:
            with mock.patch.dict(os.environ, {"GROQ_API_KEY": ""}):
                result = tm.generate_itinerary(dict(BASE_REQUEST), {}, {})
        finally:
            self.groq_patch.start()
        self.assertEqual(result["error"]["code"], "unavailable")

    def test_invented_price_in_explanation_is_dropped(self):
        result = self.ai_result(json.dumps(valid_ai_output(explanation="The whole trip costs $1234.56.")))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["report_slice"]["ai_recommendation_report"], "")
        self.assertIn("PRICE_EXPLANATION_DROPPED", [w["code"] for w in result["warnings"]])

# ==========================================
# 6. LOCAL .ENV DEAD-KEY PRUNING
# ==========================================
class TestKeyPruning(AdapterTestCase):
    def write_env(self, content):
        with open(tm.ENV_FILE, "w", encoding="utf-8") as f:
            f.write(content)

    def read_env(self, path=None):
        with open(path or tm.ENV_FILE, "r", encoding="utf-8") as f:
            return f.read()

    def test_local_env_dead_key_pruning(self):
        original = (f"# local secrets\nGROQ_API_KEY=gsk_FAKEFAKEFAKEFAKEFAKEFAKE00\n"
                    f"BOOKING_RAPIDAPI_KEYS={FIRST_BOOKING_KEY},{SECOND_BOOKING_KEY}\nTRAVELMATE_FLIGHT_MODE=disabled\n")
        self.write_env(original)
        self.router.overrides["hotels"] = lambda p, h: (
            FakeResponse(429, {"message": "You have exceeded the MONTHLY quota for Requests on your current plan"})
            if h["x-rapidapi-key"] == FIRST_BOOKING_KEY else FakeResponse(200, self.router.hotels["1"]))
        with mock.patch.object(tm, "PRUNE_DEAD_KEYS", True):
            first = self.run_engine()
            # The failing request is NOT retried with another key
            self.assertEqual(first["travel"]["hotels"]["reason_code"], "rate_limited")
            self.assertEqual([c["key"] for c in self.router.calls_for("hotels")], [FIRST_BOOKING_KEY])
            # The dead key is gone from .env, the next key is now primary, the rest of the file is untouched
            env_after = self.read_env()
            self.assertIn(f"BOOKING_RAPIDAPI_KEYS={SECOND_BOOKING_KEY}\n", env_after)
            self.assertNotIn(FIRST_BOOKING_KEY, env_after)
            self.assertIn("# local secrets", env_after)
            self.assertIn("TRAVELMATE_FLIGHT_MODE=disabled", env_after)
            self.assertEqual(self.read_env(tm.ENV_FILE + ".bak"), original)
            self.assertEqual(tm.load_key_pool("BOOKING"), [SECOND_BOOKING_KEY])
            # The NEXT request uses the promoted key
            second = self.run_engine()
            self.assertEqual(second["travel"]["hotels"]["status"], "available")
            self.assertEqual(self.router.calls_for("hotels")[-1]["key"], SECOND_BOOKING_KEY)

    def test_auth_error_key_is_pruned_including_indexed_form(self):
        self.write_env(f"BOOKING_RAPIDAPI_KEY_1={FIRST_BOOKING_KEY}\nBOOKING_RAPIDAPI_KEY_2={SECOND_BOOKING_KEY}\n")
        with mock.patch.dict(os.environ, {"BOOKING_RAPIDAPI_KEYS": "", "BOOKING_RAPIDAPI_KEY_1": FIRST_BOOKING_KEY,
                                          "BOOKING_RAPIDAPI_KEY_2": SECOND_BOOKING_KEY}):
            self.router.overrides["hotels"] = lambda p, h: FakeResponse(403, {"message": "You are not subscribed to this API."})
            with mock.patch.object(tm, "PRUNE_DEAD_KEYS", True):
                self.run_engine()
            self.assertEqual(self.read_env(), f"BOOKING_RAPIDAPI_KEY_2={SECOND_BOOKING_KEY}\n")
            self.assertEqual(tm.load_key_pool("BOOKING"), [SECOND_BOOKING_KEY])

    def test_transient_rate_limit_never_prunes(self):
        original = f"BOOKING_RAPIDAPI_KEYS={FIRST_BOOKING_KEY},{SECOND_BOOKING_KEY}\n"
        self.write_env(original)
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(429, {"message": "Too many requests"})
        with mock.patch.object(tm, "PRUNE_DEAD_KEYS", True):
            self.run_engine()
        self.assertEqual(self.read_env(), original)

    def quota_on(self, *dead_keys):
        """SIMULATED: listed keys answer 429 monthly quota (with a reset header), others return hotels."""
        def respond(params, headers):
            if headers["x-rapidapi-key"] in dead_keys:
                return FakeResponse(429, {"message": "You have exceeded the MONTHLY quota for Requests on your current plan"},
                                    {"x-ratelimit-requests-reset": "86400"})
            return FakeResponse(200, self.router.hotels["1"])
        self.router.overrides["hotels"] = respond

    def test_local_key_rotation_moves_dead_key_and_continues(self):
        self.write_env(f"BOOKING_RAPIDAPI_KEYS={FIRST_BOOKING_KEY},{SECOND_BOOKING_KEY}\n")
        self.quota_on(FIRST_BOOKING_KEY)
        with mock.patch.object(tm, "LOCAL_KEY_ROTATION", True):
            result = self.run_engine()
        # Same request continues with the next key, without stopping
        self.assertEqual(result["travel"]["hotels"]["status"], "available")
        self.assertEqual([c["key"] for c in self.router.calls_for("hotels")], [FIRST_BOOKING_KEY, SECOND_BOOKING_KEY])
        self.assertEqual(self.read_env(), f"BOOKING_RAPIDAPI_KEYS={SECOND_BOOKING_KEY}\n")
        archive = self.read_env(tm.EXHAUSTED_KEYS_FILE)
        self.assertIn(f"BOOKING_RAPIDAPI_KEYS={FIRST_BOOKING_KEY}\n", archive)
        self.assertIn("quota_exhausted | quota resets around", archive)
        self.assertNotIn(FIRST_BOOKING_KEY, json.dumps(result))

    def test_local_key_rotation_all_keys_dead(self):
        self.write_env(f"BOOKING_RAPIDAPI_KEYS={FIRST_BOOKING_KEY},{SECOND_BOOKING_KEY}\n")
        self.quota_on(FIRST_BOOKING_KEY, SECOND_BOOKING_KEY)
        with mock.patch.object(tm, "LOCAL_KEY_ROTATION", True):
            result = self.run_engine()
        self.assertEqual(result["travel"]["hotels"]["reason_code"], "rate_limited")
        self.assertEqual(self.read_env(), "BOOKING_RAPIDAPI_KEYS=\n")
        archive = self.read_env(tm.EXHAUSTED_KEYS_FILE)
        self.assertIn(FIRST_BOOKING_KEY, archive)
        self.assertIn(SECOND_BOOKING_KEY, archive)
        self.assertEqual(result["status"], "success")  # The itinerary is still generated

    def test_local_key_rotation_ignores_transient_errors(self):
        self.write_env(f"BOOKING_RAPIDAPI_KEYS={FIRST_BOOKING_KEY},{SECOND_BOOKING_KEY}\n")
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(500, {"message": "down"})
        with mock.patch.object(tm, "LOCAL_KEY_ROTATION", True):
            result = self.run_engine()
        self.assertEqual(result["travel"]["hotels"]["reason_code"], "provider_error")
        self.assertEqual({c["key"] for c in self.router.calls_for("hotels")}, {FIRST_BOOKING_KEY})
        self.assertFalse(os.path.exists(tm.EXHAUSTED_KEYS_FILE))

    def test_pruning_disabled_by_default(self):
        original = f"BOOKING_RAPIDAPI_KEYS={FIRST_BOOKING_KEY},{SECOND_BOOKING_KEY}\n"
        self.write_env(original)
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(429, {"message": "You have exceeded the MONTHLY quota"})
        self.run_engine()
        self.assertEqual(self.read_env(), original)
        self.assertFalse(os.path.exists(tm.ENV_FILE + ".bak"))

# ==========================================
# 7. SECURITY, ERROR SAFETY & CACHE
# ==========================================
class TestSecurityAndCache(AdapterTestCase):
    def test_credentials_are_redacted_from_logs(self):
        stream = []
        handler = logging.Handler()
        handler.emit = lambda record: stream.append(record.getMessage())
        tm.logger.addHandler(handler)
        try:
            tm.logger.warning(f"key {FIRST_BOOKING_KEY} and gsk_ABCDEFGHIJKLMNOPQRSTUVWX and x-rapidapi-key: abcdef1234567890")
        finally:
            tm.logger.removeHandler(handler)
        for secret in (FIRST_BOOKING_KEY, "gsk_ABCDEFGHIJKLMNOPQRSTUVWX", "abcdef1234567890"):
            self.assertNotIn(secret, stream[0])

    def test_internal_exception_text_is_never_returned(self):
        with mock.patch.object(tm, "_search_travel_validated", side_effect=RuntimeError("boom gsk_SECRETSECRETSECRETSECRET")):
            result = self.run_engine()
        self.assertEqual(result["error"], {"code": "internal_error", "message": tm.ERROR_MESSAGES["internal_error"]})
        self.assertNotIn("boom", json.dumps(result))
        self.assertNotIn("SECRET", json.dumps(result))

    def test_response_never_contains_keys(self):
        with self.indicative_flights():
            dump = json.dumps(self.run_engine())
        for key in ("fakeskykey0001aaaa", FIRST_BOOKING_KEY, FAKE_ENV["GROQ_API_KEY"]):
            self.assertNotIn(key, dump)

    def test_cache_hit_uses_no_provider_call(self):
        tm.run_travelmate_engine(dict(BASE_REQUEST))
        first_calls = len(self.router.calls)
        result = tm.run_travelmate_engine(dict(BASE_REQUEST))
        self.assertEqual(len(self.router.calls), first_calls)
        self.assertEqual(result["travel"]["data_mode"], "includes_cached")

    def test_save_report_false_still_writes_cache(self):
        tm.run_travelmate_engine(dict(BASE_REQUEST), save_report=False)
        self.assertTrue(os.path.exists(tm.CACHE_FILE))
        self.assertFalse(os.path.exists(tm.REPORT_FILE))

    def test_concurrent_cache_writes_keep_valid_file(self):
        errors = []

        def writer(index):
            try:
                tm.cache_put(f"key-{index}", "test", {"value": index})
            except Exception as e:  # pragma: no cover - reported below
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertFalse(errors)
        with open(tm.CACHE_FILE, "r", encoding="utf-8") as f:
            self.assertEqual({f"key-{i}" for i in range(20)}, set(json.load(f)))

    def test_expired_cache_is_never_served(self):
        tm.run_travelmate_engine(dict(BASE_REQUEST))
        with open(tm.CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        for entry in cache.values():
            entry["saved_at"] = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        tm.atomic_write_json(tm.CACHE_FILE, cache)
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(429, {"message": "Too many requests"})
        result = tm.run_travelmate_engine(dict(BASE_REQUEST))
        self.assertEqual(result["travel"]["hotels"]["reason_code"], "rate_limited")

# ==========================================
# LIVE EVIDENCE CHAIN (REAL PROVIDERS, ONE RUN)
# ==========================================
def write_live_evidence():
    """
    Runs ONE real request (cache refresh, so data is fetched live) and writes the traceable chain:
    inputs -> raw provider data -> normalized context -> AI input -> AI raw output -> validated output -> final response,
    plus the BE-04 calculate_budget result computed from the same run when the backend is available.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    start = datetime.now(timezone.utc).date() + timedelta(days=30)
    request_data = {"departure_city": "Istanbul", "destination_city": "Cairo", "start_date": start.isoformat(),
                    "return_date": (start + timedelta(days=3)).isoformat(), "adults": 2, "budget_usd": 1500}
    request_id = tm.new_request_id()
    evidence = {}
    # Contract default budget (60 s); the evidence records how long the user actually waited
    deadline = datetime.now(timezone.utc) + timedelta(seconds=tm.DEFAULT_DEADLINE_SECONDS)
    started = time.monotonic()
    result = tm.run_travelmate_engine(request_data, deadline_at=deadline, request_id=request_id,
                                      cache_mode="refresh", evidence=evidence)
    total_seconds = round(time.monotonic() - started, 1)

    be04 = {"available": BE04_AVAILABLE, "report_slice_valid": None, "budget_output": None, "error": None}
    if BE04_AVAILABLE and result["be04_budget_input"]:
        try:
            ZiyadReportSlice.model_validate(result["report_slice"])
            be04["report_slice_valid"] = True
            be04["budget_output"] = json.loads(calculate_budget(
                BudgetInput.model_validate(result["be04_budget_input"])).model_dump_json())
        except Exception as e:  # Recorded as evidence of incompatibility
            be04["error"] = f"{type(e).__name__}: {str(e)[:500]}"

    public_offers = (result["travel"] or {}).get("hotels", {}).get("public_offers", [])
    flights = (result["travel"] or {}).get("flights") or {}
    legs = [l for l in (flights.get("selected_outbound_flight"), flights.get("selected_return_flight")) if l]
    legs += [l for group in (flights.get("alternative_date_offers") or {}).values() for l in group]
    chain_checks = {
        "total_response_seconds": total_seconds,
        "deadline_seconds": tm.DEFAULT_DEADLINE_SECONDS,
        "final_status": result["status"],
        "final_error_code": (result["error"] or {}).get("code"),
        "live_integration_status": result["live_integration_status"],
        "flight_mode": tm.FLIGHT_MODE,
        "flights_status": flights.get("status"),
        "flights_reason_code": flights.get("reason_code"),
        "flight_date_flags_consistent": all(l["date_matches_request"] == (l["flight_date"] == l["requested_date"])
                                            for l in legs) if legs else None,
        "live_round_trip_offers": len(flights.get("round_trip_offers") or []),
        "selected_leg_totals_usd": [l["total_price_usd"] for l in (flights.get("selected_outbound_flight"),
                                                                    flights.get("selected_return_flight")) if l],
        "leg_date_flags_consistent": all(l["date_matches_request"] == (l["flight_date"] == l["requested_date"])
                                         for l in (flights.get("selected_outbound_flight"),
                                                   flights.get("selected_return_flight")) if l)
        if flights.get("selected_outbound_flight") else None,
        "live_offers_match_local_dates": all(
            tm.utc_to_local_date(o["outbound_departure_at"], o["departure_airport_code"]) == request_data["start_date"]
            and tm.utc_to_local_date(o["return_departure_at"], o["arrival_airport_code"]) == request_data["return_date"]
            for o in flights["round_trip_offers"]) if flights.get("round_trip_offers") else None,
        "live_offers_match_adults": all(o["adults"] == request_data["adults"] for o in flights["round_trip_offers"])
        if flights.get("round_trip_offers") else None,
        "selected_flight_offer_id": (result["selected_offers"] or {}).get("selected_flight_offer_id"),
        "selected_flight_total_usd": ((flights.get("selected_offer") or {}).get("price") or {}).get("amount_usd"),
        "hotel_offers_count": len(public_offers),
        # None = nothing to check (no offers), never a vacuous True
        "hotel_offers_match_dates": all(o["check_in"] == request_data["start_date"] and
                                        o["check_out"] == request_data["return_date"] for o in public_offers) if public_offers else None,
        "hotel_offers_match_adults": all(o["occupancy_adults"] == request_data["adults"] for o in public_offers) if public_offers else None,
        "hotel_room_qty_values": sorted({o["room_qty"] for o in public_offers}, key=str),
        "selected_hotel_offer_id": (result["selected_offers"] or {}).get("selected_hotel_offer_id"),
        "ai_status": (result["ai_itinerary"] or {}).get("status"),
        "ai_latency_ms": ((result["ai_itinerary"] or {}).get("provenance") or {}).get("latency_ms"),
        "ai_itinerary_dates": [d["date"] for d in ((result["ai_itinerary"] or {}).get("itinerary") or [])],
        "be04": {k: v for k, v in be04.items() if k != "budget_output"} | {
            "status": (be04["budget_output"] or {}).get("status"),
            "selected_hotel_offer_id": (be04["budget_output"] or {}).get("selected_hotel_offer_id"),
            "selected_flight_offer_id": (be04["budget_output"] or {}).get("selected_flight_offer_id"),
            "provider_subtotal_usd": (be04["budget_output"] or {}).get("provider_subtotal_usd")},
        "provider_calls": [{"service": c["service"], "cache_status": c["provenance"]["cache_status"],
                            "http_status": c["provenance"].get("http_status"), "attempts": c["provenance"].get("attempts"),
                            "retrieved_at": c["provenance"]["retrieved_at"], "rate_limit": c["provenance"].get("rate_limit")}
                           for c in evidence.get("provider_calls", [])]
    }

    folder = os.path.join(BASE_DIR, "evidence", request_id)
    files = {
        "01_inputs.json": evidence.get("inputs"),
        "02_raw_provider_data.json": evidence.get("provider_calls"),
        "03_normalized_context.json": evidence.get("normalized_context"),
        "04_ai_input.json": evidence.get("ai_input"),
        "05_ai_raw_output.json": {"content": evidence.get("ai_raw_output")},
        "06_validated_ai_output.json": evidence.get("ai_validated_output"),
        "07_final_response.json": result,
        "08_be04_budget_output.json": be04
    }
    os.makedirs(folder, exist_ok=True)
    manifest = {"request_id": request_id, "generated_at": tm.utc_now_iso(), "adapter_schema": "v2 (BE-04 report slice)",
                "chain_checks": chain_checks, "files": {}}
    for name, content in files.items():
        tm.atomic_write_json(os.path.join(folder, name), tm.sanitize(content))
        with open(os.path.join(folder, name), "rb") as f:
            manifest["files"][name] = hashlib.sha256(f.read()).hexdigest()
    tm.atomic_write_json(os.path.join(folder, "manifest.json"), manifest)

    # Fail loudly if any credential leaked into the evidence
    secrets = tm._configured_secrets()
    for name in os.listdir(folder):
        with open(os.path.join(folder, name), "r", encoding="utf-8") as f:
            text = f.read()
        if [s for s in secrets if s in text] or [p.pattern for p in tm.SECRET_PATTERNS if p.search(text)]:
            raise SystemExit(f"[-] Credential pattern found in {name}. Evidence NOT valid.")

    print(f"\n[+] Evidence chain written to: {folder}")
    print(json.dumps(chain_checks, indent=4))
    return result

if __name__ == "__main__":
    if "--live-evidence" in sys.argv:
        write_live_evidence()
    else:
        unittest.main(verbosity=2)
