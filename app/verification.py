from app.models import Invoice
from app.evidence import Evidence


def compare_invoice_to_evidence(invoice: Invoice, evidence: Evidence) -> dict:
    """Compare an invoice with one piece of evidence.

    The result is deliberately explainable: each check is explicit, and the
    response exposes failed checks and a simple percentage score. Missing
    evidence fields are treated as unverified rather than automatically true.
    """
    checks = {
        "supplier_match": (
            evidence.supplier_name is not None
            and evidence.supplier_name == invoice.supplier_name
        ),
        "buyer_match": (
            evidence.buyer_name is not None
            and evidence.buyer_name == invoice.buyer_name
        ),
        "amount_match": (
            evidence.amount is not None
            and evidence.amount == invoice.amount
        ),
        "currency_match": (
            evidence.currency is not None
            and evidence.currency == invoice.currency
        ),
    }

    passed = sum(checks.values())
    total = len(checks)
    failed_checks = [name for name, passed_check in checks.items() if not passed_check]
    score = round((passed / total) * 100, 2) if total else 0.0

    return {
        "status": "verified" if passed == total else "review_required",
        "checks": checks,
        "failed_checks": failed_checks,
        "passed_checks": passed,
        "total_checks": total,
        "verification_score": score,
    }
