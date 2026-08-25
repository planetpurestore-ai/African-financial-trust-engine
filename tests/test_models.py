from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.evidence import Evidence
from app.models import Invoice


def test_invoice_normalizes_currency_and_text():
    invoice = Invoice(
        invoice_number=" INV-100 ",
        supplier_name=" Supplier Ltd ",
        buyer_name=" Buyer Ltd ",
        amount=Decimal("1000.00"),
        currency=" usd ",
        issue_date=date(2026, 1, 10),
        due_date=date(2026, 2, 10),
    )

    assert invoice.invoice_number == "INV-100"
    assert invoice.supplier_name == "Supplier Ltd"
    assert invoice.currency == "USD"


def test_invoice_rejects_due_date_before_issue_date():
    with pytest.raises(ValidationError):
        Invoice(
            invoice_number="INV-101",
            supplier_name="Supplier Ltd",
            buyer_name="Buyer Ltd",
            amount=Decimal("1000.00"),
            currency="USD",
            issue_date=date(2026, 2, 10),
            due_date=date(2026, 1, 10),
        )


def test_evidence_normalizes_currency_and_rejects_blank_reference():
    evidence = Evidence(
        evidence_id="PO-100",
        evidence_type="purchase_order",
        reference_number=" PO-100 ",
        currency=" eur ",
    )

    assert evidence.reference_number == "PO-100"
    assert evidence.currency == "EUR"

    with pytest.raises(ValidationError):
        Evidence(
            evidence_id="PO-101",
            evidence_type="purchase_order",
            reference_number="   ",
        )
