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
