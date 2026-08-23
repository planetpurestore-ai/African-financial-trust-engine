from app.models import Invoice
from app.evidence import Evidence


def compare_invoice_to_evidence(invoice: Invoice, evidence: Evidence) -> dict:
    checks = {
        "supplier_match": evidence.supplier_name is None or evidence.supplier_name == invoice.supplier_name,
        "buyer_match": evidence.buyer_name is None or evidence.buyer_name == invoice.buyer_name,
        "amount_match": evidence.amount is None or evidence.amount == invoice.amount,
        "currency_match": evidence.currency is None or evidence.currency == invoice.currency,
    }

    passed = sum(checks.values())
    total = len(checks)

    return {
        "status": "verified" if passed == total else "review_required",
        "checks": checks,
        "passed_checks": passed,
        "total_checks": total,
    }
