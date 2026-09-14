import hashlib
import hmac
import os

from app.integrations import normalize_financial_event, verify_webhook_signature, webhook_secret_for


def test_webhook_secret_is_deterministic(monkeypatch):
    monkeypatch.setenv("API_KEY_PEPPER", "pepper")
    assert webhook_secret_for(7, "Mono") == webhook_secret_for(7, "mono")
    assert webhook_secret_for(7, "mono") != webhook_secret_for(8, "mono")


def test_webhook_signature_round_trip():
    secret = "secret"
    body = b'{"id":"tx-1"}'
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(body, signature, secret)
    assert not verify_webhook_signature(body, signature[:-1] + "0", secret)


def test_financial_event_normalization():
    event = normalize_financial_event("provider", {"transactionId": "abc", "amount": "10.50", "currency_code": "usd", "state": "PAID"})
    assert event["provider_transaction_id"] == "abc"
    assert event["amount"] == "10.50"
    assert event["currency"] == "USD"
    assert event["status"] == "paid"
