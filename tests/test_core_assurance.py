from datetime import date

from app.document_engine import extract_fields, inspect_document_integrity
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
    assert result["verification_score"] == 80.0
    assert risk["decision"] in {"review", "approve", "reject"}
    assert risk["decision"] != "approve"


def test_document_extraction_is_explicitly_field_based():
    text = "Invoice Number: INV-9\nSupplier: Supplier Ltd\nBuyer: Buyer Ltd\nCurrency: USD\nSubtotal: 1200.00\nTax Amount: 300.00\nAmount: 1500.00\nIssue Date: 15 September 2026\nDue Date: 15 October 2026"
    result = extract_fields(text)
    assert result["fields"]["invoice_number"] == "INV-9"
    assert result["fields"]["supplier_name"] == "Supplier Ltd"
    assert result["fields"]["buyer_name"] == "Buyer Ltd"
    assert result["fields"]["currency"] == "USD"
    assert result["fields"]["amount"] == "1500.00"
    assert result["fields"]["subtotal"] == "1200.00"
    assert result["fields"]["tax_amount"] == "300.00"
    assert result["fields"]["issue_date"] == "2026-09-15"
    assert result["fields"]["due_date"] == "2026-10-15"
    assert "confidence" in result


def test_document_extraction_flags_subtotal_tax_mismatch():
    text = """Invoice Number: INV-10
Supplier: Supplier Ltd
Buyer: Buyer Ltd
Currency: USD
Subtotal: 1200.00
Tax Amount: 250.00
Amount: 1500.00
Issue Date: 15 September 2026"""
    result = extract_fields(text)
    assert result["arithmetic_consistent"] is False
    assert result["requires_review"] is True
    assert "subtotal_tax_total_mismatch" in result["review_reasons"]


def test_pdf_integrity_signals_are_not_authenticity_proof():
    result = inspect_document_integrity(
        b"%PDF-1.4\\n/JavaScript (alert)\\n/EmbeddedFiles\\n%%EOF",
        "application/pdf",
    )
    assert result["status"] == "review"
    assert "pdf_embedded_script" in result["signals"]
    assert "pdf_embedded_files" in result["signals"]
    assert result["is_authenticity_proof"] is False


def test_text_integrity_flags_bidirectional_override_controls():
    result = inspect_document_integrity(
        "Invoice: INV-1 " + chr(0x202E),
        "text/plain",
    )
    assert "text_contains_bidirectional_override_controls" in result["signals"]
