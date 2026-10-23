from datetime import date
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
)


# TODO(BE-03 / Ziyad): Replace with the official list from adapter-contracts.md
# once the verified canonical city list is provided.
SUPPORTED_CITIES = frozenset({"Istanbul", "Rome", "Cairo", "Paris", "Dubai"})


class GenerateTripRequest(BaseModel):
    """Strict public request; city labels are normalized to title-cased canonicals."""

    model_config = ConfigDict(extra="forbid")

    departure_city: StrictStr = Field(min_length=1)
    destination_city: StrictStr = Field(min_length=1)
    start_date: date
    return_date: date
    adults: StrictInt = Field(ge=1, le=4)
    budget_usd: Decimal = Field(gt=0, allow_inf_nan=False)

    @field_validator("budget_usd", mode="before")
    @classmethod
    def budget_must_be_a_json_number(cls, value: object) -> object:
        if isinstance(value, bool) or isinstance(value, str):
            raise ValueError("budget_usd must be a JSON number")
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        return value

    @field_validator("departure_city", "destination_city", mode="before")
    @classmethod
    def normalize_city_label(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().title()
        return value

    @field_validator("budget_usd")
    @classmethod
    def budget_must_remain_positive_after_rounding(
        cls, value: Decimal
    ) -> Decimal:
        rounded = value.quantize(Decimal("0.01"))
        if rounded <= Decimal("0.00"):
            raise ValueError(
                "budget_usd must be greater than zero after rounding to cents"
            )
        return rounded
