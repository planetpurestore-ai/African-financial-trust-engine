from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field


class Evidence(BaseModel):
    evidence_id: str = Field(min_length=1)
    evidence_type: Literal["purchase_order", "contract", "payment_record"]
    reference_number: str = Field(min_length=1)
    supplier_name: str | None = None
    buyer_name: str | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    evidence_date: date | None = None
    description: str | None = None
