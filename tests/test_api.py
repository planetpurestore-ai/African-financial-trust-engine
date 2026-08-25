from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.database import DATABASE_PATH


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_verify_endpoint_returns_explainable_result():
    payload = {
        "invoice": {
            "invoice_number": "API-INV-001",
            "supplier_name": "Supplier Ltd",
            "buyer_name": "Buyer Ltd",
            "amount": "10000.00",
            "currency": "usd",
            "issue_date": "2026-01-10",
            "due_date": "2026-02-10"
        },
        "evidence": {
            "evidence_id": "API-PO-001",
            "evidence_type": "purchase_order",
            "reference_number": "API-PO-001",
            "supplier_name": " supplier ltd ",
            "buyer_name": "BUYER LTD",
            "amount": "10000.00",
            "currency": "USD"
        }
    }

    response = client.post("/verify", json=payload)
    assert response.status_code == 200
    verification = response.json()["verification"]
    assert verification["status"] == "verified"
    assert verification["verification_score"] == 100.0


def test_verify_endpoint_rejects_invalid_invoice_dates():
    payload = {
        "invoice": {
            "invoice_number": "API-INV-002",
            "supplier_name": "Supplier Ltd",
            "buyer_name": "Buyer Ltd",
            "amount": "10000.00",
            "currency": "USD",
            "issue_date": "2026-02-10",
            "due_date": "2026-01-10"
        },
        "evidence": {
            "evidence_id": "API-PO-002",
            "evidence_type": "purchase_order",
            "reference_number": "API-PO-002"
        }
    }

    response = client.post("/verify", json=payload)
    assert response.status_code == 422
