from datetime import date

from app.document_engine import extract_fields
from app.evidence import Evidence
from app.models import Invoice
from app.verification import compare_invoice_to_evidence_set
from app.risk_engine import assess


def invoice():
    return Invoice(
        invoice_number="ASSURANCE-001",
        supplier_name="Supplier Ltd",
        buyer_name="Buyer Ltd",
        amount=1500,
        currency="USD",
        issue_date=date(2026, 9, 15),
        due_date=date(2026, 10, 15),
    )


def evidence():
    return [
        Evidence(evidence_id="PO-1", evidence_type="purchase_order", reference_number="PO-1", supplier_name="Supplier Ltd", buyer_name="Buyer Ltd", amount=1500, currency="USD", evidence_date=date(2026, 9, 15)),
        Evidence(evidence_id="PAY-1", evidence_type="payment_record", reference_number="PAY-1", supplier_name="Supplier Ltd", buyer_name="Buyer Ltd", amount=1500, currency="USD", evidence_date=date(2026, 9, 15)),
        Evidence(evidence_id="CON-1", evidence_type="contract", reference_number="CON-1", supplier_name="Supplier Ltd", buyer_name="Buyer Ltd", evidence_date=date(2026, 9, 15)),
    ]


def test_full_evidence_package_verifies():
    result = compare_invoice_to_evidence_set(invoice(), evidence())
    assert result["status"] == "verified"
    assert result["verification_score"] == 100.0
    assert result["failed_checks"] == []


def test_conflicting_amount_is_not_verified():
    items = evidence()
    items[0].amount = 1200
    result = compare_invoice_to_evidence_set(invoice(), items)
    assert result["status"] != "verified"
    assert "amount_match" in result["failed_checks"] or "amount_match:conflict" in result["failed_checks"]


def test_missing_payment_does_not_claim_truth():
    items = [e for e in evidence() if e.evidence_type != "payment_record"]
    result = compare_invoice_to_evidence_set(invoice(), items)
    risk = assess(invoice(), items, duplicate=False)
    assert result["verification_score"] == 100.0
    assert risk["decision"] in {"review", "approve", "reject"}
    assert risk["decision"] != "approve"


def test_document_extraction_is_explicitly_field_based():
    text = "Invoice Number: INV-9\nSupplier: Supplier Ltd\nBuyer: Buyer Ltd\nCurrency: USD\nAmount: 1500.00\nIssue Date: 15 September 2026\nDue Date: 15 October 2026"
    result = extract_fields(text)
    assert result["fields"]["invoice_number"] == "INV-9"
    assert result["fields"]["supplier_name"] == "Supplier Ltd"
    assert result["fields"]["buyer_name"] == "Buyer Ltd"
    assert result["fields"]["currency"] == "USD"
    assert result["fields"]["amount"] == 1500.0
    assert result["fields"]["issue_date"] == "2026-09-15"
    assert result["fields"]["due_date"] == "2026-10-15"
    assert "confidence" in result
