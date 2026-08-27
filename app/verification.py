from app.models import Invoice
from app.evidence import Evidence

CHECK_NAMES = ("supplier_match", "buyer_match", "amount_match", "currency_match")


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.strip().casefold().split()) or None


def _normalize_currency(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip().upper() or None


def _checks_for_evidence(invoice: Invoice, evidence: Evidence) -> dict[str, bool | None]:
    invoice_supplier = _normalize_text(invoice.supplier_name)
    invoice_buyer = _normalize_text(invoice.buyer_name)
    evidence_supplier = _normalize_text(evidence.supplier_name)
    evidence_buyer = _normalize_text(evidence.buyer_name)
    invoice_currency = _normalize_currency(invoice.currency)
    evidence_currency = _normalize_currency(evidence.currency)

    return {
        "supplier_match": None if evidence_supplier is None else evidence_supplier == invoice_supplier,
        "buyer_match": None if evidence_buyer is None else evidence_buyer == invoice_buyer,
        "amount_match": None if evidence.amount is None else evidence.amount == invoice.amount,
        "currency_match": None if evidence_currency is None else evidence_currency == invoice_currency,
    }


def _aggregate(checks_by_evidence: dict[str, dict[str, bool | None]]) -> dict:
    checks: dict[str, bool] = {}
    conflicts: list[str] = []
    incomplete_checks: list[str] = []
    supporting_evidence: dict[str, list[str]] = {}

    for check_name in CHECK_NAMES:
        true_ids = [eid for eid, values in checks_by_evidence.items() if values.get(check_name) is True]
        false_ids = [eid for eid, values in checks_by_evidence.items() if values.get(check_name) is False]
        unknown_ids = [eid for eid, values in checks_by_evidence.items() if values.get(check_name) is None]

        checks[check_name] = bool(true_ids) and not false_ids
        supporting_evidence[check_name] = true_ids

        if true_ids and false_ids:
            conflicts.append(check_name)
        elif not true_ids and not false_ids and unknown_ids:
            incomplete_checks.append(check_name)

    passed = sum(checks.values())
    # Score measures evidence coverage, not pass/fail. A conflicting check is fully
    # scoreable because evidence exists on both sides; conflicts separately force review.
    scoreable = sum(
        bool([eid for eid, values in checks_by_evidence.items() if values.get(name) is not None])
        for name in CHECK_NAMES
    )
    total = len(CHECK_NAMES)
    failed_checks = [name for name, passed_check in checks.items() if not passed_check]
    failed_checks.extend(f"conflict:{name}" for name in conflicts)
    status = "verified" if passed == total and not conflicts and not incomplete_checks else "review_required"

    return {
        "status": status,
        "checks": checks,
        "failed_checks": failed_checks,
        "conflicts": conflicts,
        "incomplete_checks": incomplete_checks,
        "passed_checks": passed,
        "total_checks": total,
        "verification_score": round((scoreable / total) * 100, 2),
        "evidence_count": len(checks_by_evidence),
        "supporting_evidence": supporting_evidence,
    }


def compare_invoice_to_evidence(invoice: Invoice, evidence: Evidence) -> dict:
    """Compare an invoice with one piece of evidence using explainable checks."""
    return _aggregate({evidence.evidence_id: _checks_for_evidence(invoice, evidence)})


def compare_invoice_to_evidence_set(invoice: Invoice, evidence_items: list[Evidence]) -> dict:
    """Aggregate multiple evidence records while surfacing conflicting or incomplete evidence."""
    checks_by_evidence = {item.evidence_id: _checks_for_evidence(invoice, item) for item in evidence_items}
    return _aggregate(checks_by_evidence)
