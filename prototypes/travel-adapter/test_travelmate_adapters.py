"""
TravelMate adapter tests and live evidence generator.

  python test_travelmate_adapters.py                 -> offline unit tests (no network, no API quota)
  python test_travelmate_adapters.py --live-evidence -> ONE real run that writes a sanitized evidence chain to
                                                        evidence/<request_id>/ (uses real keys from .env)

Offline tests use recorded real provider responses from tests/fixtures/ (recorded 2026-10-17) plus explicitly
SIMULATED failures (HTTP errors, malformed AI output, exchange rates). Simulated data is labeled in each test.
"""
import os
import sys
import json
import copy
import math
import time
import hashlib
import logging
import tempfile
import threading
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(BASE_DIR, "tests", "fixtures")
sys.path.insert(0, BASE_DIR)

import httpx
import groq
import travalmate as tm

FAKE_ENV = {
    "SKYSCANNER_RAPIDAPI_KEYS": "fakeskykey0001aaaa,fakeskykey0002bbbb",
    "BOOKING_RAPIDAPI_KEYS": "fakebookkey001cccc,fakebookkey002dddd",
    "GROQ_API_KEY": "gsk_FAKEFAKEFAKEFAKEFAKEFAKE00",
    "TRAVELMATE_APPROVED_POLICY_IDS": "policy-test-v1"
}
FROZEN_TODAY = date(2026, 10, 20)  # Fixtures were recorded for a 2026-11-01 -> 2026-11-05 stay

BASE_REQUEST = {
    "trip_type": "round_trip",
    "origin": "IST",
    "destination_city": "Cairo",
    "check_in_date": "2026-11-01",
    "check_out_date": "2026-11-05",
    "adults": 2,
    "budget_usd": 2000,
    "rooms": 2
}

def load_fixture(name):
    with open(os.path.join(FIXTURES_DIR, f"{name}.json"), "r", encoding="utf-8") as f:
        return json.load(f)

def simulated_fx_payload():
    """SIMULATED exchange-rate response (fixed GBP rate) so offline tests are deterministic."""
    return {"result": "success", "time_last_update_unix": time.time() - 3600,
            "time_last_update_utc": "SIMULATED", "rates": {"USD": 1, "GBP": 0.75, "EUR": 0.9}}

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
        self.overrides = {}  # service -> callable(params, headers) returning FakeResponse
        self.calls = []

    def __call__(self, url, headers=None, params=None, timeout=None):
        service = ("fx" if "open.er-api.com" in url else "flights" if "/skyscanner/route" in url
                   else "hotels" if "searchHotels" in url else "destination")
        self.calls.append({"service": service, "key": (headers or {}).get("x-rapidapi-key"), "params": params})
        if service in self.overrides:
            return self.overrides[service](params, headers)
        if service == "fx":
            return FakeResponse(200, self.fx)
        if service == "flights":
            return FakeResponse(200, self.flights[params["origin"]], {"x-ratelimit-requests-remaining": "99"})
        if service == "hotels":
            return FakeResponse(200, self.hotels[params["room_qty"]], {"x-ratelimit-requests-remaining": "99"})
        return FakeResponse(200, {"status": True, "data": []})

def valid_ai_output(days=None, explanation="Flight prices are indicative cached quotes."):
    dates = days or ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"]
    itinerary = []
    for i, d in enumerate(dates):
        day_type = "arrival" if i == 0 else ("departure" if i == len(dates) - 1 else "full_day")
        activities = [] if day_type != "full_day" else [{
            "time_of_day": "morning", "title": "Giza Pyramids", "description": "Guided visit.",
            "location": "Giza", "cost_status": "estimate", "estimated_cost_usd_per_person": 20}]
        itinerary.append({"date": d, "day_type": day_type, "activities": activities,
                          "empty_day_reason": "Travel and hotel check-in/out." if not activities else None})
    return {"itinerary": itinerary, "price_explanation": explanation}

class FakeGroqClient:
    """SIMULATED Groq client. Records every call so tests can prove there is no automatic retry."""
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.calls = 0
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
            mock.patch.object(tm, "_today", lambda: FROZEN_TODAY),
            mock.patch.object(tm, "_sleep", mock.Mock()),
            mock.patch.object(tm, "KEY_ROTATION_ON_QUOTA", False),
            mock.patch.object(tm, "ALLOW_STALE_CACHE_FALLBACK", False),
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

    def run_engine(self, **overrides):
        return tm.run_travelmate_engine(dict(BASE_REQUEST, **overrides), cache_mode="off")

# ==========================================
# 1. INVALID INPUT (validated BEFORE any external call)
# ==========================================
class TestInvalidInput(AdapterTestCase):
    def assert_invalid(self, field, **overrides):
        result = self.run_engine(**overrides)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "invalid_input")
        self.assertIn(field, [f["field"] for f in result["error"]["details"]["fields"]])
        self.assertEqual(self.requests_get.call_count, 0, "No provider call may happen for invalid input")

    def test_past_check_in_date(self):
        self.assert_invalid("check_in_date", check_in_date="2026-10-19")

    def test_check_out_not_after_check_in(self):
        self.assert_invalid("check_out_date", check_out_date="2026-11-01")

    def test_wrong_date_format(self):
        self.assert_invalid("check_in_date", check_in_date="01/11/2026")

    def test_airport_code_must_be_exactly_three_letters(self):
        self.assert_invalid("origin", origin="ISTA")
        self.assert_invalid("origin", origin="I5T")

    def test_city_must_be_text(self):
        self.assert_invalid("destination_city", destination_city="12345")
        self.assert_invalid("destination_city", destination_city=None)

    def test_budget_must_stay_positive_after_rounding(self):
        self.assert_invalid("budget_usd", budget_usd=0.004)
        self.assert_invalid("budget_usd", budget_usd=float("nan"))
        self.assert_invalid("budget_usd", budget_usd=float("inf"))
        self.assert_invalid("budget_usd", budget_usd=-10)

    def test_adults_must_be_positive_integer(self):
        self.assert_invalid("adults", adults=True)
        self.assert_invalid("adults", adults=0)
        self.assert_invalid("adults", adults=1.5)

    def test_rooms_cannot_exceed_adults(self):
        self.assert_invalid("rooms", rooms=3)

    def test_destination_airport_must_belong_to_city(self):
        self.assert_invalid("destination_airport", destination_airport="DXB")

    def test_origin_cannot_equal_destination(self):
        self.assert_invalid("origin", origin="CAI")

    def test_unsupported_city_is_not_invalid_input(self):
        result = self.run_engine(destination_city="Atlantis")
        self.assertEqual(result["error"]["code"], "unsupported_search")
        self.assertEqual(self.requests_get.call_count, 0)

    def test_public_parameters_do_not_expose_adapter_fields(self):
        result = self.run_engine()
        self.assertNotIn("rooms", result["search_parameters"])
        self.assertNotIn("destination_airport", result["search_parameters"])
        self.assertNotIn("adapter", result["search_parameters"])

# ==========================================
# 2. PROVIDER FAILURES & KEY HANDLING (SIMULATED HTTP errors)
# ==========================================
class TestProviderFailures(AdapterTestCase):
    def test_provider_failure_on_http_500(self):
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(500, {"message": "Internal error"})
        result = self.run_engine()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "provider_failure")
        self.assertEqual(result["error"]["category"], "hotels")
        hotel_calls = [c for c in self.router.calls if c["service"] == "hotels"]
        # 1 retry per key for transient failures, and a 500 is NOT a reason to switch keys
        self.assertEqual(len(hotel_calls), 2)
        self.assertEqual({c["key"] for c in hotel_calls}, {"fakebookkey001cccc"})
        self.assertEqual(result["ai_itinerary"]["status"], "not_run")

    def test_rate_limited_does_not_rotate_keys_by_default(self):
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(
            429, {"message": "You have exceeded the MONTHLY quota for Requests on your current plan"})
        result = self.run_engine()
        self.assertEqual(result["error"]["code"], "rate_limited")
        hotel_keys = [c["key"] for c in self.router.calls if c["service"] == "hotels"]
        self.assertEqual(hotel_keys, ["fakebookkey001cccc"])

    def test_quota_rotation_only_when_explicitly_enabled(self):
        def quota_on_first_key(params, headers):
            if headers["x-rapidapi-key"] == "fakebookkey001cccc":
                return FakeResponse(429, {"message": "You have exceeded the MONTHLY quota for Requests"})
            return FakeResponse(200, self.router.hotels[params["room_qty"]])
        self.router.overrides["hotels"] = quota_on_first_key
        with mock.patch.object(tm, "KEY_ROTATION_ON_QUOTA", True):
            result = self.run_engine()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["provenance"]["hotels"]["key_slot"], 2)

    def test_retry_after_is_honored_once_within_deadline(self):
        responses = [FakeResponse(429, {"message": "Too many requests"}, {"Retry-After": "2"})]
        def burst_limit(params, headers):
            return responses.pop(0) if responses else FakeResponse(200, self.router.hotels[params["room_qty"]])
        self.router.overrides["hotels"] = burst_limit
        result = self.run_engine()
        self.assertEqual(result["status"], "success")
        tm._sleep.assert_any_call(2.0)

    def test_auth_error_fails_over_to_next_configured_key(self):
        def first_key_unsubscribed(params, headers):
            if headers["x-rapidapi-key"] == "fakebookkey001cccc":
                return FakeResponse(403, {"message": "You are not subscribed to this API."})
            return FakeResponse(200, self.router.hotels[params["room_qty"]])
        self.router.overrides["hotels"] = first_key_unsubscribed
        result = self.run_engine()
        self.assertEqual(result["status"], "success")

    def test_auth_error_when_all_keys_rejected(self):
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(403, {"message": "You are not subscribed to this API."})
        result = self.run_engine()
        self.assertEqual(result["error"]["code"], "auth_error")

    def test_invalid_response_for_non_json_body(self):
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(200, None, text="<html>")
        result = self.run_engine()
        self.assertEqual(result["error"]["code"], "invalid_response")

    def test_hidden_error_inside_200_response(self):
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(200, {"status": False, "message": "Something went wrong"})
        result = self.run_engine()
        self.assertEqual(result["error"]["code"], "provider_failure")

    def test_timeout_when_deadline_already_passed(self):
        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        result = tm.run_travelmate_engine(dict(BASE_REQUEST), deadline_at=past, cache_mode="off")
        self.assertEqual(result["error"]["code"], "timeout")
        self.assertFalse([c for c in self.router.calls if c["service"] == "hotels"])

    def test_missing_credentials(self):
        with mock.patch.dict(os.environ, {"BOOKING_RAPIDAPI_KEYS": "", "BOOKING_RAPIDAPI_KEY_1": ""}):
            result = self.run_engine()
        self.assertEqual(result["error"]["code"], "auth_error")
        self.assertEqual(result["error"]["details"]["reason"], "missing_credentials")

    def test_flight_failure_does_not_fail_mandatory_hotel_category(self):
        self.router.overrides["flights"] = lambda p, h: FakeResponse(502, {"message": "Bad gateway"})
        result = self.run_engine()
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["travel_availability"]["flights"]["status"], "error")
        self.assertEqual(result["travel_availability"]["flights"]["error"]["code"], "provider_failure")

# ==========================================
# 3. NO RESULTS & OFFER ELIGIBILITY
# ==========================================
class TestNoResultsAndEligibility(AdapterTestCase):
    def test_no_results_when_provider_returns_no_hotels(self):
        empty = copy.deepcopy(self.router.hotels["2"])
        empty["data"]["hotels"] = []
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(200, empty)
        result = self.run_engine()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "no_results")
        self.assertEqual(result["hotels_data"], [])

    def test_alternative_date_flights_are_separate_and_never_budgeted(self):
        result = self.run_engine()
        flights = result["flights_data"]
        self.assertEqual(flights["outbound_flights"], [])  # Recorded data has no quote on 2026-11-01
        self.assertTrue(flights["alternative_date_flights"]["outbound"])
        for offer in flights["alternative_date_flights"]["outbound"]:
            self.assertFalse(offer["eligibility"]["eligible"])
            self.assertNotEqual(offer["flight_date"], "2026-11-01")
        self.assertEqual(result["travel_availability"]["flights"]["status"], "no_results")
        self.assertEqual(result["budget_summary"]["basis"], "hotel_only_flight_price_unavailable")
        for tier in result["budget_tiers_within_limit"]:
            self.assertIsNone(tier["flight_hotel_subtotal_usd"])
            self.assertIsNone(tier["outbound_flight_offer_id"])
        self.assertIsNone(result["selected_offers"]["outbound_flight"])

    def test_exact_date_flight_is_eligible_indicative_and_converted_with_provenance(self):
        flights = copy.deepcopy(self.router.flights["ist"])
        flights["data"]["deals"][0]["legs"][0]["date"] = "2026-11-01"  # SIMULATED exact-date quote
        self.router.overrides["flights"] = lambda p, h: FakeResponse(200, flights if p["origin"] == "ist" else self.router.flights["cai"])
        result = self.run_engine(trip_type="one_way")
        offer = result["flights_data"]["outbound_flights"][0]
        self.assertTrue(offer["eligibility"]["eligible"])
        self.assertEqual(offer["price_authority"], "indicative")
        self.assertFalse(offer["group_price_verified"])
        conversion = offer["provenance"]["currency_conversion"]
        self.assertEqual(conversion["status"], "converted")
        self.assertEqual(conversion["original_currency"], "GBP")
        self.assertEqual(offer["price_per_adult_usd"], tm.round_money(flights["data"]["deals"][0]["price"] / 0.75))
        self.assertEqual(offer["group_total_usd"], tm.round_money(offer["price_per_adult_usd"] * 2))
        self.assertEqual(result["budget_summary"]["basis"], "flight_plus_hotel")
        tier = result["budget_tiers_within_limit"][0]
        self.assertEqual(tier["flight_hotel_subtotal_usd"],
                         tm.round_money(tier["flight_subtotal_usd"] + tier["hotel_total_usd"]))
        self.assertTrue(tier["subtotal_is_indicative"])
        self.assertLessEqual(tier["flight_hotel_subtotal_usd"], 2000)

    def test_hotel_occupancy_mismatch_is_excluded(self):
        # Requesting 1 room while the provider answers for 2 rooms must exclude every offer
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(200, self.router.hotels["2"])
        result = self.run_engine(rooms=1)
        self.assertEqual(result["error"]["code"], "no_results")
        self.assertGreater(result["hotels_coverage"]["excluded"]["occupancy_mismatch"], 0)

    def test_hotel_adult_count_mismatch_is_excluded(self):
        result = self.run_engine(adults=3, rooms=2)
        self.assertEqual(result["error"]["code"], "no_results")

    def test_hotel_date_mismatch_is_excluded(self):
        result = self.run_engine(check_out_date="2026-11-06")
        self.assertEqual(result["error"]["code"], "no_results")
        self.assertGreater(result["hotels_coverage"]["excluded"]["date_mismatch"], 0)

    def test_hotel_far_from_city_is_excluded(self):
        far = copy.deepcopy(self.router.hotels["2"])
        far["data"]["hotels"][0]["property"]["latitude"] = 21.4  # SIMULATED: moved to Jeddah
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(200, far)
        result = self.run_engine()
        self.assertEqual(result["hotels_coverage"]["excluded"]["destination_mismatch"], 1)

    def test_unverified_occupancy_is_excluded(self):
        unverified = copy.deepcopy(self.router.hotels["2"])
        unverified["data"]["hotels"][0]["accessibilityLabel"] = "Some hotel. 900 USD."
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(200, unverified)
        result = self.run_engine()
        self.assertEqual(result["hotels_coverage"]["excluded"]["occupancy_unverified"], 1)

# ==========================================
# 4. PRICE SAFETY, TAXES & CURRENCY POLICY
# ==========================================
class TestPriceSafety(AdapterTestCase):
    def test_negative_nan_and_infinity_prices_are_rejected(self):
        bad = copy.deepcopy(self.router.hotels["2"])
        bad["data"]["hotels"][0]["property"]["priceBreakdown"]["grossPrice"]["value"] = -50
        bad["data"]["hotels"][1]["property"]["priceBreakdown"]["grossPrice"]["value"] = float("nan")
        bad["data"]["hotels"][2]["property"]["priceBreakdown"]["grossPrice"]["value"] = float("inf")
        bad["data"]["hotels"][3]["property"]["priceBreakdown"]["excludedPrice"]["value"] = -1
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(200, bad)
        result = self.run_engine()
        self.assertEqual(result["hotels_coverage"]["excluded"]["invalid_price"], 4)
        for hotel in result["hotels_data"]:
            for key in ["base_price_usd", "taxes_and_fees_usd", "total_price_usd"]:
                if hotel[key] is not None:
                    self.assertTrue(math.isfinite(hotel[key]) and hotel[key] >= 0)

    def test_missing_taxes_stay_unknown_never_zero(self):
        missing = copy.deepcopy(self.router.hotels["2"])
        del missing["data"]["hotels"][0]["property"]["priceBreakdown"]["excludedPrice"]
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(200, missing)
        result = self.run_engine()
        hotel_id = missing["data"]["hotels"][0]["hotel_id"]
        hotel = next(h for h in result["hotels_data"] if h["hotel_id"] == hotel_id)
        self.assertEqual(hotel["taxes_status"], "unknown")
        self.assertIsNone(hotel["taxes_and_fees_usd"])
        self.assertIsNone(hotel["total_price_usd"])
        self.assertIsNone(hotel["fits_budget"])
        self.assertNotIn(hotel["offer_id"], [t["hotel_offer_id"] for t in result["budget_tiers_within_limit"]])

    def test_known_taxes_are_added_exactly_once(self):
        result = self.run_engine()
        for hotel in result["hotels_data"]:
            self.assertEqual(hotel["total_price_usd"], tm.round_money(hotel["base_price_usd"] + hotel["taxes_and_fees_usd"]))

    def test_unconvertible_flight_currency_is_excluded_with_warning(self):
        self.router.overrides["fx"] = lambda p, h: FakeResponse(503, None, text="down")  # SIMULATED outage
        result = self.run_engine()
        coverage = result["flights_data"]["coverage"]["outbound"]
        self.assertEqual(coverage["excluded"]["unconvertible_currency"], coverage["deals_returned"])
        self.assertEqual(result["flights_data"]["alternative_date_flights"]["outbound"], [])
        self.assertTrue(any("could not be converted" in w for w in result["warnings"]))

    def test_stale_exchange_rates_are_not_used(self):
        self.router.fx["time_last_update_unix"] = time.time() - 72 * 3600  # SIMULATED 3-day-old rates
        result = self.run_engine()
        self.assertEqual(result["provenance"]["exchange_rates"]["reason"], "rates_too_old")

    def test_flight_coverage_documents_ignored_parameters(self):
        coverage = self.run_engine()["flights_data"]["coverage"]["outbound"]
        self.assertFalse(coverage["date_parameter_honored"])
        self.assertFalse(coverage["currency_parameter_honored"])
        self.assertEqual(coverage["returned_currency"], "GBP")

# ==========================================
# 5. AI OUTPUT VALIDATION (SIMULATED AI responses)
# ==========================================
class TestAIOutput(AdapterTestCase):
    def ai_result(self, content=None, error=None, **engine_kwargs):
        self.groq_client.content = content
        self.groq_client.error = error
        return tm.run_travelmate_engine(dict(BASE_REQUEST), cache_mode="off", **engine_kwargs)

    def assert_invalid_output(self, result):
        self.assertEqual(result["status"], "success")  # Travel data is still valid
        self.assertEqual(result["ai_itinerary"]["status"], "error")
        self.assertEqual(result["ai_itinerary"]["error"]["code"], "invalid_output")
        self.assertIsNone(result["ai_itinerary"]["itinerary"])

    def test_valid_itinerary_is_published(self):
        result = self.ai_result(json.dumps(valid_ai_output()))
        itinerary = result["ai_itinerary"]["itinerary"]
        self.assertEqual(result["ai_itinerary"]["status"], "success")
        self.assertEqual([d["date"] for d in itinerary],
                         ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"])
        self.assertEqual(self.groq_client.last_kwargs["temperature"], 0.1)

    def test_malformed_json_fails_safely(self):
        self.assert_invalid_output(self.ai_result("Here is your trip: {not json"))

    def test_wrong_number_of_days_fails(self):
        self.assert_invalid_output(self.ai_result(json.dumps(valid_ai_output(days=["2026-11-01", "2026-11-02"]))))

    def test_wrong_date_order_fails(self):
        output = valid_ai_output()
        output["itinerary"][1]["date"], output["itinerary"][2]["date"] = "2026-11-03", "2026-11-02"
        self.assert_invalid_output(self.ai_result(json.dumps(output)))

    def test_empty_full_day_fails(self):
        output = valid_ai_output()
        output["itinerary"][2]["activities"] = []
        self.assert_invalid_output(self.ai_result(json.dumps(output)))

    def test_empty_travel_day_without_reason_fails(self):
        output = valid_ai_output()
        output["itinerary"][0]["empty_day_reason"] = None
        self.assert_invalid_output(self.ai_result(json.dumps(output)))

    def test_incomplete_activity_fails(self):
        output = valid_ai_output()
        output["itinerary"][1]["activities"][0] = {"title": "Museum", "cost_status": "estimate"}
        self.assert_invalid_output(self.ai_result(json.dumps(output)))

    def test_unknown_cost_with_number_fails(self):
        output = valid_ai_output()
        output["itinerary"][1]["activities"][0].update(cost_status="unknown", estimated_cost_usd_per_person=15)
        self.assert_invalid_output(self.ai_result(json.dumps(output)))

    def test_ai_is_never_retried_automatically(self):
        result = self.ai_result(error=groq_status_error(groq.InternalServerError, 500))
        self.assertEqual(self.groq_client.calls, 1)
        self.assertEqual(result["ai_itinerary"]["error"]["code"], "unavailable")
        self.assertEqual(result["ai_itinerary"]["provenance"]["automatic_retries"], 0)

    def test_ai_rate_limit_and_auth_mapping(self):
        result = self.ai_result(error=groq_status_error(groq.RateLimitError, 429))
        self.assertEqual(result["ai_itinerary"]["error"]["code"], "rate_limited")
        result = self.ai_result(error=groq_status_error(groq.AuthenticationError, 401))
        self.assertEqual(result["ai_itinerary"]["error"]["code"], "auth_error")

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
        self.assertEqual(result["ai_itinerary"]["status"], "success")
        self.assertEqual(result["ai_recommendation_report"], "")
        self.assertTrue(any("price explanation was dropped" in w for w in result["warnings"]))

    def test_food_and_transport_unknown_without_approved_policy(self):
        result = self.ai_result(json.dumps(valid_ai_output()),
                                estimation_policy={"policy_id": "not-reviewed", "food_usd_per_person_per_day": 30})
        estimates = result["ai_itinerary"]["ancillary_estimates"]
        self.assertEqual(estimates["food"]["status"], "unknown")
        self.assertEqual(estimates["local_transport"]["status"], "unknown")
        self.assertEqual(estimates["activities"]["status"], "estimate")

    def test_food_estimate_with_approved_policy(self):
        result = self.ai_result(json.dumps(valid_ai_output()),
                                estimation_policy={"policy_id": "policy-test-v1", "food_usd_per_person_per_day": 30})
        food = result["ai_itinerary"]["ancillary_estimates"]["food"]
        self.assertEqual(food["status"], "estimate")
        self.assertEqual(food["amount_usd"], 30 * 2 * 5)
        self.assertEqual(food["policy_id"], "policy-test-v1")
        self.assertEqual(result["ai_itinerary"]["ancillary_estimates"]["local_transport"]["status"], "unknown")

    def test_ineligible_selected_offers_are_not_sent_to_ai(self):
        result = self.run_engine()
        alternative = result["flights_data"]["alternative_date_flights"]["outbound"][0]
        ai = tm.generate_itinerary(dict(BASE_REQUEST), {"outbound_flight": alternative, "hotel": None}, {})
        self.assertEqual(ai["status"], "success")
        self.assertTrue(any("not an eligible" in w for w in ai["warnings"]))
        sent = self.groq_client.last_kwargs["messages"][1]["content"]
        self.assertNotIn(alternative["flight_date"] + '"', sent.split("RULES:")[0])

# ==========================================
# 6. SECURITY, ERROR SAFETY & CACHE
# ==========================================
class TestSecurityAndCache(AdapterTestCase):
    def test_credentials_are_redacted_from_logs(self):
        stream = []
        handler = logging.Handler()
        handler.emit = lambda record: stream.append(record.getMessage())
        tm.logger.addHandler(handler)
        try:
            tm.logger.warning("key fakebookkey001cccc and gsk_ABCDEFGHIJKLMNOPQRSTUVWX and x-rapidapi-key: abcdef1234567890")
        finally:
            tm.logger.removeHandler(handler)
        self.assertNotIn("fakebookkey001cccc", stream[0])
        self.assertNotIn("gsk_ABCDEFGHIJKLMNOPQRSTUVWX", stream[0])
        self.assertNotIn("abcdef1234567890", stream[0])

    def test_internal_exception_text_is_never_returned(self):
        with mock.patch.object(tm, "_search_travel_validated", side_effect=RuntimeError("boom gsk_SECRETSECRETSECRETSECRET")):
            result = self.run_engine()
        self.assertEqual(result["error"]["code"], "internal_error")
        self.assertNotIn("boom", json.dumps(result))
        self.assertNotIn("SECRET", json.dumps(result))

    def test_response_never_contains_keys(self):
        dump = json.dumps(self.run_engine())
        for key in ["fakeskykey0001aaaa", "fakebookkey001cccc", FAKE_ENV["GROQ_API_KEY"]]:
            self.assertNotIn(key, dump)

    def test_cache_hit_uses_no_provider_call(self):
        tm.run_travelmate_engine(dict(BASE_REQUEST))
        first_calls = len(self.router.calls)
        result = tm.run_travelmate_engine(dict(BASE_REQUEST))
        self.assertEqual(len(self.router.calls), first_calls)
        self.assertEqual(result["data_mode"], "includes_cached")

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
            cache = json.load(f)
        self.assertEqual({f"key-{i}" for i in range(20)}, set(cache))

    def test_stale_cache_fallback_is_labeled(self):
        tm.run_travelmate_engine(dict(BASE_REQUEST))
        with open(tm.CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        for entry in cache.values():
            entry["saved_at"] = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        tm.atomic_write_json(tm.CACHE_FILE, cache)
        self.router.overrides["hotels"] = lambda p, h: FakeResponse(429, {"message": "Too many requests"})
        with mock.patch.object(tm, "ALLOW_STALE_CACHE_FALLBACK", True):
            result = tm.run_travelmate_engine(dict(BASE_REQUEST))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["provenance"]["hotels"]["cache_status"], "stale_fallback")
        self.assertEqual(result["data_mode"], "stale_cache_fallback")

# ==========================================
# LIVE EVIDENCE CHAIN (REAL PROVIDERS, ONE RUN)
# ==========================================
def write_live_evidence():
    """
    Runs ONE real request (cache refresh, so data is fetched live) and writes the traceable chain:
    inputs -> raw provider data -> normalized context -> AI input -> AI raw output -> validated output -> final response.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    check_in = date.today() + timedelta(days=30)
    request_data = {
        "trip_type": "round_trip",
        "origin": "IST",
        "destination_city": "Cairo",
        "check_in_date": check_in.isoformat(),
        "check_out_date": (check_in + timedelta(days=3)).isoformat(),
        "adults": 2,
        "budget_usd": 1500,
        "rooms": 1
    }
    request_id = tm.new_request_id()
    evidence = {}
    deadline = datetime.now(timezone.utc) + timedelta(seconds=150)
    result = tm.run_travelmate_engine(request_data, deadline_at=deadline, request_id=request_id,
                                      cache_mode="refresh", evidence=evidence)

    folder = os.path.join(BASE_DIR, "evidence", request_id)
    files = {
        "01_inputs.json": evidence.get("inputs"),
        "02_raw_provider_data.json": evidence.get("provider_calls"),
        "03_normalized_context.json": evidence.get("normalized_context"),
        "04_ai_input.json": evidence.get("ai_input"),
        "05_ai_raw_output.json": {"content": evidence.get("ai_raw_output")},
        "06_validated_ai_output.json": evidence.get("ai_validated_output"),
        "07_final_response.json": result
    }
    hotels = result["hotels_data"]
    chain_checks = {
        "final_status": result["status"],
        "final_error_code": (result["error"] or {}).get("code"),
        # None = nothing to check (no offers), never a vacuous True
        "hotel_offers_match_dates": all(h["check_in_date"] == request_data["check_in_date"] and
                                        h["check_out_date"] == request_data["check_out_date"] for h in hotels) if hotels else None,
        "hotel_offers_match_adults_and_rooms": all(h["adults"] == 2 and h["rooms"] == 1 for h in hotels) if hotels else None,
        "hotel_offers_count": len(hotels),
        "flight_date_parameter_honored": result["flights_data"]["coverage"].get("outbound", {}).get("date_parameter_honored"),
        "eligible_exact_date_flights": len(result["flights_data"]["outbound_flights"]),
        "ai_itinerary_status": result["ai_itinerary"]["status"],
        "ai_itinerary_dates": [d["date"] for d in (result["ai_itinerary"]["itinerary"] or [])],
        "provider_calls": [{"service": c["service"], "cache_status": c["provenance"]["cache_status"],
                            "http_status": c["provenance"].get("http_status"),
                            "retrieved_at": c["provenance"]["retrieved_at"],
                            "rate_limit": c["provenance"].get("rate_limit")}
                           for c in evidence.get("provider_calls", [])]
    }

    os.makedirs(folder, exist_ok=True)
    manifest = {"request_id": request_id, "generated_at": tm.utc_now_iso(), "chain_checks": chain_checks, "files": {}}
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
        leaked = [s for s in secrets if s in text] or [p.pattern for p in tm.SECRET_PATTERNS if p.search(text)]
        if leaked:
            raise SystemExit(f"[-] Credential pattern found in {name}. Evidence NOT valid.")

    print(f"\n[+] Evidence chain written to: {folder}")
    print(json.dumps(chain_checks, indent=4))
    return result

if __name__ == "__main__":
    if "--live-evidence" in sys.argv:
        write_live_evidence()
    else:
        unittest.main(verbosity=2)
