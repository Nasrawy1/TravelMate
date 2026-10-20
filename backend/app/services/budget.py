"""BE-04 deterministic budget calculator.

Selection and invalid-reference rejection are owned by Ziyad's travel adapter /
BE-03. BE-04 is a pure calculator: the same inputs produce the same outputs,
with no side effects, I/O or external calls. The current input has one selected
outbound flight, return flight and hotel.

TODO(BE-03): If the adapter later supplies candidate offers, prefer comparable
known-fee totals; choose lowest base plus additional fees; tie-break
lexicographically by offer ID; use the unknown-fee fallback only if it is the
sole option, with a note.

The flight offer ID is synthetic because Ziyad's report slice has no flight
IDs: ``outbound-airline-date-origin-destination__return-airline-date-origin-destination``.
"""

from decimal import Decimal

from app.services.models import (
    BudgetInput,
    BudgetOutput,
    CostItem,
    OfferCandidate,
    cents,
)


def select_offer(
    candidates: list[OfferCandidate], category: str
) -> tuple[OfferCandidate | None, list[str]]:
    """Select a comparable known-fee total, falling back to lowest base."""
    if not candidates:
        return None, []

    known_total_candidates = [
        candidate for candidate in candidates
        if candidate.additional_fees_usd is not None
    ]
    if known_total_candidates:
        selected = min(
            known_total_candidates,
            key=lambda candidate: (
                candidate.base_usd + candidate.additional_fees_usd,
                candidate.id,
            ),
        )
        return selected, []

    selected = min(candidates, key=lambda candidate: (candidate.base_usd, candidate.id))
    return selected, [
        f"All {category} candidate totals have unknown additional fees; "
        f"selected lowest base offer {selected.id} without a verified final total."
    ]


def calculate_budget(data: BudgetInput) -> BudgetOutput:
    """Build a normalized cost ledger and derive deterministic budget totals."""
    items: list[CostItem] = []
    notes = [
        "Flight offer ID is synthetic: outbound-airline-date-origin-destination__"
        "return-airline-date-origin-destination.",
        "provider_subtotal_usd and estimated_subtotal_usd include only categories "
        "with priced entries; unknown categories are excluded and listed in "
        "missing_categories. These subtotals are not the complete trip cost or "
        "remaining balance.",
    ]
    outbound = data.flights_data.selected_outbound_flight
    returning = data.flights_data.selected_return_flight
    selected_flight_candidate: OfferCandidate | None = None
    selected_hotel_candidate: OfferCandidate | None = None

    if data.flight_candidates:
        selected_flight_candidate, selection_notes = select_offer(data.flight_candidates, "flight")
        notes.extend(selection_notes)
        notes.append("Flight selection mode: fee-aware candidate selection.")
    else:
        notes.append("Flight selection mode: caller-provided selected flight legs.")

    if data.hotel_candidates:
        selected_hotel_candidate, selection_notes = select_offer(data.hotel_candidates, "hotel")
        notes.extend(selection_notes)
        notes.append("Hotel selection mode: fee-aware candidate selection.")
    else:
        notes.append("Hotel selection mode: caller-provided selected hotel.")

    if selected_flight_candidate is not None:
        flight_id = selected_flight_candidate.id
        items.append(CostItem(
            id="flights", category="flights", label="Selected round-trip flights",
            amount_usd=cents(selected_flight_candidate.base_usd), kind="provider",
            basis="Selected normalized flight candidate base price.", source_offer_id=flight_id,
        ))
        if selected_flight_candidate.additional_fees_usd is None:
            items.append(CostItem(
                id="flight-taxes-fees", category="taxes_fees", label="Selected flight taxes and fees",
                amount_usd=None, kind="unknown",
                basis="Selected flight candidate has unknown additional fees.", source_offer_id=flight_id,
            ))
        elif selected_flight_candidate.additional_fees_usd > 0:
            items.append(CostItem(
                id="flight-taxes-fees", category="taxes_fees", label="Selected flight taxes and fees",
                amount_usd=cents(selected_flight_candidate.additional_fees_usd), kind="provider",
                basis="Selected flight candidate additional fees, counted once.", source_offer_id=flight_id,
            ))
    elif outbound is not None and returning is not None:
        flight_id = (
            f"{outbound.airline}-{outbound.flight_date}-{outbound.origin_airport}-"
            f"{outbound.destination_airport}__{returning.airline}-{returning.flight_date}-"
            f"{returning.origin_airport}-{returning.destination_airport}"
        )
        items.append(CostItem(
            id="flights", category="flights", label="Selected round-trip flights",
            amount_usd=cents(outbound.total_price_usd + returning.total_price_usd),
            kind="provider", basis="Sum of selected normalized outbound and return totals; each already covers all travelers.",
            source_offer_id=flight_id,
        ))
        for leg_name, flight in (("Outbound", outbound), ("Return", returning)):
            if not flight.date_matches_request:
                notes.append(
                    f"{leg_name} flight date {flight.flight_date} differs from requested {flight.requested_date}."
                )
    else:
        flight_id = None
        items.append(CostItem(
            id="flights", category="flights", label="Selected round-trip flights",
            amount_usd=None, kind="unknown", basis="Both selected flight legs are required for a priced round trip.",
        ))

    hotel = data.selected_hotel
    if selected_hotel_candidate is not None:
        hotel_id = None
        items.append(CostItem(
            id="accommodation", category="accommodation", label="Selected hotel base price",
            amount_usd=cents(selected_hotel_candidate.base_usd), kind="provider",
            basis="Selected normalized hotel candidate base price.",
            source_offer_id=selected_hotel_candidate.id,
        ))
        if selected_hotel_candidate.additional_fees_usd is None:
            items.append(CostItem(
                id="hotel-taxes-fees", category="taxes_fees", label="Selected hotel taxes and fees",
                amount_usd=None, kind="unknown", basis="Selected hotel candidate has unknown additional fees.",
                source_offer_id=selected_hotel_candidate.id,
            ))
        elif selected_hotel_candidate.additional_fees_usd > 0:
            items.append(CostItem(
                id="hotel-taxes-fees", category="taxes_fees", label="Selected hotel taxes and fees",
                amount_usd=cents(selected_hotel_candidate.additional_fees_usd), kind="provider",
                basis="Selected hotel candidate additional fees, counted once.",
                source_offer_id=selected_hotel_candidate.id,
            ))
    elif hotel is None:
        items.append(CostItem(
            id="accommodation", category="accommodation", label="Selected hotel base price",
            amount_usd=None, kind="unknown", basis="No selected hotel was supplied.",
        ))
        items.append(CostItem(
            id="hotel-taxes-fees", category="taxes_fees", label="Selected hotel taxes and fees",
            amount_usd=None, kind="unknown", basis="No selected hotel was supplied; fees are unknown.",
        ))
        hotel_id = None
    else:
        hotel_id = hotel.hotel_id
        items.append(CostItem(
            id="accommodation", category="accommodation", label=f"{hotel.name} base price",
            amount_usd=cents(hotel.base_price_usd), kind="provider",
            basis="Selected hotel base price for the entire stay; the hotel total already includes taxes and fees.",
            source_offer_id=hotel.hotel_id,
        ))
        if hotel.taxes_and_fees_usd is None:
            items.append(CostItem(
                id="hotel-taxes-fees", category="taxes_fees", label=f"{hotel.name} taxes and fees",
                amount_usd=None, kind="unknown",
                basis="Hotel taxes_and_fees_usd is unknown; total_price_usd is not treated as a fee breakdown.",
                source_offer_id=hotel.hotel_id,
            ))
        elif hotel.taxes_and_fees_usd > 0:
            items.append(CostItem(
                id="hotel-taxes-fees", category="taxes_fees", label=f"{hotel.name} taxes and fees",
                amount_usd=cents(hotel.taxes_and_fees_usd), kind="provider",
                basis="Selected hotel taxes_and_fees_usd, counted once; not added again to the already inclusive total.",
                source_offer_id=hotel.hotel_id,
            ))

    for index, activity in enumerate(data.activities, start=1):
        items.append(CostItem(
            id=f"activity-{activity.activity_ref.date}-{activity.activity_ref.order}",
            category="activities", label=activity.label,
            amount_usd=None if activity.amount_usd is None else cents(activity.amount_usd),
            kind=activity.kind, basis=activity.basis, activity_ref=activity.activity_ref,
        ))

    for category, amount in (("food", data.food), ("local_transport", data.local_transport)):
        items.append(CostItem(
            id=category, category=category, label=category.replace("_", " ").title(),
            amount_usd=None if amount is None else cents(amount),
            kind="unknown" if amount is None else "estimate",
            basis="No structured whole-trip cost was supplied." if amount is None else "Caller-supplied whole-trip estimate.",
        ))

    for fee in data.additional_fees:
        if fee.included_in_offer and fee.amount_usd is not None:
            continue
        items.append(CostItem(
            id=f"fee-{fee.reference}", category="taxes_fees", label=f"Additional fee: {fee.reference}",
            amount_usd=None if fee.amount_usd is None else cents(fee.amount_usd),
            kind=fee.kind, basis="Additional fee supplied by caller; included fees are not counted twice.",
        ))

    provider = cents(sum(
        (item.amount_usd for item in items if item.kind == "provider" and item.amount_usd is not None),
        Decimal("0.00"),
    ))
    estimated = cents(sum(
        (item.amount_usd for item in items if item.kind == "estimate" and item.amount_usd is not None),
        Decimal("0.00"),
    ))
    unknown_items = [item for item in items if item.kind == "unknown"]
    missing = list(dict.fromkeys(item.category for item in unknown_items))
    projected = None if unknown_items else cents(provider + estimated)
    if provider > data.budget_usd or (projected is not None and projected > data.budget_usd):
        status = "over_budget"
    elif projected is not None:
        status = "within_budget"
    else:
        status = "uncertain"

    for category in missing:
        notes.append(f"{category} includes unknown costs; projected total is incomplete.")

    return BudgetOutput(
        budget_usd=data.budget_usd,
        selected_flight_offer_id=flight_id,
        selected_hotel_offer_id=hotel_id,
        selected_hotel_candidate_id=(
            None if selected_hotel_candidate is None else selected_hotel_candidate.id
        ),
        provider_subtotal_usd=provider,
        estimated_subtotal_usd=estimated,
        projected_total_usd=projected,
        status=status,
        missing_categories=missing,
        notes=notes,
        cost_items=items,
    )
