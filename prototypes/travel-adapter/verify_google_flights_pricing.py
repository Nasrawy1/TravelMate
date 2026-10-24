"""
Google Flights price-meaning verification (PR #25 review, item 2).

Runs the SAME one-way searches with adults=1 and adults=2 for the outbound and the return direction, close in time,
then asks the provider booking-details endpoint for the cheapest flight of each search. Every request (without the
API key) and every raw response is saved to evidence/google-flights-price-verification-<timestamp>/, plus a
summary.json that compares the same flight numbers across the two traveler counts.

    python verify_google_flights_pricing.py IST CAI 2026-11-20 2026-11-23      (uses 6 requests of the monthly quota)
"""
import os
import sys
import json
import time
import hashlib
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import travalmate as tm

HOST = tm.GOOGLE_FLIGHTS_HOST

def call(path, params, key):
    started = time.monotonic()
    response = requests.get(f"https://{HOST}{path}", params=params, timeout=40,
                            headers={"x-rapidapi-host": HOST, "x-rapidapi-key": key})
    try:
        body = response.json()
    except ValueError:
        body = {"_non_json_body": response.text[:2000]}
    return {
        "request": {"method": "GET", "url": f"https://{HOST}{path}", "params": params,
                    "headers": {"x-rapidapi-host": HOST, "x-rapidapi-key": "<redacted>"}},
        "requested_at": tm.utc_now_iso(),
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "http_status": response.status_code,
        "rate_limit": {k: v for k, v in response.headers.items() if k.lower().startswith("x-ratelimit")},
        "response": body
    }

def options(record):
    itineraries = ((record["response"] or {}).get("data") or {}).get("itineraries") or {}
    return (itineraries.get("topFlights") or []) + (itineraries.get("otherFlights") or [])

def flight_key(option):
    return " + ".join(s.get("flight_number", "?") for s in option.get("flights") or [])

def main(origin, destination, outbound_date, return_date):
    keys = tm.load_key_pool("GOOGLE_FLIGHTS")
    if not keys:
        raise SystemExit("GOOGLE_FLIGHTS_RAPIDAPI_KEYS is not configured in .env")
    key = keys[0]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = os.path.join(tm.BASE_DIR, "evidence", f"google-flights-price-verification-{stamp}")
    os.makedirs(folder, exist_ok=True)

    legs = [("outbound", origin, destination, outbound_date), ("return", destination, origin, return_date)]
    records, summary = {}, {"generated_at": tm.utc_now_iso(), "legs": {}}
    for direction, dep, arr, day in legs:
        for adults in (1, 2):
            params = {"departure_id": dep, "arrival_id": arr, "outbound_date": day, "travel_class": "ECONOMY",
                      "adults": str(adults), "show_hidden": "1", "currency": "USD", "language_code": "en-US",
                      "country_code": "US", "search_type": "best"}
            name = f"{direction}_{dep}-{arr}_{day}_adults{adults}"
            records[name] = call("/api/v1/searchFlights", params, key)
            tm.atomic_write_json(os.path.join(folder, f"{name}.json"), tm.sanitize(records[name]))
            print(f"[+] {name}: HTTP {records[name]['http_status']} in {records[name]['elapsed_ms']} ms")

        one = {flight_key(o): o for o in options(records[f"{direction}_{dep}-{arr}_{day}_adults1"])}
        two = {flight_key(o): o for o in options(records[f"{direction}_{dep}-{arr}_{day}_adults2"])}
        common = sorted(set(one) & set(two), key=lambda k: two[k].get("price") or 0)
        rows = [{"flight": k, "departure": two[k].get("departure_time"), "price_adults1": one[k].get("price"),
                 "price_adults2": two[k].get("price"),
                 "ratio": round(two[k]["price"] / one[k]["price"], 3) if one[k].get("price") else None}
                for k in common]
        summary["legs"][direction] = {"route": f"{dep}->{arr}", "date": day, "common_flights": len(rows),
                                      "comparison": rows[:15]}

        # Provider booking details for the cheapest common flight (2 adults): partner prices for that exact itinerary
        if common:
            cheapest = two[common[0]]
            token = cheapest.get("booking_token")
            if token:
                name = f"{direction}_booking_details_{common[0].replace(' ', '')}_adults2"
                params = {"booking_token": token, "currency": "USD", "language_code": "en-US", "country_code": "US"}
                record = call("/api/v1/getBookingDetails", params, key)
                record["request"]["params"]["booking_token"] = f"<sha256:{hashlib.sha256(token.encode()).hexdigest()[:16]}>"
                tm.atomic_write_json(os.path.join(folder, f"{name}.json"), tm.sanitize(record))
                summary["legs"][direction]["booking_details_file"] = f"{name}.json"
                summary["legs"][direction]["booking_details_http"] = record["http_status"]
                print(f"[+] {name}: HTTP {record['http_status']} in {record['elapsed_ms']} ms")

    tm.atomic_write_json(os.path.join(folder, "summary.json"), summary)
    for name in os.listdir(folder):  # Never leave a credential in the evidence
        with open(os.path.join(folder, name), "r", encoding="utf-8") as f:
            text = f.read()
        if [s for s in tm._configured_secrets() if s in text] or [p for p in tm.SECRET_PATTERNS if p.search(text)]:
            raise SystemExit(f"[-] Credential pattern found in {name}. Evidence NOT valid.")
    print(f"\n[+] Saved to {folder}")
    print(json.dumps({d: {k: v for k, v in s.items() if k != "comparison"} | {"first_rows": s["comparison"][:5]}
                      for d, s in summary["legs"].items()}, indent=2))

if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
