import os
import uuid

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./assurance_test.db")
os.environ.setdefault("API_KEY_PEPPER", "assurance-test-pepper")
os.environ.setdefault("BOOTSTRAP_TOKEN", "assurance-bootstrap-token")

from app.production_entry import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json().get("status") == "ok"


def test_security_headers_and_request_id():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "no-referrer"
    assert response.headers.get("permissions-policy") == "camera=(), microphone=(), geolocation=()"
    assert response.headers.get("x-request-id")


def test_bootstrap_requires_token():
    response = client.post("/v1/organizations", json={"name": "Assurance Bank"})
    assert response.status_code in (401, 403)


def test_bootstrap_and_isolation_flow():
    name = f"Assurance Bank {uuid.uuid4().hex[:8]}"
    response = client.post(
        "/v1/organizations",
        headers={"X-Bootstrap-Token": os.environ["BOOTSTRAP_TOKEN"]},
        json={"name": name},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["organization"]["name"] == name
    assert payload["api_key"].startswith("aft_live_")

    key = payload["api_key"]
    status = client.get("/v1/bank-grade/status", headers={"X-API-Key": key})
    assert status.status_code == 200
    capabilities = status.json()["capabilities"]
    assert capabilities["audit_hash_chain"] is True
    assert capabilities["document_ingestion"] is True
    assert capabilities["authoritative_bank_connections"] is False


def test_unknown_api_key_is_rejected():
    response = client.get("/v1/bank-grade/status", headers={"X-API-Key": "aft_live_invalid"})
    assert response.status_code in (401, 403)
