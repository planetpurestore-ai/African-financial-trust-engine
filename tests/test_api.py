from fastapi.testclient import TestClient

from app.main import APP_VERSION, app

client = TestClient(app)


def _invoice(invoice_number="API-INV-001"):
    return {"invoice_number": invoice_number, "supplier_name": "Supplier Ltd", "buyer_name": "Buyer Ltd",
            "amount": "10000.00", "currency": "USD", "issue_date": "2026-01-10", "due_date": "2026-02-10"}


def _evidence(evidence_id="API-PO-001", amount="10000.00", **overrides):
    return {"evidence_id": evidence_id, "evidence_type": "purchase_order", "reference_number": evidence_id,
            "supplier_name": "Supplier Ltd", "buyer_name": "Buyer Ltd", "amount": amount, "currency": "USD", **overrides}


def test_health_endpoint():
    body = client.get("/health").json()
    assert body == {"status": "ok", "service": "trust-engine", "version": APP_VERSION, "database": "ok"}


def test_verify_endpoint_returns_explainable_result_and_audit_id():
    response = client.post("/verify", json={"invoice": _invoice(), "evidence": _evidence(
        supplier_name=" supplier ltd ", buyer_name="BUYER LTD", currency="usd")})
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "verified"
    assert isinstance(body["audit_id"], int)
    assert body["verification"]["verification_score"] == 100.0


def test_verify_endpoint_rejects_invalid_invoice_dates():
    payload = {"invoice": {**_invoice("API-INV-002"), "issue_date": "2026-02-10", "due_date": "2026-01-10"},
               "evidence": _evidence("API-PO-002")}
    assert client.post("/verify", json=payload).status_code == 422


def test_invoice_and_evidence_can_be_stored_and_verified():
    invoice_number, evidence_id = "API-CRUD-001", "API-CRUD-PO-001"
    assert client.post("/invoices", json=_invoice(invoice_number)).status_code == 201
    assert client.post("/evidence", json=_evidence(evidence_id)).status_code == 201
    assert client.get(f"/invoices/{invoice_number}").status_code == 200
    assert client.get(f"/evidence/{evidence_id}").status_code == 200
    verification = client.post(f"/verify-stored/{invoice_number}/{evidence_id}")
    assert verification.status_code == 200
    assert verification.json()["decision"] == "verified"
    assert client.post(f"/verification-summary/{invoice_number}/{evidence_id}").json()["verification_score"] == 100.0


def test_missing_stored_records_return_404():
    assert client.get("/invoices/DOES-NOT-EXIST").status_code == 404
    assert client.get("/evidence/DOES-NOT-EXIST").status_code == 404
    assert client.post("/verify-stored/DOES-NOT-EXIST/NO-EVIDENCE").status_code == 404
    assert client.post("/verification-summary/DOES-NOT-EXIST/NO-EVIDENCE").status_code == 404


def test_mismatched_stored_evidence_requires_review():
    invoice_number, evidence_id = "API-REVIEW-001", "API-REVIEW-PO-001"
    client.post("/invoices", json=_invoice(invoice_number))
    client.post("/evidence", json=_evidence(evidence_id, amount="9000.00"))
    body = client.post(f"/verification-summary/{invoice_number}/{evidence_id}").json()
    assert body["decision"] == "review_required"
    assert body["verification_score"] == 75.0
    assert "amount_match" in body["failed_checks"]


def test_batch_verification_and_conflict_detection():
    payload = {"invoice": _invoice("API-BATCH-001"), "evidence": [
        _evidence("API-BATCH-CONTRACT", amount=None, evidence_type="contract"),
        _evidence("API-BATCH-PAYMENT", amount="10000.00", evidence_type="payment_record")],}
    body = client.post("/verify-batch", json=payload).json()
    assert body["decision"] == "verified"
    assert body["verification"]["evidence_count"] == 2
    assert body["verification"]["supporting_evidence"]["amount_match"] == ["API-BATCH-PAYMENT"]

    conflict = {"invoice": _invoice("API-BATCH-CONFLICT"), "evidence": [
        _evidence("API-CONFLICT-LOW", amount="9000.00"), _evidence("API-CONFLICT-CORRECT", amount="10000.00")],}
    body = client.post("/verify-batch", json=conflict).json()
    assert body["decision"] == "review_required"
    assert body["verification"]["conflicts"] == ["amount_match"]


def test_audit_history_records_verification():
    invoice_number = "API-AUDIT-001"
    response = client.post("/verify", json={"invoice": _invoice(invoice_number), "evidence": _evidence("API-AUDIT-PO")})
    audit_id = response.json()["audit_id"]
    history = client.get(f"/audits/{invoice_number}")
    assert history.status_code == 200
    body = history.json()
    assert body["count"] >= 1
    assert body["audits"][0]["audit_id"] == audit_id
    assert body["audits"][0]["decision"] == "verified"


def test_audit_history_honors_limit():
    invoice_number = "API-AUDIT-LIMIT"
    for index in range(3):
        client.post("/verify", json={"invoice": _invoice(invoice_number), "evidence": _evidence(f"API-AUDIT-{index}")})
    response = client.get(f"/audits/{invoice_number}?limit=2")
    assert response.status_code == 200
    assert response.json()["count"] == 2


def test_batch_verification_rejects_duplicate_evidence_ids():
    payload = {"invoice": _invoice("API-BATCH-DUPLICATE"), "evidence": [
        _evidence("API-DUPLICATE"), _evidence("API-DUPLICATE")]}
    assert client.post("/verify-batch", json=payload).status_code == 422


def test_incomplete_single_evidence_requires_review():
    body = client.post("/verify", json={
        "invoice": _invoice("API-INCOMPLETE"),
        "evidence": _evidence("API-INCOMPLETE-PO", amount=None, currency=None, supplier_name=None, buyer_name=None),
    }).json()
    assert body["decision"] == "review_required"
    assert body["verification"]["verification_score"] == 0.0
    assert set(body["verification"]["incomplete_checks"]) == set(("supplier_match", "buyer_match", "amount_match", "currency_match"))


def test_batch_verification_limits():
    assert client.post("/verify-batch", json={"invoice": _invoice("API-BATCH-EMPTY"), "evidence": []}).status_code == 422
    evidence = [_evidence(f"API-MANY-{i}") for i in range(101)]
    assert client.post("/verify-batch", json={"invoice": _invoice("API-BATCH-LIMIT"), "evidence": evidence}).status_code == 422


def test_audit_history_limit_validation():
    assert client.get("/audits/API-AUDIT-VALIDATION?limit=0").status_code == 422
    assert client.get("/audits/API-AUDIT-VALIDATION?limit=101").status_code == 422
