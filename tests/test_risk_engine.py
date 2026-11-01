from datetime import date
from decimal import Decimal

from app.models import Invoice
from app.evidence import Evidence
from app.risk_engine import assess


def invoice():
    return Invoice(invoice_number="INV-1", supplier_name="Supplier", buyer_name="Buyer", amount=Decimal("100"), currency="USD", issue_date=date(2026, 1, 1), due_date=date(2026, 2, 1))


def test_clean_transaction_is_approved():
    evidence = [
        Evidence(evidence_id="PO-1", evidence_type="purchase_order", reference_number="PO-1", supplier_name="Supplier", buyer_name="Buyer", amount=Decimal("100"), currency="USD"),
        Evidence(evidence_id="PAY-1", evidence_type="payment_record", reference_number="PAY-1", supplier_name="Supplier", buyer_name="Buyer", amount=Decimal("100"), currency="USD"),
    ]
    result = assess(invoice(), evidence)
    assert result["decision"] == "approve"
    assert result["flags"] == []


def test_duplicate_is_rejected():
    evidence = [Evidence(evidence_id="PO-1", evidence_type="purchase_order", reference_number="PO-1", amount=Decimal("100"), currency="USD")]
    result = assess(invoice(), evidence, duplicate=True)
    assert result["decision"] == "reject"
    assert "duplicate_invoice_number" in result["flags"]


def test_payment_conflict_is_rejected():
    evidence = [Evidence(evidence_id="PAY-1", evidence_type="payment_record", reference_number="PAY-1", amount=Decimal("99"), currency="USD")]
    result = assess(invoice(), evidence)
    assert result["decision"] == "reject"
    assert "payment_amount_or_currency_conflict" in result["flags"]



def test_commercial_evidence_must_match_invoice_parties_and_amount():
    evidence = [
        Evidence(evidence_id="PO-WRONG", evidence_type="purchase_order",
                 reference_number="PO-WRONG", supplier_name="Other Supplier",
                 buyer_name="Buyer", amount=Decimal("100"), currency="USD"),
        Evidence(evidence_id="PAY-OK", evidence_type="payment_record",
                 reference_number="PAY-OK", amount=Decimal("100"), currency="USD"),
    ]
    result = assess(invoice(), evidence)
    assert result["decision"] == "review"
    assert result["commercial_evidence_matches"] == 0
    assert "no_matching_commercial_evidence" in result["flags"]


def test_payment_without_currency_is_not_a_match():
    evidence = [
        Evidence(evidence_id="PO-OK", evidence_type="purchase_order",
                 reference_number="PO-OK", supplier_name="Supplier",
                 buyer_name="Buyer", amount=Decimal("100"), currency="USD"),
        Evidence(evidence_id="PAY-NO-CURRENCY", evidence_type="payment_record",
                 reference_number="PAY-NO-CURRENCY", amount=Decimal("100")),
    ]
    result = assess(invoice(), evidence)
    assert result["decision"] == "review"
    assert result["payment_matches"] == 0
    assert "payment_not_matched" in result["flags"]
