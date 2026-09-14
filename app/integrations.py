import base64
import hashlib
import hmac
import os
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

class OCRProviderError(RuntimeError):
    pass

def _google_vision_key() -> str:
    key = os.getenv("GOOGLE_VISION_API_KEY")
    if not key:
        raise OCRProviderError("GOOGLE_VISION_API_KEY is not configured")
    return key

def google_vision_document_text(data: bytes) -> str:
    url = "https://vision.googleapis.com/v1/images:annotate"
    payload = {"requests": [{"image": {"content": base64.b64encode(data).decode("ascii")}, "features": [{"type": "DOCUMENT_TEXT_DETECTION"}]}]}
    try:
        with httpx.Client(timeout=45.0) as client:
            response = client.post(url, params={"key": _google_vision_key()}, json=payload)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OCRProviderError(f"OCR provider request failed: {type(exc).__name__}") from exc
    error = body.get("responses", [{}])[0].get("error")
    if error:
        raise OCRProviderError(error.get("message", "OCR provider returned an error"))
    return (body.get("responses", [{}])[0].get("fullTextAnnotation", {}).get("text") or "").strip()

def image_ocr(data: bytes, content_type: str) -> dict[str, Any]:
    provider = os.getenv("OCR_PROVIDER", "google").lower()
    if provider != "google":
        raise OCRProviderError(f"Unsupported OCR_PROVIDER: {provider}")
    return {"provider": "google_vision", "content_type": content_type, "text": google_vision_document_text(data)}

def webhook_secret_for(organization_id: int, provider: str) -> str:
    pepper = os.getenv("API_KEY_PEPPER")
    if not pepper:
        raise RuntimeError("API_KEY_PEPPER is required")
    material = f"webhook:{organization_id}:{provider.strip().lower()}".encode()
    return "aft_wh_" + hmac.new(pepper.encode(), material, hashlib.sha256).hexdigest()

def verify_webhook_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    if not secret or not signature:
        return False
    supplied = signature.removeprefix("sha256=").strip()
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied, expected)

def normalize_financial_event(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    def first(*keys):
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return value
        return None
    amount_raw = first("amount", "transaction_amount", "value")
    amount = None
    if amount_raw is not None:
        try:
            amount = str(Decimal(str(amount_raw)))
        except (InvalidOperation, ValueError):
            pass
    return {
        "provider": provider,
        "provider_transaction_id": first("transaction_id", "transactionId", "id", "reference", "transaction_ref"),
        "reference": first("reference", "transaction_ref", "payment_reference", "receipt", "receipt_number"),
        "status": str(first("status", "transaction_status", "state") or "unknown").lower(),
        "amount": amount,
        "currency": str(first("currency", "currency_code") or "").upper() or None,
        "sender": first("sender", "sender_name", "payer", "from", "source_account_name"),
        "recipient": first("recipient", "recipient_name", "payee", "to", "destination_account_name"),
        "timestamp": first("timestamp", "created_at", "transaction_date", "date"),
        "raw": payload,
    }
