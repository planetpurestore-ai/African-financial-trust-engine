from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field


class Invoice(BaseModel):
    invoice_number: str = Field(min_length=1)
    supplier_name: str = Field(min_length=1)
    buyer_name: str = Field(min_length=1)
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    issue_date: date
    due_date: date
