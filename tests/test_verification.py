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
    assert result["verification_score"] == 0.0
    assert {"missing_commercial_evidence", "missing_payment_evidence"}.issubset(set(result["failed_checks"]))


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
    assert result["verification_score"] == 70.0
    assert "amount_match" in result["conflicts"]


def test_delivery_note_is_reported_as_delivery_evidence_not_payment():
    delivery = Evidence(
        evidence_id="DEL-001",
        evidence_type="delivery_note",
        reference_number="DEL-001",
        supplier_name="Supplier Ltd",
        buyer_name="Buyer Ltd",
        amount=Decimal("10000.00"),
        currency="USD",
        evidence_date=date(2026, 1, 12),
    )
    result = compare_invoice_to_evidence_set(
        make_invoice(),
        [make_po(), delivery],
        policy={"require_commercial_evidence": True, "require_payment_evidence": False},
    )
    assert result["delivery_evidence_present"] is True
    assert result["payment_evidence_present"] is False


def test_declared_purchase_order_reference_must_match_evidence():
    invoice = Invoice(**make_invoice().model_dump(), purchase_order_number="PO-001")
    result = compare_invoice_to_evidence_set(invoice, [make_po(), make_payment()])
    assert result["status"] == "verified"
    assert result["reference_checks"]["purchase_order_number"]["matched"] is True
    assert result["supporting_evidence"]["purchase_order_number_match"] == ["PO-001"]


def test_declared_purchase_order_reference_mismatch_requires_review():
    invoice = Invoice(**make_invoice().model_dump(), purchase_order_number="PO-EXPECTED")
    result = compare_invoice_to_evidence_set(invoice, [make_po(), make_payment()])
    assert result["status"] == "review_required"
    assert result["verification_score"] == 90.0
    assert "purchase_order_number_match" in result["failed_checks"]


def test_contract_and_delivery_references_are_matched_to_their_own_evidence_types():
    invoice = Invoice(
        **make_invoice().model_dump(),
        contract_reference="CON-100",
        delivery_reference="DEL-100",
    )
    contract = Evidence(
        evidence_id="CON-EVIDENCE",
        evidence_type="contract",
        reference_number="CON-100",
        supplier_name="Supplier Ltd",
        buyer_name="Buyer Ltd",
        amount=Decimal("10000.00"),
        currency="USD",
    )
    delivery = Evidence(
        evidence_id="DEL-EVIDENCE",
        evidence_type="delivery_note",
        reference_number="DEL-100",
        supplier_name="Supplier Ltd",
        buyer_name="Buyer Ltd",
        amount=Decimal("10000.00"),
        currency="USD",
        evidence_date=date(2026, 1, 12),
    )
    result = compare_invoice_to_evidence_set(invoice, [make_po(), make_payment(), contract, delivery])
    assert result["status"] == "verified"
    assert result["reference_checks"]["contract_reference"]["matched"] is True
    assert result["reference_checks"]["delivery_reference"]["matched"] is True
