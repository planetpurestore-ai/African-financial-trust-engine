from fastapi.testclient import TestClient

from app.main import APP_VERSION, app


client = TestClient(app)


def _invoice(invoice_number="API-INV-001"):
    return {
        "invoice_number": invoice_number,
        "supplier_name": "Supplier Ltd",
        "buyer_name": "Buyer Ltd",
        "amount": "10000.00",
        "currency": "USD",
        "issue_date": "2026-01-10",
        "due_date": "2026-02-10",
    }


def _evidence(evidence_id="API-PO-001", amount="10000.00", **overrides):
    return {
        "evidence_id": evidence_id,
        "evidence_type": "purchase_order",
        "reference_number": evidence_id,
        "supplier_name": "Supplier Ltd",
        "buyer_name": "Buyer Ltd",
        "amount": amount,
        "currency": "USD",
        **overrides,
    }


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "trust-engine"
    assert body["version"] == APP_VERSION
    assert body["database"] == "ok"


def test_verify_endpoint_returns_explainable_result():
    response = client.post(
        "/verify",
        json={
            "invoice": _invoice(),
            "evidence": _evidence(
                supplier_name=" supplier ltd ",
                buyer_name="BUYER LTD",
                currency="usd",
            ),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "verified"
    verification = body["verification"]
    assert verification["status"] == "verified"
    assert verification["verification_score"] == 100.0


def test_verify_endpoint_rejects_invalid_invoice_dates():
    payload = {
        "invoice": {**_invoice("API-INV-002"), "issue_date": "2026-02-10", "due_date": "2026-01-10"},
        "evidence": _evidence("API-PO-002"),
    }
    response = client.post("/verify", json=payload)
    assert response.status_code == 422


def test_invoice_and_evidence_can_be_stored_and_verified():
    invoice_number = "API-CRUD-001"
    evidence_id = "API-CRUD-PO-001"

    assert client.post("/invoices", json=_invoice(invoice_number)).status_code == 201
    assert client.post("/evidence", json=_evidence(evidence_id)).status_code == 201
    assert client.get(f"/invoices/{invoice_number}").status_code == 200
    assert client.get(f"/evidence/{evidence_id}").status_code == 200

    verification = client.post(f"/verify-stored/{invoice_number}/{evidence_id}")
    assert verification.status_code == 200
    assert verification.json()["decision"] == "verified"

    summary = client.post(f"/verification-summary/{invoice_number}/{evidence_id}")
    assert summary.status_code == 200
    assert summary.json()["decision"] == "verified"
    assert summary.json()["verification_score"] == 100.0


def test_missing_stored_records_return_404():
    assert client.get("/invoices/DOES-NOT-EXIST").status_code == 404
    assert client.get("/evidence/DOES-NOT-EXIST").status_code == 404
    assert client.post("/verify-stored/DOES-NOT-EXIST/NO-EVIDENCE").status_code == 404
    assert client.post("/verification-summary/DOES-NOT-EXIST/NO-EVIDENCE").status_code == 404


def test_mismatched_stored_evidence_requires_review():
    invoice_number = "API-REVIEW-001"
    evidence_id = "API-REVIEW-PO-001"

    assert client.post("/invoices", json=_invoice(invoice_number)).status_code == 201
    assert client.post("/evidence", json=_evidence(evidence_id, amount="9000.00")).status_code == 201

    response = client.post(f"/verification-summary/{invoice_number}/{evidence_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "review_required"
    assert body["verification_score"] == 75.0
    assert "amount_match" in body["failed_checks"]


def test_batch_verification_can_combine_multiple_evidence_records():
    payload = {
        "invoice": _invoice("API-BATCH-001"),
        "evidence": [
            _evidence("API-BATCH-CONTRACT", amount=None, evidence_type="contract"),
            _evidence("API-BATCH-PAYMENT", amount="10000.00", evidence_type="payment_record"),
        ],
    }

    response = client.post("/verify-batch", json=payload)
    assert response.status_code == 200
    body = response.json()
    verification = body["verification"]

    assert body["decision"] == "verified"
    assert verification["status"] == "verified"
    assert verification["verification_score"] == 100.0
    assert verification["evidence_count"] == 2
    assert set(verification["supporting_evidence"]["amount_match"]) == {"API-BATCH-PAYMENT"}


def test_batch_conflict_requires_review_even_when_all_checks_have_a_match():
    payload = {
        "invoice": _invoice("API-BATCH-CONFLICT"),
        "evidence": [
            _evidence("API-CONFLICT-LOW", amount="9000.00"),
            _evidence("API-CONFLICT-CORRECT", amount="10000.00"),
        ],
    }

    response = client.post("/verify-batch", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "review_required"
    assert body["verification"]["status"] == "review_required"
    assert body["verification"]["verification_score"] == 100.0
    assert body["verification"]["conflicts"] == ["amount_match"]


def test_batch_verification_requires_at_least_one_evidence_record():
    response = client.post("/verify-batch", json={"invoice": _invoice("API-BATCH-EMPTY"), "evidence": []})
    assert response.status_code == 422


def test_batch_verification_rejects_more_than_100_evidence_records():
    evidence = [_evidence(f"API-MANY-{i}") for i in range(101)]
    response = client.post("/verify-batch", json={"invoice": _invoice("API-BATCH-LIMIT"), "evidence": evidence})
    assert response.status_code == 422
