from app.models import Invoice
from app.evidence import Evidence


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.strip().casefold().split()) or None


def _checks_for_evidence(invoice: Invoice, evidence: Evidence) -> dict:
    invoice_supplier = _normalize_text(invoice.supplier_name)
    invoice_buyer = _normalize_text(invoice.buyer_name)
    evidence_supplier = _normalize_text(evidence.supplier_name)
    evidence_buyer = _normalize_text(evidence.buyer_name)

    return {
        "supplier_match": evidence_supplier is not None and evidence_supplier == invoice_supplier,
        "buyer_match": evidence_buyer is not None and evidence_buyer == invoice_buyer,
        "amount_match": evidence.amount is not None and evidence.amount == invoice.amount,
        "currency_match": evidence.currency is not None and evidence.currency == invoice.currency,
    }


def compare_invoice_to_evidence(invoice: Invoice, evidence: Evidence) -> dict:
    """Compare an invoice with one piece of evidence using explainable checks."""
    checks = _checks_for_evidence(invoice, evidence)
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


def compare_invoice_to_evidence_set(invoice: Invoice, evidence_items: list[Evidence]) -> dict:
    """Aggregate multiple evidence records into one explainable verification result."""
    if not evidence_items:
        return {
            "status": "review_required",
            "checks": {
                "supplier_match": False,
                "buyer_match": False,
                "amount_match": False,
                "currency_match": False,
            },
            "failed_checks": [
                "supplier_match",
                "buyer_match",
                "amount_match",
                "currency_match",
            ],
            "passed_checks": 0,
            "total_checks": 4,
            "verification_score": 0.0,
            "evidence_count": 0,
            "supporting_evidence": {},
        }

    checks_by_evidence = {
        item.evidence_id: _checks_for_evidence(invoice, item)
        for item in evidence_items
    }

    checks = {
        check_name: any(
            evidence_checks[check_name]
            for evidence_checks in checks_by_evidence.values()
        )
        for check_name in (
            "supplier_match",
            "buyer_match",
            "amount_match",
            "currency_match",
        )
    }

    supporting_evidence = {
        check_name: [
            evidence_id
            for evidence_id, evidence_checks in checks_by_evidence.items()
            if evidence_checks[check_name]
        ]
        for check_name in checks
    }

    passed = sum(checks.values())
    total = len(checks)
    failed_checks = [name for name, passed_check in checks.items() if not passed_check]

    return {
        "status": "verified" if passed == total else "review_required",
        "checks": checks,
        "failed_checks": failed_checks,
        "passed_checks": passed,
        "total_checks": total,
        "verification_score": round((passed / total) * 100, 2),
        "evidence_count": len(evidence_items),
        "supporting_evidence": supporting_evidence,
    }
