"""Typed inputs and outputs for deterministic BE-04 budget assessment."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    field_validator,
    model_validator,
)

Money = Annotated[Decimal, Field(ge=Decimal("0"), allow_inf_nan=False)]
OptionalMoney = Money | None
Category = Literal[
    "flights", "accommodation", "activities", "food", "local_transport", "taxes_fees"
]
CostKind = Literal["provider", "estimate", "unknown"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OfferCandidate(BaseModel):
    id: str
    base_usd: Money
    additional_fees_usd: OptionalMoney
    included_in_base: bool = False

    @model_validator(mode="after")
    def fees_not_double_counted(self) -> "OfferCandidate":
        if self.included_in_base and self.additional_fees_usd is not None:
            raise ValueError("additional fees cannot be supplied when included_in_base is true")
        return self


class SelectedFlight(StrictModel):
    airline: str
    carrier_codes: list[str]
    origin_airport: str
    destination_airport: str
    flight_date: date
    requested_date: date
    date_matches_request: bool
    days_from_requested_date: int
    is_direct: bool
    stops_label: str
    price_per_person_usd: Money
    travelers: PositiveInt
    total_price_usd: Money
    quoted_at: datetime
    booking_link: str


class FlightsData(StrictModel):
    selected_outbound_flight: SelectedFlight | None = None
    selected_return_flight: SelectedFlight | None = None


class HotelOffer(StrictModel):
    hotel_id: int
    name: str
    star_rating: int | None = None
    review_score: Annotated[Decimal, Field(ge=0, le=10, allow_inf_nan=False)] | None = None
    nights: PositiveInt
    base_price_usd: Money
    taxes_and_fees_usd: Money | None
    total_price_usd: Money | None
    price_per_night_usd: Money | None = None
    fits_budget: bool | None = None

    @model_validator(mode="after")
    def total_matches_known_components(self) -> "HotelOffer":
        if self.taxes_and_fees_usd is not None and self.total_price_usd is not None:
            expected = self.base_price_usd + self.taxes_and_fees_usd
            reported = self.total_price_usd
            # Compare exact normalized cents and source decimals so sub-cent
            # discrepancies cannot be hidden by cent quantization.
            if cents(expected) != cents(reported) or expected != reported:
                raise ValueError("hotel total must equal base plus taxes and fees")
        return self


class ZiyadReportSlice(StrictModel):
    flights_data: FlightsData
    hotels_data: list[HotelOffer]
    ai_recommendation_report: str


class ActivityRef(StrictModel):
    date: date
    order: PositiveInt


class ActivityItem(StrictModel):
    label: str
    kind: CostKind
    amount_usd: Money | None
    activity_ref: ActivityRef
    basis: str

    @model_validator(mode="after")
    def amount_matches_kind(self) -> "ActivityItem":
        if (self.kind == "unknown") != (self.amount_usd is None):
            raise ValueError("unknown activities require null amount; known costs require an amount")
        return self


class AdditionalFee(StrictModel):
    reference: str
    amount_usd: Money | None
    kind: Literal["provider", "estimate", "unknown"]
    included_in_offer: bool = False

    @model_validator(mode="after")
    def amount_matches_kind(self) -> "AdditionalFee":
        if (self.kind == "unknown") != (self.amount_usd is None):
            raise ValueError("unknown fees require null amount; known fees require an amount")
        return self


class BudgetInput(StrictModel):
    budget_usd: Money
    flights_data: FlightsData
    selected_hotel: HotelOffer | None
    activities: list[ActivityItem] = Field(default_factory=list)
    food: Money | None = None
    local_transport: Money | None = None
    additional_fees: list[AdditionalFee] = Field(default_factory=list)
    flight_candidates: list[OfferCandidate] = Field(default_factory=list)
    hotel_candidates: list[OfferCandidate] = Field(default_factory=list)

    @field_validator("budget_usd")
    @classmethod
    def positive_after_cent_rounding(cls, value: Decimal) -> Decimal:
        if cents(value) <= 0:
            raise ValueError("budget must be greater than zero after rounding to cents")
        return cents(value)

    @model_validator(mode="after")
    def references_are_unique(self) -> "BudgetInput":
        refs = [item.activity_ref for item in self.activities]
        if len(refs) != len(set((ref.date, ref.order) for ref in refs)):
            raise ValueError("activity references must be unique")
        fee_refs = [fee.reference for fee in self.additional_fees]
        if len(fee_refs) != len(set(fee_refs)):
            raise ValueError("additional fee references must be unique")
        return self

    @model_validator(mode="after")
    def candidate_ids_are_valid(self) -> "BudgetInput":
        for category, candidates in (
            ("flight", self.flight_candidates),
            ("hotel", self.hotel_candidates),
        ):
            if any(not candidate.id for candidate in candidates):
                raise ValueError(f"{category} candidate IDs must not be empty")
            ids = [candidate.id for candidate in candidates]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{category} candidate IDs must be unique")
        return self

    @model_validator(mode="after")
    def candidate_selection_is_unambiguous(self) -> "BudgetInput":
        if self.flight_candidates and self.flights_data.selected_outbound_flight is not None:
            raise ValueError("flight_candidates cannot be combined with a selected outbound flight")
        if self.flight_candidates and self.flights_data.selected_return_flight is not None:
            raise ValueError("flight_candidates cannot be combined with a selected return flight")
        if self.hotel_candidates and self.selected_hotel is not None:
            raise ValueError("hotel_candidates cannot be combined with selected_hotel")
        return self


class CostItem(StrictModel):
    id: str
    category: Category
    label: str
    amount_usd: Money | None
    kind: CostKind
    coverage: Literal["entire_trip_all_travelers"] = "entire_trip_all_travelers"
    basis: str
    source_offer_id: str | int | None = None
    activity_ref: ActivityRef | None = None

    @model_validator(mode="after")
    def amount_matches_kind(self) -> "CostItem":
        if (self.kind == "unknown") != (self.amount_usd is None):
            raise ValueError("unknown costs require null amount; known costs require an amount")
        return self


class BudgetOutput(StrictModel):
    budget_usd: Money
    selected_flight_offer_id: str | None
    selected_hotel_offer_id: int | None
    selected_hotel_candidate_id: str | None = None
    provider_subtotal_usd: Money
    estimated_subtotal_usd: Money
    projected_total_usd: Money | None
    status: Literal["within_budget", "over_budget", "uncertain"]
    missing_categories: list[Category]
    notes: list[str]
    cost_items: list[CostItem]


def cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))
