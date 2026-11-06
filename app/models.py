from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator


class Invoice(BaseModel):
    invoice_number: str = Field(min_length=1)
    supplier_name: str = Field(min_length=1)
    buyer_name: str = Field(min_length=1)
    amount: Decimal = Field(gt=0)
    subtotal: Decimal | None = Field(default=None, ge=0)
    tax_amount: Decimal | None = Field(default=None, ge=0)
    total_amount: Decimal | None = Field(default=None, gt=0)
    purchase_order_number: str | None = None
    contract_reference: str | None = None
    delivery_reference: str | None = None
    currency: str
    issue_date: date
    due_date: date

    @field_validator("invoice_number", "supplier_name", "buyer_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("purchase_order_number", "contract_reference", "delivery_reference")
    @classmethod
    def normalize_optional_references(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("currency must be a 3-letter ISO-style code")
        return value

    @model_validator(mode="after")
    def validate_invoice_arithmetic(self):
        if self.total_amount is not None and self.total_amount != self.amount:
            raise ValueError("total_amount must equal the invoice amount")
        if self.subtotal is not None and self.tax_amount is not None:
            calculated_total = self.subtotal + self.tax_amount
            if calculated_total != self.amount:
                raise ValueError("subtotal plus tax_amount must equal the invoice amount")
            if self.total_amount is not None and calculated_total != self.total_amount:
                raise ValueError("subtotal plus tax_amount must equal total_amount")
        return self

    @model_validator(mode="after")
    def validate_dates(self):
        if self.due_date < self.issue_date:
            raise ValueError("due_date cannot be before issue_date")
        return self
