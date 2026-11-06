import os
import uuid

os.environ["DATABASE_URL"] = "sqlite:///./test_production.db"
os.environ["API_KEY_PEPPER"] = "test-pepper"
os.environ["BOOTSTRAP_TOKEN"] = "test-bootstrap"

from fastapi.testclient import TestClient

from app.production_entry import app
from app.production_db import Base, engine

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
# Production middleware expects this Alembic-managed policy table. Keep the
# focused API test database self-contained instead of relying on a local DB.
with engine.begin() as connection:
    connection.exec_driver_sql("""
        CREATE TABLE IF NOT EXISTS api_key_policies (
            key_hash VARCHAR(128) PRIMARY KEY,
            organization_id INTEGER NOT NULL,
            expires_at TIMESTAMP,
            scopes TEXT NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0,
            last_used_at TIMESTAMP
        )
    """)
client = TestClient(app)


def test_production_transaction_round_trip(caplog):
    caplog.set_level("INFO", logger="aft.request")
    suffix = uuid.uuid4().hex[:12]
    invoice_number = f"INV-{suffix}"
    idempotency_key = f"case-{suffix}"
    org_response = client.post(
        "/v1/organizations",
        headers={"X-Bootstrap-Token": "test-bootstrap"},
        json={"name": f"Test Institution {suffix}"},
    )
    assert org_response.status_code == 201
    api_key = org_response.json()["api_key"]

    # Upload validation rejects MIME spoofing and accepts small UTF-8 documents.
    bad_image = client.post(
        "/v1/documents",
        headers={"X-API-Key": api_key},
        files={"file": ("fake.png", b"not-a-png", "image/png")},
    )
    assert bad_image.status_code == 415
    document = client.post(
        "/v1/documents",
        headers={"X-API-Key": api_key},
        files={"file": ("invoice.txt", b"Invoice Number: DOC-1001\\nSupplier: Example Ltd", "text/plain")},
    )
    assert document.status_code == 201
    assert document.json()["duplicate"] is False

    payload = {
        "invoice": {
            "invoice_number": invoice_number,
            "supplier_name": "Supplier Ltd",
            "buyer_name": "Buyer Ltd",
            "amount": "12500.00",
            "currency": "USD",
            "issue_date": "2026-09-14",
            "due_date": "2026-10-14",
        },
        "evidence": [
            {
                "evidence_id": f"PO-{suffix}",
                "evidence_type": "purchase_order",
                "reference_number": f"PO-{suffix}",
                "supplier_name": "Supplier Ltd",
                "buyer_name": "Buyer Ltd",
                "amount": "12500.00",
                "currency": "USD",
                "evidence_date": "2026-09-14",
                "description": "Purchase order",
            },
            {
                "evidence_id": f"PAY-{suffix}",
                "evidence_type": "payment_record",
                "reference_number": f"PAY-{suffix}",
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
        headers={"X-API-Key": api_key, "Idempotency-Key": idempotency_key},
        json=payload,
    )
    assert response.status_code == 201
    result = response.json()
    assert result["status"] == "verified"
    assert result["verification"]["verification_score"] == 100.0
    assert result["audit_hash"]

    # The independent audit verifier must reproduce the exact persisted hash.
    chain = client.get("/v1/bank-grade/audits/verify-chain", headers={"X-API-Key": api_key})
    assert chain.status_code == 200
    assert chain.json()["valid"] is True

    trust_record = client.get(
        f"/v1/transactions/{result['transaction_id']}/trust-record",
        headers={"X-API-Key": api_key},
    )
    assert trust_record.status_code == 200
    assert "attachment;" in trust_record.headers["content-disposition"]
    assert trust_record.json()["record_type"] == "african_financial_trust.trust_record"
    assert trust_record.json()["record_version"] == "1.0"
    assert trust_record.json()["audit"]["event_hash"] == result["audit_hash"]

    share = client.post(
        f"/v1/transactions/{result['transaction_id']}/share-links",
        headers={"X-API-Key": api_key},
        json={"expires_in_hours": 2},
    )
    assert share.status_code == 201
    share_path = share.json()["share_path"]
    shared_record = client.get(share_path)
    assert shared_record.status_code == 200
    assert any(
        getattr(record, "http_path", None) == "/v1/shared/trust-records/{token}"
        for record in caplog.records
    )
    assert shared_record.json()["transaction_id"] == result["transaction_id"]
    share_list = client.get(
        f"/v1/transactions/{result['transaction_id']}/share-links",
        headers={"X-API-Key": api_key},
    )
    assert share_list.status_code == 200
    share_id = share.json()["share_id"]
    revoked = client.post(
        f"/v1/transactions/{result['transaction_id']}/share-links/{share_id}/revoke",
        headers={"X-API-Key": api_key},
    )
    assert revoked.status_code == 200
    assert client.get(share_path).status_code == 404

    # A customer-submitted record must never be able to self-declare as
    # independently verified, even if it supplies plausible provenance text.
    source = client.post(
        "/v1/sources/records",
        headers={"X-API-Key": api_key},
        json={
            "provider": "example-bank",
            "provider_record_id": f"bank-{suffix}",
            "reference": invoice_number,
            "amount": "12500.00",
            "currency": "USD",
            "authority": "independently_verified",
            "provenance": {"verification": "provider_direct_query"},
            "payload": {"amount": "12500.00", "currency": "USD"},
        },
    )
    assert source.status_code == 201
    assert source.json()["authority"] == "unverified"

    # First admin scope must be provisioned with the deployment bootstrap secret.
    key_list = client.get("/v1/keys", headers={"X-API-Key": api_key})
    assert key_list.status_code == 200
    key_id = key_list.json()["keys"][0]["id"]
    denied = client.post(
        f"/v1/bank-grade/controls/bootstrap/{key_id}",
        headers={"X-Bootstrap-Token": "wrong-token"},
    )
    assert denied.status_code == 403
    provisioned = client.post(
        f"/v1/bank-grade/controls/bootstrap/{key_id}",
        headers={"X-Bootstrap-Token": "test-bootstrap"},
    )
    assert provisioned.status_code == 200
    assert "bank-grade:admin" in provisioned.json()["scopes"]

    repeat = client.post(
        "/v1/transactions",
        headers={"X-API-Key": api_key, "Idempotency-Key": idempotency_key},
        json=payload,
    )
    assert repeat.status_code == 200
    assert repeat.json()["transaction_id"] == result["transaction_id"]

    changed_payload = {
        **payload,
        "invoice": {**payload["invoice"], "amount": "13000.00"},
    }
    conflict = client.post(
        "/v1/transactions",
        headers={"X-API-Key": api_key, "Idempotency-Key": idempotency_key},
        json=changed_payload,
    )
    assert conflict.status_code == 409
