from datetime import date
from decimal import Decimal, InvalidOperation
import re

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    ValidationInfo,
)


class GenerateTripRequest(BaseModel):
    """Strict public request; city labels are trimmed, then resolved by the adapter."""

    model_config = ConfigDict(extra="forbid")

    departure_city: StrictStr = Field(min_length=1, max_length=200)
    destination_city: StrictStr = Field(min_length=1, max_length=200)
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
            # Strip surrounding whitespace only; the adapter owns city resolution.
            return value.strip()
        return value

    @field_validator("start_date", "return_date", mode="before")
    @classmethod
    def date_must_use_yyyy_mm_dd(cls, value: object, info: ValidationInfo) -> date:
        field_name = info.field_name or "date"
        error_message = f"{field_name} must be a string in YYYY-MM-DD format"
        if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
            raise ValueError(error_message)
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(error_message) from exc

    @field_validator("budget_usd")
    @classmethod
    def budget_must_remain_positive_after_rounding(
        cls, value: Decimal
    ) -> Decimal:
        try:
            rounded = value.quantize(Decimal("0.01"))
        except InvalidOperation as exc:
            # Decimal's default precision cannot quantize arbitrarily large budgets.
            raise ValueError("budget_usd is too large to process") from exc
        if rounded <= Decimal("0.00"):
            raise ValueError(
                "budget_usd must be greater than zero after rounding to cents"
            )
        return rounded
