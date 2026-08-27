from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Evidence(BaseModel):
    evidence_id: str = Field(min_length=1)
    evidence_type: Literal["purchase_order", "contract", "payment_record"]
    reference_number: str = Field(min_length=1)
    supplier_name: str | None = None
    buyer_name: str | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = None
    evidence_date: date | None = None
    description: str | None = None

    @field_validator("evidence_id", "reference_number")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("supplier_name", "buyer_name", "description")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a 3-letter ISO-style code")
        return value
