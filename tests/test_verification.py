from datetime import date
from decimal import Decimal

from app.evidence import Evidence
from app.models import Invoice
from app.verification import compare_invoice_to_evidence, compare_invoice_to_evidence_set


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


def make_payment():
    return Evidence(
        evidence_id="PAY-001",
        evidence_type="payment_record",
        reference_number="PAY-001",
        supplier_name="Supplier Ltd",
        buyer_name="Buyer Ltd",
        amount=Decimal("10000.00"),
        currency="USD",
    )


def make_po(amount="10000.00"):
    return Evidence(
        evidence_id="PO-001",
        evidence_type="purchase_order",
        reference_number="PO-001",
        supplier_name="Supplier Ltd",
        buyer_name="Buyer Ltd",
        amount=Decimal(amount),
        currency="USD",
    )


def test_full_matching_evidence_is_verified():
    result = compare_invoice_to_evidence_set(make_invoice(), [make_po(), make_payment()])

    assert result["status"] == "verified"
    assert result["verification_score"] == 100.0
    assert result["failed_checks"] == []


def test_matching_purchase_order_without_payment_requires_review_and_is_not_100():
    result = compare_invoice_to_evidence(make_invoice(), make_po())

    assert result["status"] == "review_required"
    assert result["verification_score"] == 80.0
    assert "missing_payment_evidence" in result["failed_checks"]


def test_mismatched_amount_is_lower_than_a_clean_match():
    result = compare_invoice_to_evidence(make_invoice(), make_po("9000.00"))

    assert result["status"] == "review_required"
    assert result["verification_score"] == 65.0
    assert "amount_match" in result["failed_checks"]


def test_missing_evidence_fields_score_zero_and_require_review():
    evidence = Evidence(
        evidence_id="PO-003",
        evidence_type="purchase_order",
        reference_number="PO-003",
    )

    result = compare_invoice_to_evidence(make_invoice(), evidence)

    assert result["status"] == "review_required"
    assert result["verification_score"] == 20.0
    assert len([x for x in result["failed_checks"] if x.startswith("missing_")]) == 1


def test_conflicting_evidence_is_penalized():
    conflicting_payment = Evidence(
        evidence_id="PAY-002",
        evidence_type="payment_record",
        reference_number="PAY-002",
        supplier_name="Supplier Ltd",
        buyer_name="Buyer Ltd",
        amount=Decimal("8000.00"),
        currency="USD",
    )

    result = compare_invoice_to_evidence_set(make_invoice(), [make_po(), conflicting_payment])

    assert result["status"] == "review_required"
    assert result["verification_score"] == 85.0
    assert "amount_match" in result["conflicts"]
