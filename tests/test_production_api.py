import os

os.environ["DATABASE_URL"] = "sqlite:///./test_production.db"
os.environ["API_KEY_PEPPER"] = "test-pepper"
os.environ["BOOTSTRAP_TOKEN"] = "test-bootstrap"

from fastapi.testclient import TestClient

from app.production_entry import app
from app.production_db import Base, engine

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
client = TestClient(app)


def test_production_transaction_round_trip():
    org_response = client.post(
        "/v1/organizations",
        headers={"X-Bootstrap-Token": "test-bootstrap"},
        json={"name": "Test Institution"},
    )
    assert org_response.status_code == 201
    api_key = org_response.json()["api_key"]

    payload = {
        "invoice": {
            "invoice_number": "INV-1001",
            "supplier_name": "Supplier Ltd",
            "buyer_name": "Buyer Ltd",
            "amount": "12500.00",
            "currency": "USD",
            "issue_date": "2026-09-14",
            "due_date": "2026-10-14",
        },
        "evidence": [
            {
                "evidence_id": "PO-1001",
                "evidence_type": "purchase_order",
                "reference_number": "PO-1001",
                "supplier_name": "Supplier Ltd",
                "buyer_name": "Buyer Ltd",
                "amount": "12500.00",
                "currency": "USD",
                "evidence_date": "2026-09-14",
                "description": "Purchase order",
            },
            {
                "evidence_id": "PAY-1001",
                "evidence_type": "payment_record",
                "reference_number": "PAY-1001",
                "supplier_name": "Supplier Ltd",
                "buyer_name": "Buyer Ltd",
                "amount": "12500.00",
                "currency": "USD",
                "evidence_date": "2026-09-14",
                "description": "Payment record",
            },
        ],
    }
    response = client.post(
        "/v1/transactions",
        headers={"X-API-Key": api_key, "Idempotency-Key": "case-1001"},
        json=payload,
    )
    assert response.status_code == 201
    result = response.json()
    assert result["status"] == "verified"
    assert result["verification"]["verification_score"] == 100.0
    assert result["audit_hash"]

    repeat = client.post(
        "/v1/transactions",
        headers={"X-API-Key": api_key, "Idempotency-Key": "case-1001"},
        json=payload,
    )
    assert repeat.status_code == 200
    assert repeat.json()["transaction_id"] == result["transaction_id"]
