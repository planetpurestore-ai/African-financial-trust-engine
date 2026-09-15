import hashlib
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime


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


def _normalize_date(value):
    if not value:
        return None
    value = value.strip()
    formats = (
        "%Y-%m-%d",
        "%d %B %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return value


def extract_fields(text: str) -> dict:
    compact = re.sub(r"[ \t]+", " ", text)
    invoice_number = _first(
        [r"(?:invoice\s*(?:no|number|#)|inv\.?\s*#)\s*[:#-]?\s*([A-Z0-9][A-Z0-9./_-]{1,})"],
        compact,
    )
    supplier_name = _first(
        [r"(?:supplier|seller|vendor)\s*[:=]\s*([^\n\r]+)", r"(?:from)\s*[:=]\s*([^\n\r]+)"],
        text,
    )
    buyer_name = _first(
        [r"(?:buyer|customer|bill\s*to)\s*[:=]\s*([^\n\r]+)", r"(?:to)\s*[:=]\s*([^\n\r]+)"],
        text,
    )
    currency = _first([r"\b(USD|EUR|GBP|RWF|KES|UGX|TZS|ZAR|GHS|NGN|XOF|XAF)\b"], compact)
    amount_raw = _first(
        [r"(?:total\s*(?:due)?|amount\s*due|invoice\s*total)\s*[:=]?\s*(?:[A-Z]{3}\s*)?([0-9][0-9,]*(?:\.\d{1,2})?)"],
        compact,
    )
    amount = None
    if amount_raw:
        try:
            amount = str(Decimal(amount_raw.replace(",", "")))
        except InvalidOperation:
            pass

    issue_raw = _first(
        [
            r"(?:issue\s*date|invoice\s*date|date)\s*[:=]\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}|[A-Za-z]+\s+[0-9]{1,2},\s+[0-9]{4}|[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}|[0-9]{1,2}-[0-9]{1,2}-[0-9]{4})"
        ],
        text,
    )
    due_raw = _first(
        [
            r"(?:due\s*date|payment\s*due)\s*[:=]\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}|[A-Za-z]+\s+[0-9]{1,2},\s+[0-9]{4}|[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}|[0-9]{1,2}-[0-9]{1,2}-[0-9]{4})"
        ],
        text,
    )
    issue = _normalize_date(issue_raw)
    due = _normalize_date(due_raw)

    fields = {
        "invoice_number": invoice_number,
        "supplier_name": supplier_name,
        "buyer_name": buyer_name,
        "currency": currency,
        "amount": amount,
        "issue_date": issue,
        "due_date": due,
    }
    confidence = {k: (1.0 if v else 0.0) for k, v in fields.items()}
    return {**fields, "fields": fields, "confidence": confidence, "text_length": len(text)}
