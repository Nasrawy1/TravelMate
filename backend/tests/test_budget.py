from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.budget import calculate_budget, select_offer
from app.services.models import (
    ActivityItem,
    ActivityRef,
    BudgetInput,
    FlightsData,
    HotelOffer,
    OfferCandidate,
    SelectedFlight,
)


def flight(**overrides) -> SelectedFlight:
    values = {
        "airline": "Turkish Airlines",
        "carrier_codes": ["TK"],
        "origin_airport": "IST",
        "destination_airport": "CAI",
        "flight_date": date(2026, 11, 4),
        "requested_date": date(2026, 11, 1),
        "date_matches_request": True,
        "days_from_requested_date": 3,
        "is_direct": False,
        "stops_label": "With stops (exact count not provided by API)",
        "price_per_person_usd": Decimal("117.20"),
        "travelers": 2,
        "total_price_usd": Decimal("234.40"),
        "quoted_at": datetime(2026, 10, 17, 10, 30, tzinfo=timezone.utc),
        "booking_link": "https://www.skyscanner.net/example",
    }
    values.update(overrides)
    return SelectedFlight(**values)


def return_flight(**overrides) -> SelectedFlight:
    values = {
        "airline": "Air Cairo",
        "carrier_codes": ["SM"],
        "origin_airport": "CAI",
        "destination_airport": "IST",
        "flight_date": date(2026, 11, 8),
        "requested_date": date(2026, 11, 5),
        "date_matches_request": True,
        "days_from_requested_date": 3,
        "is_direct": True,
        "stops_label": "Direct",
        "price_per_person_usd": Decimal("74.58"),
        "travelers": 2,
        "total_price_usd": Decimal("149.16"),
        "quoted_at": datetime(2026, 10, 11, 13, 11, tzinfo=timezone.utc),
        "booking_link": "https://www.skyscanner.net/example",
    }
    values.update(overrides)
    return SelectedFlight(**values)


def hotel(**overrides) -> HotelOffer:
    values = {
        "hotel_id": 9406148,
        "name": "Best Dreams Hotel",
        "star_rating": 3,
        "review_score": Decimal("7.2"),
        "nights": 4,
        "base_price_usd": Decimal("168.00"),
        "taxes_and_fees_usd": Decimal("25.20"),
        "total_price_usd": Decimal("193.20"),
        "price_per_night_usd": Decimal("48.30"),
        "fits_budget": True,
    }
    values.update(overrides)
    return HotelOffer(**values)


def budget_input(**overrides) -> BudgetInput:
    values = {
        "budget_usd": Decimal("1000.00"),
        "flights_data": FlightsData(
            selected_outbound_flight=flight(), selected_return_flight=return_flight()
        ),
        "selected_hotel": hotel(),
        "activities": [],
        "food": Decimal("0"),
        "local_transport": Decimal("0"),
    }
    values.update(overrides)
    return BudgetInput(**values)


def test_selected_normalized_flights_are_summed_once_and_id_is_synthetic() -> None:
    result = calculate_budget(budget_input())

    assert result.selected_flight_offer_id == (
        "Turkish Airlines-2026-11-04-IST-CAI__Air Cairo-2026-11-08-CAI-IST"
    )
    flight_line = next(item for item in result.cost_items if item.category == "flights")
    assert flight_line.amount_usd == Decimal("383.56")
    assert flight_line.source_offer_id == result.selected_flight_offer_id


def test_date_mismatch_is_excluded_and_reported_in_notes() -> None:
    result = calculate_budget(budget_input(flights_data=FlightsData(
        selected_outbound_flight=flight(date_matches_request=False),
        selected_return_flight=return_flight(date_matches_request=False),
    )))

    assert next(item for item in result.cost_items if item.category == "flights").amount_usd is None
    assert any("Outbound flight date 2026-11-04 differs from requested 2026-11-01" in note for note in result.notes)
    assert any("Return flight date 2026-11-08 differs from requested 2026-11-05" in note for note in result.notes)


def test_mismatched_flights_are_excluded_from_ledger() -> None:
    result = calculate_budget(budget_input(flights_data=FlightsData(
        selected_outbound_flight=flight(date_matches_request=False),
        selected_return_flight=return_flight(date_matches_request=False),
    )))

    flight_line = next(item for item in result.cost_items if item.category == "flights")
    assert flight_line.kind == "unknown"
    assert flight_line.amount_usd is None
    assert result.provider_subtotal_usd == Decimal("193.20")
    assert "flights" in result.missing_categories


def test_matching_flights_are_included() -> None:
    result = calculate_budget(budget_input(flights_data=FlightsData(
        selected_outbound_flight=flight(date_matches_request=True),
        selected_return_flight=return_flight(date_matches_request=True),
    )))

    flight_line = next(item for item in result.cost_items if item.category == "flights")
    assert flight_line.kind == "provider"
    assert flight_line.amount_usd == Decimal("383.56")
    assert result.provider_subtotal_usd == Decimal("576.76")


def test_activity_provider_kind_is_rejected() -> None:
    with pytest.raises(ValueError):
        ActivityItem(
            label="Provider activity", kind="provider", amount_usd=Decimal("10"),
            activity_ref=ActivityRef(date=date(2026, 11, 5), order=1), basis="Invalid kind.",
        )


def test_hotel_tax_is_itemized_once_and_not_added_to_inclusive_total_twice() -> None:
    result = calculate_budget(budget_input())

    assert result.selected_hotel_offer_id == "9406148"
    accommodation = next(item for item in result.cost_items if item.category == "accommodation")
    tax = next(item for item in result.cost_items if item.category == "taxes_fees")
    assert accommodation.amount_usd == Decimal("168.00")
    assert accommodation.source_offer_id == result.selected_hotel_offer_id == "9406148"
    assert tax.amount_usd == Decimal("25.20")
    assert result.provider_subtotal_usd == Decimal("576.76")


def test_unknown_hotel_taxes_are_not_zero_and_prevent_complete_total() -> None:
    result = calculate_budget(budget_input(selected_hotel=hotel(taxes_and_fees_usd=None, total_price_usd=None)))

    tax = next(item for item in result.cost_items if item.category == "taxes_fees")
    assert tax.amount_usd is None
    assert "taxes_fees" in result.missing_categories
    assert result.projected_total_usd is None
    assert result.status == "uncertain"


@pytest.mark.parametrize("value", ["-0.01", "NaN", "Infinity", "-Infinity", "0.004"])
def test_budget_rejects_negative_nonfinite_or_zero_after_cent_rounding(value: str) -> None:
    with pytest.raises(ValidationError):
        budget_input(budget_usd=Decimal(value))


@pytest.mark.parametrize("field", ["price_per_person_usd", "total_price_usd"])
@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "-Infinity"])
def test_flight_rejects_negative_and_nonfinite_prices(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        flight(**{field: Decimal(value)})


@pytest.mark.parametrize("field", ["base_price_usd", "taxes_and_fees_usd", "total_price_usd"])
@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "-Infinity"])
def test_hotel_rejects_negative_and_nonfinite_prices(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        hotel(**{field: Decimal(value)})


def test_unknown_selected_flight_leg_produces_unknown_flights_cost() -> None:
    result = calculate_budget(budget_input(flights_data=FlightsData(selected_outbound_flight=flight())))

    flight_line = next(item for item in result.cost_items if item.category == "flights")
    assert flight_line.kind == "unknown"
    assert flight_line.amount_usd is None
    assert "flights" in result.missing_categories


def test_missing_hotel_and_ancillary_costs_remain_unknown() -> None:
    result = calculate_budget(budget_input(selected_hotel=None, food=None, local_transport=None))

    assert "accommodation" in result.missing_categories
    assert "food" in result.missing_categories
    assert "local_transport" in result.missing_categories
    assert result.projected_total_usd is None


def test_provider_minimum_over_budget_wins_even_with_unknown_costs() -> None:
    result = calculate_budget(
        budget_input(
            budget_usd=Decimal("500"),
            flights_data=FlightsData(
                selected_outbound_flight=flight(), selected_return_flight=return_flight()
            ),
            selected_hotel=hotel(taxes_and_fees_usd=None, total_price_usd=None),
            food=None,
        )
    )

    assert result.provider_subtotal_usd == Decimal("551.56")
    assert result.projected_total_usd is None
    assert result.status == "over_budget"


def test_complete_total_equal_to_budget_is_within_budget() -> None:
    result = calculate_budget(budget_input(budget_usd=Decimal("576.76")))

    assert result.projected_total_usd == Decimal("576.76")
    assert result.status == "within_budget"


def test_estimates_do_not_make_incomplete_trip_within_budget() -> None:
    result = calculate_budget(budget_input(food=Decimal("30"), local_transport=None))

    assert result.estimated_subtotal_usd == Decimal("30.00")
    assert result.projected_total_usd is None
    assert result.status == "uncertain"


def test_activity_references_must_be_unique() -> None:
    activity = ActivityItem(
        label="Museum", kind="unknown", amount_usd=None,
        activity_ref=ActivityRef(date=date(2026, 11, 5), order=1), basis="Not structured in report.",
    )
    with pytest.raises(ValidationError):
        budget_input(activities=[activity, activity])


def test_additional_fee_references_must_be_unique() -> None:
    fees = [
        {"reference": "resort", "amount_usd": "10", "kind": "provider"},
        {"reference": "resort", "amount_usd": "5", "kind": "estimate"},
    ]
    with pytest.raises(ValidationError):
        budget_input(additional_fees=fees)


def test_included_fee_is_not_counted_again() -> None:
    result = calculate_budget(budget_input(additional_fees=[{
        "reference": "hotel-included", "amount_usd": "25.20", "kind": "provider", "included_in_offer": True,
    }]))

    assert len([item for item in result.cost_items if item.category == "taxes_fees"]) == 1
    assert result.provider_subtotal_usd == Decimal("576.76")


def test_unknown_fee_stays_unknown() -> None:
    result = calculate_budget(budget_input(additional_fees=[{
        "reference": "unpriced-fee", "amount_usd": None, "kind": "unknown",
    }]))

    assert "taxes_fees" in result.missing_categories
    assert result.projected_total_usd is None
    assert result.status == "uncertain"


def test_ziyad_fixture_slice_and_unknown_activity_path() -> None:
    """The report slice itself has no activities; this input exercises unknown activity handling."""
    result = calculate_budget(budget_input(
        food=None,
        local_transport=None,
        flights_data=FlightsData(
            selected_outbound_flight=flight(date_matches_request=False),
            selected_return_flight=return_flight(date_matches_request=False),
        ),
        activities=[ActivityItem(
            label="Unpriced activity", kind="unknown", amount_usd=None,
            activity_ref=ActivityRef(date=date(2026, 11, 5), order=1),
            basis="Activity costs are not structured in the report Markdown.",
        )],
    ))

    assert result.provider_subtotal_usd == Decimal("193.20")
    assert result.estimated_subtotal_usd == Decimal("0.00")
    assert result.projected_total_usd is None
    assert result.status == "uncertain"
    assert "activities" in result.missing_categories
    assert "flights" in result.missing_categories
    assert "food" in result.missing_categories
    assert "local_transport" in result.missing_categories
    assert result.selected_hotel_offer_id == "9406148"
    assert "flight offer id is synthetic" in " ".join(result.notes).lower()


def test_same_input_produces_deterministic_output() -> None:
    data = budget_input()

    assert calculate_budget(data).model_dump() == calculate_budget(data).model_dump()


def test_all_unknown_inputs_are_uncertain_not_within_budget() -> None:
    data = budget_input(
        flights_data=FlightsData(),
        selected_hotel=None,
        activities=[],
        food=None,
        local_transport=None,
    )

    result = calculate_budget(data)

    assert result.provider_subtotal_usd == Decimal("0.00")
    assert result.estimated_subtotal_usd == Decimal("0.00")
    assert result.projected_total_usd is None
    assert result.status == "uncertain"


def test_inputs_are_not_mutated() -> None:
    activity = ActivityItem(
        label="Museum", kind="estimate", amount_usd=Decimal("12.34"),
        activity_ref=ActivityRef(date=date(2026, 11, 5), order=1),
        basis="Caller supplied estimate.",
    )
    data = budget_input(
        activities=[activity],
        additional_fees=[{
            "reference": "seat-fee", "amount_usd": "4.50", "kind": "provider",
        }],
    )
    before = data.model_dump()

    first = calculate_budget(data)
    second = calculate_budget(data)

    assert second.model_dump() == first.model_dump()
    assert data.model_dump() == before


def test_fee_aware_selection_prefers_known_total() -> None:
    candidates = [
        OfferCandidate(id="unknown-cheapest-base", base_usd=Decimal("50"), additional_fees_usd=None),
        OfferCandidate(id="known-second", base_usd=Decimal("90"), additional_fees_usd=Decimal("5")),
        OfferCandidate(id="known-third", base_usd=Decimal("80"), additional_fees_usd=Decimal("20")),
    ]

    result = calculate_budget(budget_input(
        flights_data=FlightsData(), flight_candidates=candidates,
    ))

    assert result.selected_flight_offer_id == "known-second"
    assert next(item for item in result.cost_items if item.category == "flights").amount_usd == Decimal("90.00")


def test_included_in_base_is_known_total_and_has_no_unknown_fee_line() -> None:
    included_offer = OfferCandidate(
        id="included-100", base_usd=Decimal("100"), additional_fees_usd=None,
        included_in_base=True,
    )
    known_fee_offer = OfferCandidate(
        id="fee-130", base_usd=Decimal("100"), additional_fees_usd=Decimal("30"),
    )
    result = calculate_budget(budget_input(
        flights_data=FlightsData(), flight_candidates=[included_offer, known_fee_offer],
    ))

    assert result.selected_flight_offer_id == "included-100"
    assert not any(
        item.id == "flight-taxes-fees" and item.kind == "unknown"
        for item in result.cost_items
    )


def test_fee_aware_selection_tie_break_by_id() -> None:
    selected, notes = select_offer([
        OfferCandidate(id="z-offer", base_usd=Decimal("90"), additional_fees_usd=Decimal("10")),
        OfferCandidate(id="a-offer", base_usd=Decimal("95"), additional_fees_usd=Decimal("5")),
    ], "flight")

    assert selected is not None and selected.id == "a-offer"
    assert notes == []


def test_fee_aware_selection_falls_back_to_lowest_base_with_warning() -> None:
    selected, notes = select_offer([
        OfferCandidate(id="higher", base_usd=Decimal("100"), additional_fees_usd=None),
        OfferCandidate(id="lower", base_usd=Decimal("80"), additional_fees_usd=None),
    ], "flight")

    assert selected is not None and selected.id == "lower"
    assert len(notes) == 1 and "unknown additional fees" in notes[0]


def test_invalid_candidate_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        budget_input(
            flights_data=FlightsData(),
            flight_candidates=[OfferCandidate(
                id="", base_usd=Decimal("10"), additional_fees_usd=Decimal("1")
            )],
        )


def test_duplicate_candidate_ids_are_rejected() -> None:
    candidate = OfferCandidate(id="same", base_usd=Decimal("10"), additional_fees_usd=Decimal("1"))
    with pytest.raises(ValueError, match="must be unique"):
        budget_input(flights_data=FlightsData(), flight_candidates=[candidate, candidate])


def test_ambiguous_selection_raises() -> None:
    candidate = OfferCandidate(id="candidate", base_usd=Decimal("10"), additional_fees_usd=Decimal("1"))
    with pytest.raises(ValueError, match="selected outbound flight"):
        calculate_budget(budget_input(flight_candidates=[candidate]))


def test_hotel_candidate_id_is_exposed() -> None:
    candidates = [
        OfferCandidate(id="higher-total", base_usd=Decimal("100"), additional_fees_usd=Decimal("20")),
        OfferCandidate(id="winning-hotel", base_usd=Decimal("90"), additional_fees_usd=Decimal("5")),
    ]
    data = budget_input(selected_hotel=None, hotel_candidates=candidates)

    result = calculate_budget(data)

    assert result.selected_hotel_offer_id == "winning-hotel"
    accommodation = next(item for item in result.cost_items if item.category == "accommodation")
    assert accommodation.source_offer_id == "winning-hotel"


def _acceptance_budget_input(budget: str) -> BudgetInput:
    return budget_input(
        budget_usd=Decimal(budget),
        flights_data=FlightsData(),
        flight_candidates=[OfferCandidate(
            id="provider-flight", base_usd=Decimal("950"),
            additional_fees_usd=Decimal("0"),
        )],
        selected_hotel=hotel(
            base_price_usd=Decimal("0"), taxes_and_fees_usd=Decimal("0"),
            total_price_usd=Decimal("0"), price_per_night_usd=Decimal("0"),
        ),
        activities=[ActivityItem(
            label="Trip activities", kind="estimate", amount_usd=Decimal("190"),
            activity_ref=ActivityRef(date=date(2026, 11, 5), order=1),
            basis="Fixture estimate.",
        )],
        food=Decimal("0"),
        local_transport=Decimal("0"),
    )


def test_within_budget_950_provider_190_estimates_projected_1140() -> None:
    result = calculate_budget(_acceptance_budget_input("1200"))

    assert result.provider_subtotal_usd == Decimal("950.00")
    assert result.estimated_subtotal_usd == Decimal("190.00")
    assert result.projected_total_usd == Decimal("1140.00")
    assert result.status == "within_budget"


def test_same_costs_budget_1000_over_budget() -> None:
    result = calculate_budget(_acceptance_budget_input("1000"))

    assert result.provider_subtotal_usd == Decimal("950.00")
    assert result.estimated_subtotal_usd == Decimal("190.00")
    assert result.projected_total_usd == Decimal("1140.00")
    assert result.status == "over_budget"


def test_partial_price_provider_550_estimates_40_null_uncertain() -> None:
    data = budget_input(
        budget_usd=Decimal("500"),
        flights_data=FlightsData(),
        flight_candidates=[OfferCandidate(
            id="provider-flight", base_usd=Decimal("550"),
            additional_fees_usd=Decimal("0"),
        )],
        selected_hotel=hotel(
            base_price_usd=Decimal("0"), taxes_and_fees_usd=Decimal("0"),
            total_price_usd=Decimal("0"), price_per_night_usd=Decimal("0"),
        ),
        activities=[ActivityItem(
            label="Trip activities", kind="estimate", amount_usd=Decimal("40"),
            activity_ref=ActivityRef(date=date(2026, 11, 5), order=1), basis="Fixture estimate.",
        )],
        food=None,
        local_transport=Decimal("0"),
    )
    result = calculate_budget(data)

    assert result.provider_subtotal_usd == Decimal("550.00")
    assert result.estimated_subtotal_usd == Decimal("40.00")
    assert result.projected_total_usd is None
    # Contract precedence marks the trip over budget when known provider costs exceed $500.
    assert result.status == "over_budget"


def test_ledger_items_are_rounded_to_cents_before_summing() -> None:
    """Decimal quantize uses the default ROUND_HALF_EVEN mode: 10.005 rounds to 10.00."""
    data = budget_input(
        flights_data=FlightsData(),
        selected_hotel=hotel(
            base_price_usd=Decimal("0"), taxes_and_fees_usd=Decimal("0"),
            total_price_usd=Decimal("0"), price_per_night_usd=Decimal("0"),
        ),
        flight_candidates=[OfferCandidate(
            id="fractional-flight", base_usd=Decimal("10.005"),
            additional_fees_usd=Decimal("10.005"),
        )],
    )
    result = calculate_budget(data)

    assert result.provider_subtotal_usd == Decimal("20.00")
    assert [item.amount_usd for item in result.cost_items if item.kind == "provider"][:2] == [
        Decimal("10.00"), Decimal("10.00")
    ]


def test_unknown_flight_id_is_not_silently_accepted() -> None:
    result = calculate_budget(budget_input())

    assert result.selected_flight_offer_id == (
        "Turkish Airlines-2026-11-04-IST-CAI__Air Cairo-2026-11-08-CAI-IST"
    )


def test_recompute_reflects_new_selected_offer() -> None:
    hotel_offer = hotel()
    first = calculate_budget(budget_input(
        flights_data=FlightsData(),
        selected_hotel=hotel_offer,
        flight_candidates=[
            OfferCandidate(id="candidate-a", base_usd=Decimal("100"), additional_fees_usd=Decimal("0")),
            OfferCandidate(id="candidate-b", base_usd=Decimal("120"), additional_fees_usd=Decimal("0")),
        ],
    ))
    second = calculate_budget(budget_input(
        flights_data=FlightsData(),
        selected_hotel=hotel_offer,
        flight_candidates=[
            OfferCandidate(id="candidate-a", base_usd=Decimal("130"), additional_fees_usd=Decimal("0")),
            OfferCandidate(id="candidate-b", base_usd=Decimal("90"), additional_fees_usd=Decimal("0")),
        ],
    ))

    assert first.selected_flight_offer_id == "candidate-a"
    assert second.selected_flight_offer_id == "candidate-b"
    assert second.provider_subtotal_usd < first.provider_subtotal_usd
