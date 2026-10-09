from app.document_engine import extract_fields


def test_extracts_invoice_and_supporting_evidence_references():
    invoice = extract_fields(
        "Invoice No: INV-2026-0042\nSupplier: Kigali Coffee Cooperative\n"
        "Buyer: Northstar Imports\nCurrency: EUR\nTotal Due: 1250.00\n"
        "Issue Date: 2026-10-01\nDue Date: 2026-11-01"
    )
    assert invoice["invoice_number"] == "INV-2026-0042"
    assert invoice["supplier_name"] == "Kigali Coffee Cooperative"
    assert invoice["buyer_name"] == "Northstar Imports"
    assert invoice["amount"] == 1250.0
    assert invoice["currency"] == "EUR"

    purchase_order = extract_fields("Purchase Order No: PO-2026-101\nSupplier: Example Ltd")
    assert purchase_order["purchase_order_number"] == "PO-2026-101"

    payment = extract_fields("Payment Reference: PAY-778812\nAmount: EUR 1250.00")
    assert payment["reference_number"] == "PAY-778812"
    assert payment["amount"] == 1250.0


def test_extraction_marks_missing_invoice_fields_for_review():
    result = extract_fields("Total Due: USD 10.00")
    assert result["requires_review"] is True
    assert "invoice_number" in result["missing_required_fields"]