from app.models import Invoice
from app.evidence import Evidence


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.strip().casefold().split()) or None


def compare_invoice_to_evidence(invoice: Invoice, evidence: Evidence) -> dict:
    """Compare an invoice with one piece of evidence using explainable checks."""
    invoice_supplier = _normalize_text(invoice.supplier_name)
    invoice_buyer = _normalize_text(invoice.buyer_name)
    evidence_supplier = _normalize_text(evidence.supplier_name)
    evidence_buyer = _normalize_text(evidence.buyer_name)

    checks = {
        "supplier_match": evidence_supplier is not None and evidence_supplier == invoice_supplier,
        "buyer_match": evidence_buyer is not None and evidence_buyer == invoice_buyer,
        "amount_match": evidence.amount is not None and evidence.amount == invoice.amount,
        "currency_match": evidence.currency is not None and evidence.currency == invoice.currency,
    }

    passed = sum(checks.values())
    total = len(checks)
    failed_checks = [name for name, passed_check in checks.items() if not passed_check]
    score = round((passed / total) * 100, 2) if total else 0.0

    if passed == total:
        status = "verified"
    else:
        status = "review_required"

    return {
        "status": status,
        "checks": checks,
        "failed_checks": failed_checks,
        "passed_checks": passed,
        "total_checks": total,
        "verification_score": score,
    }
