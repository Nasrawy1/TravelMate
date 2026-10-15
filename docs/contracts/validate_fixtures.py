"""Validate TravelMate v0.4 synthetic fixtures; no network/provider calls."""
import copy
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "contracts/api-v0.4.schema.json").read_text())
MANIFEST = json.loads((ROOT / "fixtures/manifest.json").read_text())
TODAY = date.fromisoformat(MANIFEST["validation_today_utc"])

def require(condition, message):
    if not condition:
        raise ValueError(message)

def money(value):
    return Decimal(str(value))

def shape(name, value):
    Draft202012Validator(
        {"$ref": "#/$defs/" + name, "$defs": SCHEMA["$defs"]},
        format_checker=FormatChecker(),
    ).validate(value)

def request_check(r):
    shape("request", r)
    start, end = date.fromisoformat(r["start_date"]), date.fromisoformat(r["return_date"])
    require(start > TODAY, "start must be future under fixture clock")
    require(1 <= (end-start).days <= 7, "night range")
    require(r["departure_city"].strip().casefold() != r["destination_city"].strip().casefold(), "distinct cities")

def response_check(r, req):
    shape("response", r)
    request_check(req)
    trip, budget = r["trip"], r["budget"]
    for key in ("departure_city", "destination_city", "start_date", "return_date", "adults"):
        require(trip[key] == req[key], "trip/request mismatch")
    require(budget["budget_usd"] == req["budget_usd"], "budget/request mismatch")
    start, end = date.fromisoformat(trip["start_date"]), date.fromisoformat(trip["return_date"])
    nights = (end-start).days
    require(trip["nights"] == nights, "night count")
    expected_dates = [(start + timedelta(days=i)).isoformat() for i in range(nights+1)]
    require([d["date"] for d in r["itinerary"]] == expected_dates, "complete ordered dates")
    activities = {}
    for index, day in enumerate(r["itinerary"]):
        acts = day["activities"]
        if acts:
            require(day["empty_day_reason"] is None, "nonempty day reason")
        else:
            require(index in (0, nights) and bool(day["empty_day_reason"]), "empty day reason")
        require([a["order"] for a in acts] == list(range(1, len(acts)+1)), "activity order")
        for a in acts:
            c = a["cost"]
            require(c["kind"] in ("estimate", "unknown"), "AI provider activity forbidden")
            require((c["amount_usd"] is None and c["coverage"] is None) if c["kind"] == "unknown"
                    else (c["amount_usd"] is not None and c["coverage"] == "all_travelers"), "activity cost")
            activities[(day["date"], a["order"])] = c
    offers, selected = {}, {}
    for category, selection, ledger_category in (
        ("flights", "selected_flight_offer_id", "flights"),
        ("hotels", "selected_hotel_offer_id", "accommodation"),
    ):
        group = r["travel_options"][category]
        require(group["status"] == ("live" if group["offers"] else "unavailable"), "offer status")
        ids = []
        for offer in group["offers"]:
            oid = offer["id"]
            require(oid not in offers, "offer ID uniqueness")
            offers[oid] = offer
            ids.append(oid)
            price = offer["price"]
            require(price["kind"] == "provider" and price["amount_usd"] is not None and
                    price["coverage"] == "entire_trip_all_travelers", "offer price")
            tax = offer["taxes"]
            require((tax["additional_amount_usd"] == 0) if tax["status"] == "included" else
                    ((tax["additional_amount_usd"] is not None and tax["additional_amount_usd"] > 0)
                     if tax["status"] == "additional_known" else tax["additional_amount_usd"] is None), "tax semantics")
            if category == "hotels":
                require(offer["check_in"] == trip["start_date"] and offer["check_out"] == trip["return_date"]
                        and offer["occupancy_adults"] == trip["adults"], "hotel coverage")
            else:
                require(offer["adults"] == trip["adults"], "flight group coverage")
                # Airport local-date matching needs adapter provenance and actual timezone mapping.
        chosen = budget[selection]
        require((chosen in ids) if ids else chosen is None, "selected offer reference")
        if ids:
            known = [o for o in group["offers"] if o["taxes"]["status"] != "unknown"]
            pool = known or group["offers"]
            def total(o):
                return money(o["price"]["amount_usd"]) + money(o["taxes"]["additional_amount_usd"] or 0)
            best = min(pool, key=lambda o: (total(o), o["id"]))
            require(chosen == best["id"], "fee-aware selection")
        selected[ledger_category] = offers.get(chosen)
    require(r["live_integration_status"] == ("price_received" if offers else "no_price"), "live status")
    items = budget["cost_items"]
    require(len({i["id"] for i in items}) == len(items), "unique item IDs")
    for cat in ("flights", "accommodation", "food", "local_transport"):
        require(sum(i["category"] == cat for i in items) == 1, "one category base")
    refs = set()
    for item in items:
        cat, kind = item["category"], item["kind"]
        require((item["amount_usd"] is None) == (kind == "unknown"), "unknown amount")
        if item["amount_usd"] is not None:
            require(money(item["amount_usd"]) == money(item["amount_usd"]).quantize(Decimal(".01")), "cent precision")
        if cat == "activities":
            ref = item["activity_ref"]
            require(ref is not None, "activity ref required")
            key = (ref["date"], ref["order"])
            require(key in activities and key not in refs, "unique valid activity ref")
            refs.add(key)
            a = activities[key]
            require(item["amount_usd"] == a["amount_usd"] and kind == a["kind"], "activity ledger match")
        else:
            require(item["activity_ref"] is None, "nonactivity ref")
        if cat in selected:
            offer = selected[cat]
            require(kind == ("provider" if offer else "unknown"), "travel cost kind")
            require(item["source_offer_id"] == (offer["id"] if offer else None), "base offer link")
            require(item["amount_usd"] == (offer["price"]["amount_usd"] if offer else None), "base cost match")
        elif cat == "taxes_fees":
            require(item["source_offer_id"] in [o["id"] for o in selected.values() if o], "tax offer link")
        else:
            require(kind in ("estimate", "unknown") and item["source_offer_id"] is None, "estimate source")
    require(refs == set(activities), "activity ledger complete")
    expected_tax_ids = []
    for offer in selected.values():
        if not offer:
            continue
        tax_lines = [i for i in items if i["category"] == "taxes_fees" and i["source_offer_id"] == offer["id"]]
        t = offer["taxes"]
        require(len(tax_lines) == (0 if t["status"] == "included" else 1), "tax double counting")
        if tax_lines:
            expected_tax_ids.append(tax_lines[0]["id"])
            require(tax_lines[0]["amount_usd"] == t["additional_amount_usd"] and
                    tax_lines[0]["kind"] == ("unknown" if t["status"] == "unknown" else "provider"), "tax amount")
    require(len(expected_tax_ids) == sum(i["category"] == "taxes_fees" for i in items), "extra tax")
    missing = {i["category"] for i in items if i["kind"] == "unknown"}
    require(set(budget["missing_categories"]) == missing, "missing category set")
    p = sum((money(i["amount_usd"]) for i in items if i["kind"] == "provider"), Decimal(0))
    e = sum((money(i["amount_usd"]) for i in items if i["kind"] == "estimate"), Decimal(0))
    total = None if missing else p+e
    require(money(budget["provider_subtotal_usd"]) == p and money(budget["estimated_subtotal_usd"]) == e, "subtotals")
    require((budget["projected_total_usd"] is None) if total is None else
            (budget["projected_total_usd"] is not None and money(budget["projected_total_usd"]) == total), "total")
    limit = money(budget["budget_usd"])
    status = "over_budget" if p > limit or (total is not None and total > limit) else (
        "within_budget" if total is not None else "uncertain")
    require(budget["status"] == status, "budget status")

def main():
    Draft202012Validator.check_schema(SCHEMA)
    responses = {}
    for case in MANIFEST["cases"]:
        value = json.loads((ROOT / "fixtures" / case["file"]).read_text())
        if case["schema"] == "response":
            response_check(value, case["request"])
            responses[case["file"]] = (value, case["request"])
        elif case["schema"] == "request":
            request_check(value)
        else:
            shape("error", value)
            require(case["headers"]["X-Request-ID"] == value["request_id"], "request ID header")
            codes = {"UNAUTHORIZED":401,"VALIDATION_ERROR":422,"AI_GENERATION_FAILED":502,
                     "GENERATION_TIMEOUT":504,"RATE_LIMITED":429}
            require(case["http_status"] == codes[value["error"]["code"]], "error HTTP mapping")
    mutations = [
        ("partial-prices.json", lambda r: r["budget"].update(status="within_budget")),
        ("within-budget.json", lambda r: r["budget"].update(selected_hotel_offer_id="missing")),
        ("within-budget.json", lambda r: r["itinerary"].pop()),
        ("within-budget.json", lambda r: r["budget"]["cost_items"].append(copy.deepcopy(r["budget"]["cost_items"][-1]))),
        ("within-budget.json", lambda r: r["travel_options"]["hotels"]["offers"][0].update(occupancy_adults=1)),
        ("within-budget.json", lambda r: r["budget"].update(provider_subtotal_usd=900)),
        ("no-prices.json", lambda r: r.update(live_integration_status="price_received")),
        ("known-minimum-over-budget.json", lambda r: r["budget"].update(status="uncertain")),
    ]
    for filename, mutate in mutations:
        original, req = responses[filename]
        invalid = copy.deepcopy(original)
        mutate(invalid)
        try:
            response_check(invalid, req)
        except Exception as exc:
            # Validators raise ValidationError; semantic checks raise ValueError.
            from jsonschema.exceptions import ValidationError
            if not isinstance(exc, (ValueError, ValidationError)):
                raise
        else:
            raise AssertionError("Negative mutation was accepted: " + filename)
    print(f"PASS: {len(MANIFEST['cases'])} fixtures and {len(mutations)} rejected invalid mutations.")
    print("No live APIs tested; provider compatibility and team approval remain pending.")

if __name__ == "__main__":
    main()
