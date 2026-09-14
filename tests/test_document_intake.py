from app.document_intake import ingest_text


def test_invoice_intake_extracts_core_fields():
    result = ingest_text("invoice", "Invoice INV-1001 Total: USD 12500.00")
    assert result["fields"]["invoice_number"] == "INV-1001"
    assert result["fields"]["currency"] == "USD"
    assert result["fields"]["amount"] == "12500.00"
    assert len(result["sha256"]) == 64
