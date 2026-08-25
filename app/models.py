from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


class Invoice(BaseModel):
    invoice_number: str = Field(min_length=1)
    supplier_name: str = Field(min_length=1)
    buyer_name: str = Field(min_length=1)
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    issue_date: date
    due_date: date

    @field_validator("invoice_number", "supplier_name", "buyer_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a 3-letter ISO-style code")
        return value

    @model_validator(mode="after")
    def validate_dates(self):
        if self.due_date < self.issue_date:
            raise ValueError("due_date cannot be before issue_date")
        return self
