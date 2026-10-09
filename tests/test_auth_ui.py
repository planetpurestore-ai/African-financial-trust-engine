import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.auth_ui as auth_ui
from app.production_db import Base
from app.production_entry import app


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[auth_ui.db_session] = override_db
    monkeypatch.setenv("BOOTSTRAP_TOKEN", "test-bootstrap-token-long-enough")
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_bootstrap_login_me_and_logout(client):
    created = client.post(
        "/v1/auth/bootstrap",
        headers={"X-Bootstrap-Token": "test-bootstrap-token-long-enough"},
        json={
            "full_name": "Test Admin",
            "email": "admin@example.com",
            "password": "a-long-test-password-123",
            "organization_name": "Example Institution",
        },
    )
    assert created.status_code == 201
    assert created.json()["user"]["full_name"] == "Test Admin"
    assert created.json()["user"]["organization_name"] == "Example Institution"
    assert "aft_session" in client.cookies

    me = client.get("/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "admin@example.com"

    client.post("/v1/auth/logout")
    assert client.get("/v1/auth/me").status_code == 401

    login = client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "a-long-test-password-123"},
    )
    assert login.status_code == 200
    assert client.get("/v1/auth/me").status_code == 200


def test_bootstrap_requires_token_and_only_runs_once(client):
    payload = {
        "full_name": "Test Admin",
        "email": "admin@example.com",
        "password": "a-long-test-password-123",
        "organization_name": "Example Institution",
    }
    assert client.post("/v1/auth/bootstrap", json=payload).status_code == 403
    headers = {"X-Bootstrap-Token": "test-bootstrap-token-long-enough"}
    assert client.post("/v1/auth/bootstrap", headers=headers, json=payload).status_code == 201
    assert client.post(
        "/v1/auth/bootstrap",
        headers=headers,
        json={**payload, "email": "second@example.com"},
    ).status_code == 409


def test_dashboard_requires_session(client):
    assert client.get("/v1/ui/dashboard").status_code == 401
    client.post(
        "/v1/auth/bootstrap",
        headers={"X-Bootstrap-Token": "test-bootstrap-token-long-enough"},
        json={
            "full_name": "Test Admin",
            "email": "admin@example.com",
            "password": "a-long-test-password-123",
            "organization_name": "Example Institution",
        },
    )
    response = client.get("/v1/ui/dashboard")
    assert response.status_code == 200
    assert response.json()["metrics"]["total"] == 0



def test_additional_organizations_have_separate_admin_context(client):
    headers = {"X-Bootstrap-Token": "test-bootstrap-token-long-enough"}
    first = client.post(
        "/v1/auth/bootstrap",
        headers=headers,
        json={
            "full_name": "First Admin",
            "email": "first@example.com",
            "password": "a-long-test-password-123",
            "organization_name": "First Institution",
        },
    )
    assert first.status_code == 201
    second = client.post(
        "/v1/auth/organizations",
        headers=headers,
        json={
            "full_name": "Second Admin",
            "email": "second@example.com",
            "password": "another-long-password-456",
            "organization_name": "Second Institution",
        },
    )
    assert second.status_code == 201
    assert second.json()["organization"]["id"] != first.json()["user"]["organization_id"]

    client.post("/v1/auth/logout")
    signed_in = client.post(
        "/v1/auth/login",
        json={"email": "second@example.com", "password": "another-long-password-456"},
    )
    assert signed_in.status_code == 200
    assert client.get("/v1/auth/me").json()["user"]["organization_name"] == "Second Institution"
    assert client.get("/v1/ui/dashboard").json()["metrics"]["total"] == 0

    client.post("/v1/auth/logout")
    client.post(
        "/v1/auth/login",
        json={"email": "first@example.com", "password": "a-long-test-password-123"},
    )
    assert client.get("/v1/auth/me").json()["user"]["organization_name"] == "First Institution"



def test_bootstrap_rejects_invalid_email(client):
    response = client.post(
        "/v1/auth/bootstrap",
        headers={"X-Bootstrap-Token": "test-bootstrap-token-long-enough"},
        json={
            "full_name": "Test Admin",
            "email": "not-an-email",
            "password": "a-long-test-password-123",
            "organization_name": "Example Institution",
        },
    )
    assert response.status_code == 422
    assert client.get("/v1/auth/me").status_code == 401


def test_bootstrap_rejects_duplicate_email_case_insensitively(client):
    headers = {"X-Bootstrap-Token": "test-bootstrap-token-long-enough"}
    payload = {
        "full_name": "Test Admin",
        "email": "admin@example.com",
        "password": "a-long-test-password-123",
        "organization_name": "Example Institution",
    }
    assert client.post("/v1/auth/bootstrap", headers=headers, json=payload).status_code == 201
    duplicate = client.post(
        "/v1/auth/organizations",
        headers=headers,
        json={**payload, "email": "ADMIN@example.com", "organization_name": "Second Institution"},
    )
    assert duplicate.status_code == 409



def test_authenticated_transaction_submission_and_audit_chain(client):
    headers = {"X-Bootstrap-Token": "test-bootstrap-token-long-enough"}
    first = client.post(
        "/v1/auth/bootstrap",
        headers=headers,
        json={
            "full_name": "First Admin",
            "email": "first@example.com",
            "password": "a-long-test-password-123",
            "organization_name": "First Institution",
        },
    )
    assert first.status_code == 201
    payload = {
        "invoice": {
            "invoice_number": "INV-MVP-1001",
            "supplier_name": "Kigali Coffee Cooperative",
            "buyer_name": "Northstar Imports",
            "amount": "1250.00",
            "currency": "EUR",
            "issue_date": "2026-10-01",
            "due_date": "2026-11-01",
        },
        "evidence": [{
            "evidence_id": "PO-MVP-1001",
            "evidence_type": "purchase_order",
            "reference_number": "PO-MVP-1001",
            "supplier_name": "Kigali Coffee Cooperative",
            "buyer_name": "Northstar Imports",
            "amount": "1250.00",
            "currency": "EUR",
            "evidence_date": "2026-10-01",
        }],
    }
    created = client.post("/v1/ui/transactions", json=payload, headers={"Idempotency-Key": "test-mvp-1001"})
    assert created.status_code == 201
    body = created.json()
    assert body["invoice_number"] == "INV-MVP-1001"
    assert body["status"] in {"verified", "review_required", "rejected"}
    assert body["audit_id"] is not None
    assert body["audit_hash"]
    assert body["verification"] is not None
    detail = client.get("/v1/ui/transactions/" + body["transaction_id"])
    assert detail.status_code == 200
    assert detail.json()["invoice"]["invoice_number"] == "INV-MVP-1001"
    assert detail.json()["audit"]["event_hash"] == body["audit_hash"]
    chain = client.get("/v1/ui/audits/verify-chain")
    assert chain.status_code == 200
    assert chain.json()["valid"] is True
    dashboard = client.get("/v1/ui/dashboard").json()
    assert dashboard["metrics"]["total"] == 1
    assert dashboard["transactions"][0]["invoice_number"] == "INV-MVP-1001"

    provisioned = client.post(
        "/v1/auth/organizations",
        headers=headers,
        json={
            "full_name": "Second Admin",
            "email": "second@example.com",
            "password": "another-long-password-456",
            "organization_name": "Second Institution",
        },
    )
    assert provisioned.status_code == 201
    client.post("/v1/auth/logout")
    signed_in = client.post(
        "/v1/auth/login",
        json={"email": "second@example.com", "password": "another-long-password-456"},
    )
    assert signed_in.status_code == 200
    assert client.get("/v1/ui/dashboard").json()["metrics"]["total"] == 0
    assert client.get("/v1/ui/transactions").json()["count"] == 0
    assert client.get("/v1/ui/transactions/" + body["transaction_id"]).status_code == 404



def test_authenticated_document_upload_extracts_fields(client):
    created = client.post(
        "/v1/auth/bootstrap",
        headers={"X-Bootstrap-Token": "test-bootstrap-token-long-enough"},
        json={
            "full_name": "Document Admin",
            "email": "docs@example.com",
            "password": "a-long-test-password-123",
            "organization_name": "Document Institution",
        },
    )
    assert created.status_code == 201
    uploaded = client.post(
        "/v1/ui/documents",
        files={
            "file": (
                "invoice.txt",
                "Invoice No: INV-DOC-100\nSupplier: Kigali Coffee Cooperative\n"
                "Buyer: Northstar Imports\nCurrency: EUR\nTotal Due: 1250.00",
                "text/plain",
            )
        },
    )
    assert uploaded.status_code == 201
    body = uploaded.json()
    assert body["extraction"]["invoice_number"] == "INV-DOC-100"
    assert body["extraction"]["supplier_name"] == "Kigali Coffee Cooperative"
    assert body["extraction"]["amount"] == 1250.0
    listed = client.get("/v1/ui/documents")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
