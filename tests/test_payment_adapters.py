from app.payment_adapters import adapter_catalog, normalize_payment_event


def test_payment_adapter_catalog_covers_requested_rails():
    catalog = {item["key"]: item for item in adapter_catalog()}
    required = {
        "bank_transfer", "open_banking", "mobile_money", "mpesa", "mtn_momo",
        "airtel_money", "card_network", "apple_pay", "google_pay", "paypal",
        "stripe", "adyen", "flutterwave", "paystack",
    }
    assert required <= catalog.keys()
    assert all(item["status"] == "awaiting_provider_credentials" for item in catalog.values())


def test_payment_event_normalization_is_provider_neutral_and_does_not_claim_truth():
    event = normalize_payment_event("  M-Pesa ", {
        "transactionId": "TX-123",
        "transaction_amount": "1500.00",
        "currency_code": "rwf",
        "transaction_status": "COMPLETED",
        "payer": "Kigali Trading Ltd",
        "payee": "East Africa Imports Ltd",
        "created_at": "2026-09-15T10:00:00Z",
    })
    assert event["provider"] == "m-pesa"
    assert event["provider_transaction_id"] == "TX-123"
    assert event["amount"] == "1500.00"
    assert event["currency"] == "RWF"
    assert event["status"] == "completed"
    assert event["sender"] == "Kigali Trading Ltd"
    assert event["recipient"] == "East Africa Imports Ltd"
    assert event["truth_status"] == "unverified_provider_event"
