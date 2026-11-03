from datetime import date
from decimal import Decimal

from app.evidence import Evidence
from app.models import Invoice
from app.risk_engine import assess
from app.verification import compare_invoice_to_evidence_set


def make_invoice():
    return Invoice(
        invoice_number="ASSURE-2026-001",
        supplier_name="Kigali Coffee Cooperative",
        buyer_name="Northstar Imports",
        amount=Decimal("1250.00"),
        currency="EUR",
        issue_date=date(2026, 10, 1),
        due_date=date(2026, 11, 1),
    )


def make_evidence(evidence_id, evidence_type, *, supplier="Kigali Coffee Cooperative",
                  buyer="Northstar Imports", amount="1250.00", currency="EUR"):
    return Evidence(
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        reference_number=evidence_id,
        supplier_name=supplier,
        buyer_name=buyer,
        amount=Decimal(amount) if amount is not None else None,
        currency=currency,
        evidence_date=date(2026, 10, 1),
    )


def full_package():
    return [
        make_evidence("PO-001", "purchase_order"),
        make_evidence("CON-001", "contract", amount=None, currency=None),
        make_evidence("PAY-001", "payment_record"),
    ]


def test_full_consistent_package_is_verified_with_explainable_checks():
    result = compare_invoice_to_evidence_set(make_invoice(), full_package())
    assert result["status"] == "verified"
    assert result["failed_checks"] == []
    assert result["verification_score"] == 100.0
    assert result["commercial_evidence_present"] is True
    assert result["payment_evidence_present"] is True


def test_amount_conflict_forces_review_and_is_named():
    evidence = full_package()
    evidence.append(make_evidence("PAY-002", "payment_record", amount="900.00"))
    result = compare_invoice_to_evidence_set(make_invoice(), evidence)
    assert result["status"] == "review_required"
    assert "amount_match" in result["conflicts"]
    assert result["verification_score"] < 100


def test_missing_payment_never_verifies():
    evidence = [e for e in full_package() if e.evidence_type != "payment_record"]
    result = compare_invoice_to_evidence_set(make_invoice(), evidence)
    assert result["status"] != "verified"
    assert result["payment_evidence_present"] is False
    assert "missing_payment_evidence" in result["failed_checks"]


def test_missing_commercial_evidence_never_verifies():
    evidence = [make_evidence("PAY-001", "payment_record")]
    result = compare_invoice_to_evidence_set(make_invoice(), evidence)
    assert result["status"] != "verified"
    assert result["commercial_evidence_present"] is False
    assert "missing_commercial_evidence" in result["failed_checks"]


def test_counterparty_conflict_forces_review():
    evidence = full_package()
    evidence.append(make_evidence("PO-002", "purchase_order", supplier="Different Supplier Ltd"))
    result = compare_invoice_to_evidence_set(make_invoice(), evidence)
    assert result["status"] == "review_required"
    assert "supplier_match" in result["conflicts"]


def test_risk_engine_does_not_approve_missing_payment():
    evidence = [make_evidence("PO-001", "purchase_order")]
    result = assess(make_invoice(), evidence)
    assert result["decision"] == "review"
    assert "payment_not_verified" in result["flags"]


def test_duplicate_invoice_number_is_a_hard_rejection_signal():
    result = assess(make_invoice(), full_package(), duplicate=True)
    assert result["decision"] == "reject"
    assert "duplicate_invoice_number" in result["flags"]
