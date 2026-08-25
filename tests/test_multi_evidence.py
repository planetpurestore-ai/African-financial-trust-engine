from datetime import date
from decimal import Decimal

from app.evidence import Evidence
from app.models import Invoice
from app.verification import compare_invoice_to_evidence_set


def invoice():
    return Invoice(
        invoice_number="INV-100",
        supplier_name="Supplier Ltd",
        buyer_name="Buyer Ltd",
        amount=Decimal("10000.00"),
        currency="USD",
        issue_date=date(2026, 1, 10),
        due_date=date(2026, 2, 10),
    )


def test_multiple_evidence_items_can_combine_to_verify_invoice():
    result = compare_invoice_to_evidence_set(
        invoice(),
        [
            Evidence(
                evidence_id="PO-100",
                evidence_type="purchase_order",
                reference_number="PO-100",
                supplier_name="Supplier Ltd",
                buyer_name="Buyer Ltd",
            ),
            Evidence(
                evidence_id="PAY-100",
                evidence_type="payment_record",
                reference_number="PAY-100",
                amount=Decimal("10000.00"),
                currency="USD",
            ),
        ],
    )

    assert result["status"] == "verified"
    assert result["verification_score"] == 100.0
    assert result["supporting_evidence"]["supplier_match"] == ["PO-100"]
    assert result["supporting_evidence"]["buyer_match"] == ["PO-100"]
    assert result["supporting_evidence"]["amount_match"] == ["PAY-100"]
    assert result["supporting_evidence"]["currency_match"] == ["PAY-100"]


def test_conflicting_evidence_does_not_hide_the_conflict():
    result = compare_invoice_to_evidence_set(
        invoice(),
        [
            Evidence(
                evidence_id="PO-101",
                evidence_type="purchase_order",
                reference_number="PO-101",
                supplier_name="Supplier Ltd",
                buyer_name="Buyer Ltd",
                amount=Decimal("9000.00"),
                currency="USD",
            ),
            Evidence(
                evidence_id="PO-102",
                evidence_type="purchase_order",
                reference_number="PO-102",
                supplier_name="Supplier Ltd",
                buyer_name="Buyer Ltd",
                amount=Decimal("10000.00"),
                currency="USD",
            ),
        ],
    )

    assert result["status"] == "verified"
    assert result["supporting_evidence"]["amount_match"] == ["PO-102"]
