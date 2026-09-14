import hashlib
import re
from decimal import Decimal, InvalidOperation
from datetime import date


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_pdf_text(data: bytes) -> str:
    from io import BytesIO
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def _first(patterns, text):
    for pattern in patterns:
        m = re.search(pattern, text, re.I | re.M)
        if m:
            return m.group(1).strip()
    return None


def extract_fields(text: str) -> dict:
    compact = re.sub(r"[ \t]+", " ", text)
    invoice_number = _first([r"(?:invoice\s*(?:no|number|#)|inv\.?\s*#)\s*[:#-]?\s*([A-Z0-9][A-Z0-9./_-]{1,})"], compact)
    currency = _first([r"\b(USD|EUR|GBP|RWF|KES|UGX|TZS|ZAR|GHS|NGN|XOF|XAF)\b"], compact)
    amount_raw = _first([r"(?:total|amount due|invoice total)\s*[:=]?\s*(?:[A-Z]{3}\s*)?([0-9][0-9,]*(?:\.\d{1,2})?)"], compact)
    amount = None
    if amount_raw:
        try:
            amount = str(Decimal(amount_raw.replace(",", "")))
        except InvalidOperation:
            pass
    issue = _first([r"(?:issue date|invoice date|date)\s*[:=]\s*(\d{4}-\d{2}-\d{2})"], compact)
    due = _first([r"(?:due date|payment due)\s*[:=]\s*(\d{4}-\d{2}-\d{2})"], compact)
    fields = {"invoice_number": invoice_number, "currency": currency, "amount": amount, "issue_date": issue, "due_date": due}
    confidence = {k: (1.0 if v else 0.0) for k, v in fields.items()}
    return {"fields": fields, "confidence": confidence, "text_length": len(text)}
