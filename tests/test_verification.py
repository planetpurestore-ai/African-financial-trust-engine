from datetime import date
from decimal import Decimal

from app.evidence import Evidence
from app.models import Invoice
from app.verification import compare_invoice_to_evidence


def make_invoice():
    return Invoice(
        invoice_number="INV-001",
        supplier_name="Supplier Ltd",
        buyer_name="Buyer Ltd",
        amount=Decimal("10000.00"),
        currency="USD",
        issue_date=date(2026, 1, 10),
        due_date=date(2026, 2, 10),
    )


def test_matching_evidence_is_verified():
    evidence = Evidence(
        evidence_id="PO-001",
        evidence_type="purchase_order",
        reference_number="PO-001",
        supplier_name="Supplier Ltd",
        buyer_name="Buyer Ltd",
        amount=Decimal("10000.00"),
        currency="USD",
    )

    result = compare_invoice_to_evidence(make_invoice(), evidence)

    assert result["status"] == "verified"
    assert result["passed_checks"] == 4
    assert result["verification_score"] == 100.0
    assert result["failed_checks"] == []


def test_mismatched_amount_requires_review():
    evidence = Evidence(
        evidence_id="PO-002",
        evidence_type="purchase_order",
        reference_number="PO-002",
        supplier_name="Supplier Ltd",
        buyer_name="Buyer Ltd",
        amount=Decimal("9000.00"),
        currency="USD",
    )

    result = compare_invoice_to_evidence(make_invoice(), evidence)

    assert result["status"] == "review_required"
    assert result["passed_checks"] == 3
    assert result["verification_score"] == 75.0
    assert "amount_match" in result["failed_checks"]


def test_missing_evidence_fields_are_not_treated_as_verified():
    evidence = Evidence(
        evidence_id="PO-003",
        evidence_type="purchase_order",
        reference_number="PO-003",
    )

    result = compare_invoice_to_evidence(make_invoice(), evidence)

    assert result["status"] == "review_required"
    assert result["passed_checks"] == 0
    assert result["verification_score"] == 0.0
    assert len(result["failed_checks"]) == 4
