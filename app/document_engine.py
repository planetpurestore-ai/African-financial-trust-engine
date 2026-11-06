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
        "%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y",
        "%b %d, %Y", "%d/%m/%Y", "%d-%m-%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return value



def inspect_document_integrity(data: bytes | str, content_type: str) -> dict:
    """Return conservative tampering-risk indicators, never an authenticity verdict."""
    signals = []
    if content_type == "application/pdf":
        if isinstance(data, str):
            data = data.encode("utf-8")
        if data.count(b"%%EOF") > 1:
            signals.append("multiple_pdf_revision_markers")
        if re.search(rb"/(?:JavaScript|JS)\b", data):
            signals.append("pdf_embedded_script")
        if b"/EmbeddedFiles" in data:
            signals.append("pdf_embedded_files")
        if b"/OpenAction" in data or re.search(rb"/AA\b", data):
            signals.append("pdf_active_action")
        if b"/Encrypt" in data:
            signals.append("pdf_encrypted_document")
        if b"/ByteRange" in data and b"/Contents" in data:
            signals.append("pdf_signature_field_present_but_not_cryptographically_verified")
    elif content_type.startswith("text/"):
        if isinstance(data, bytes):
            if bytes([0]) in data:
                signals.append("text_contains_null_bytes")
            try:
                decoded = data.decode("utf-8")
            except UnicodeDecodeError:
                decoded = ""
                signals.append("text_encoding_is_not_utf8")
        else:
            decoded = data
            if chr(0) in decoded:
                signals.append("text_contains_null_bytes")
        if any(0x202A <= ord(char) <= 0x202E or 0x2066 <= ord(char) <= 0x2069 for char in decoded):
            signals.append("text_contains_bidirectional_override_controls")
    return {
        "status": "review" if signals else "no_obvious_anomaly",
        "signals": signals,
        "is_authenticity_proof": False,
        "limitations": "Heuristic file-integrity indicators only; they do not establish issuer identity, signature validity, or transaction truth.",
    }


def extract_fields(text: str) -> dict:
    compact = re.sub(r"[ \t]+", " ", text)
    invoice_number = _first([r"(?:invoice\s*(?:no|number|#)|inv\.?\s*#)\s*[:#-]?\s*([A-Z0-9][A-Z0-9./_-]{1,})"], compact)
    supplier_name = _first([r"(?:supplier|seller|vendor)\s*[:=]\s*([^\n\r]+)", r"(?:from)\s*[:=]\s*([^\n\r]+)"], text)
    buyer_name = _first([r"(?:buyer|customer|bill\s*to)\s*[:=]\s*([^\n\r]+)", r"(?:to)\s*[:=]\s*([^\n\r]+)"], text)
    currency = _first([r"\b(USD|EUR|GBP|RWF|KES|UGX|TZS|ZAR|GHS|NGN|XOF|XAF)\b"], compact)
    amount_raw = _first([
        r"^\s*(?:invoice\s+total|total(?:\s+due)?|amount\s+due)\s*[:=]?\s*(?:[A-Z]{3}\s*)?([0-9][0-9,]*(?:\.\d{1,2})?)",
        r"^\s*amount\s*[:=]\s*(?:[A-Z]{3}\s*)?([0-9][0-9,]*(?:\.\d{1,2})?)",
    ], compact)
    def money_string(raw):
        if not raw:
            return None
        try:
            # Preserve decimal precision for financial amounts; floats can
            # silently round large values and fractions of a currency unit.
            return format(Decimal(raw.replace(",", "")), "f")
        except (InvalidOperation, ValueError):
            return None

    amount = money_string(amount_raw)
    subtotal_raw = _first([
        r"(?:sub\s*total|subtotal)\s*[:=]?\s*(?:[A-Z]{3}\s*)?([0-9][0-9,]*(?:\.\d{1,2})?)",
    ], compact)
    tax_raw = _first([
        r"(?:tax\s*amount|vat\s*amount|total\s*tax|total\s*vat)\s*[:=]?\s*(?:[A-Z]{3}\s*)?([0-9][0-9,]*(?:\.\d{1,2})?)",
    ], compact)
    subtotal = money_string(subtotal_raw)
    tax_amount = money_string(tax_raw)
    issue_raw = _first([r"(?:issue\s*date|invoice\s*date|date)\s*[:=]\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}|[A-Za-z]+\s+[0-9]{1,2},\s+[0-9]{4}|[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}|[0-9]{1,2}-[0-9]{1,2}-[0-9]{4})"], text)
    due_raw = _first([r"(?:due\s*date|payment\s*due)\s*[:=]\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}|[A-Za-z]+\s+[0-9]{1,2},\s+[0-9]{4}|[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}|[0-9]{1,2}-[0-9]{1,2}-[0-9]{4})"], text)
    issue = _normalize_date(issue_raw)
    due = _normalize_date(due_raw)
    fields = {
        "invoice_number": invoice_number,
        "supplier_name": supplier_name,
        "buyer_name": buyer_name,
        "currency": currency,
        "amount": amount,
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "issue_date": issue,
        "due_date": due,
    }
    confidence = {k: (1.0 if v else 0.0) for k, v in fields.items()}
    required = ("invoice_number", "supplier_name", "buyer_name", "amount", "currency")
    missing_required = [k for k in required if not fields[k]]
    arithmetic_consistent = None
    review_reasons = [f"missing_required_field:{name}" for name in missing_required]
    if subtotal is not None and tax_amount is not None and amount is not None:
        arithmetic_consistent = (
            Decimal(subtotal) + Decimal(tax_amount) == Decimal(amount)
        )
        if not arithmetic_consistent:
            review_reasons.append("subtotal_tax_total_mismatch")
    return {
        **fields,
        "fields": fields,
        "confidence": confidence,
        "confidence_basis": "field_presence_only; not an OCR/model truth probability",
        "arithmetic_consistent": arithmetic_consistent,
        "requires_review": bool(review_reasons),
        "review_reasons": review_reasons,
        "missing_required_fields": missing_required,
        "text_length": len(text),
    }
