from __future__ import annotations
import hashlib
import re
from decimal import Decimal, InvalidOperation
from typing import Any

ALLOWED_TYPES = {"invoice", "purchase_order", "contract", "payment_record", "delivery_note"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_text(text: str) -> str:
    return " ".join(text.replace("\x00", " ").split())


def extract_fields(text: str) -> dict[str, Any]:
    text = normalize_text(text)
    fields: dict[str, Any] = {}
    patterns = {
        "invoice_number": r"(?:invoice|inv\.?)[\s#:=-]*([A-Z0-9][A-Z0-9._/-]{2,})",
        "purchase_order_number": r"(?:purchase\s*order|PO)[\s#:=-]*([A-Z0-9][A-Z0-9._/-]{2,})",
        "currency": r"\b(USD|EUR|GBP|RWF|KES|UGX|TZS|NGN|ZAR|GHS)\b",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.I)
        if match: fields[key] = match.group(1).upper()
    amount_patterns = [r"(?:total|amount\s*due|grand\s*total)[\s:=-]*(?:[A-Z]{3}\s*)?([0-9][0-9,]*(?:\.[0-9]{1,2})?)"]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            try: fields["amount"] = str(Decimal(match.group(1).replace(",", "")))
            except InvalidOperation: pass
            break
    return fields


def ingest_text(document_type: str, text: str, filename: str | None = None) -> dict[str, Any]:
    if document_type not in ALLOWED_TYPES:
        raise ValueError(f"Unsupported document_type: {document_type}")
    clean = normalize_text(text)
    return {
        "document_type": document_type,
        "filename": filename,
        "sha256": sha256_bytes(clean.encode()),
        "character_count": len(clean),
        "fields": extract_fields(clean),
        "raw_text": clean,
    }
