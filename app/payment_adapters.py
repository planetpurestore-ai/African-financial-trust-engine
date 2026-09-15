"""Provider-neutral payment adapter framework.

The adapters deliberately stop at the provider boundary: real credentials,
contracts, OAuth flows and provider-specific endpoints are configured later.
All rails normalize into one Trust Engine payment-evidence shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PaymentAdapterSpec:
    key: str
    category: str
    display_name: str
    regions: tuple[str, ...]
    capabilities: tuple[str, ...]
    live: bool = False


COMMON = ("payments", "webhooks", "normalized_events")

ADAPTERS: tuple[PaymentAdapterSpec, ...] = (
    PaymentAdapterSpec("bank_transfer", "bank", "Bank transfer / account", ("global",), COMMON + ("account_transactions",)),
    PaymentAdapterSpec("open_banking", "bank", "Open banking", ("supported_markets",), COMMON + ("account_transactions", "balances")),
    PaymentAdapterSpec("mobile_money", "mobile_money", "Mobile money", ("africa",), COMMON + ("wallet_transactions",)),
    PaymentAdapterSpec("mpesa", "mobile_money", "M-Pesa", ("africa",), COMMON + ("wallet_transactions",)),
    PaymentAdapterSpec("mtn_momo", "mobile_money", "MTN MoMo", ("africa",), COMMON + ("wallet_transactions",)),
    PaymentAdapterSpec("airtel_money", "mobile_money", "Airtel Money", ("africa",), COMMON + ("wallet_transactions",)),
    PaymentAdapterSpec("card_network", "card", "Visa / Mastercard card payments", ("global",), COMMON + ("card_transactions",)),
    PaymentAdapterSpec("apple_pay", "wallet", "Apple Pay", ("supported_markets",), COMMON + ("wallet_transactions",)),
    PaymentAdapterSpec("google_pay", "wallet", "Google Pay", ("supported_markets",), COMMON + ("wallet_transactions",)),
    PaymentAdapterSpec("paypal", "psp", "PayPal", ("global",), COMMON + ("merchant_transactions",)),
    PaymentAdapterSpec("stripe", "psp", "Stripe", ("global",), COMMON + ("merchant_transactions", "refunds")),
    PaymentAdapterSpec("adyen", "psp", "Adyen", ("global",), COMMON + ("merchant_transactions", "refunds")),
    PaymentAdapterSpec("flutterwave", "psp", "Flutterwave", ("africa", "global"), COMMON + ("merchant_transactions", "refunds")),
    PaymentAdapterSpec("paystack", "psp", "Paystack", ("africa",), COMMON + ("merchant_transactions", "refunds")),
)

INDEX = {a.key: a for a in ADAPTERS}


def adapter_catalog() -> list[dict[str, Any]]:
    return [
        {
            "key": a.key,
            "category": a.category,
            "display_name": a.display_name,
            "regions": list(a.regions),
            "capabilities": list(a.capabilities),
            "live": a.live,
            "status": "awaiting_provider_credentials" if not a.live else "connected",
        }
        for a in ADAPTERS
    ]


def normalize_payment_event(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize common provider payload fields without asserting truth."""
    def first(*keys: str):
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return value
        return None

    amount = first("amount", "transaction_amount", "value", "gross_amount")
    currency = first("currency", "currency_code", "currencyCode")
    return {
        "source": "payment_adapter",
        "provider": provider.strip().lower(),
        "provider_transaction_id": first("transaction_id", "transactionId", "payment_id", "paymentId", "id", "reference"),
        "reference": first("reference", "transaction_ref", "payment_reference", "receipt", "receipt_number"),
        "status": str(first("status", "transaction_status", "state") or "unknown").lower(),
        "amount": str(amount) if amount is not None else None,
        "currency": str(currency).upper() if currency else None,
        "sender": first("sender", "sender_name", "payer", "from", "source_account_name"),
        "recipient": first("recipient", "recipient_name", "payee", "to", "destination_account_name"),
        "timestamp": first("timestamp", "created_at", "transaction_date", "date"),
        "metadata": first("metadata", "meta") or {},
        "truth_status": "unverified_provider_event",
    }
