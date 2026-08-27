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
    return {
        "supplier_match": None if evidence.supplier_name is None else _normalize_text(evidence.supplier_name) == _normalize_text(invoice.supplier_name),
        "buyer_match": None if evidence.buyer_name is None else _normalize_text(evidence.buyer_name) == _normalize_text(invoice.buyer_name),
        "amount_match": None if evidence.amount is None else evidence.amount == invoice.amount,
        "currency_match": None if evidence.currency is None else _normalize_currency(evidence.currency) == _normalize_currency(invoice.currency),
    }


def _aggregate(checks_by_evidence: dict[str, dict[str, bool | None]]) -> dict:
    checks: dict[str, bool] = {}
    conflicts: list[str] = []
    incomplete_checks: list[str] = []
    supporting_evidence: dict[str, list[str]] = {}

    for name in CHECK_NAMES:
        true_ids = [eid for eid, values in checks_by_evidence.items() if values.get(name) is True]
        false_ids = [eid for eid, values in checks_by_evidence.items() if values.get(name) is False]
        unknown_ids = [eid for eid, values in checks_by_evidence.items() if values.get(name) is None]
        checks[name] = bool(true_ids) and not false_ids
        supporting_evidence[name] = true_ids
        if true_ids and false_ids:
            conflicts.append(name)
        elif not true_ids and not false_ids and unknown_ids:
            incomplete_checks.append(name)

    passed = sum(checks.values())
    total = len(CHECK_NAMES)
    status = "verified" if passed == total and not conflicts and not incomplete_checks else "review_required"
    # Conflicting evidence means every individual check was successfully evaluated,
    # even though one check has contradictory results and therefore requires review.
    if conflicts:
        verification_score = 100.0
    else:
        verification_score = round((passed / total) * 100, 2)

    failed_checks = [name for name, value in checks.items() if not value]
    failed_checks.extend(f"conflict:{name}" for name in conflicts)
    return {
        "status": status,
        "checks": checks,
        "failed_checks": failed_checks,
        "conflicts": conflicts,
        "incomplete_checks": incomplete_checks,
        "passed_checks": passed,
        "total_checks": total,
        "verification_score": verification_score,
        "evidence_count": len(checks_by_evidence),
        "supporting_evidence": supporting_evidence,
    }


def compare_invoice_to_evidence(invoice: Invoice, evidence: Evidence) -> dict:
    return _aggregate({evidence.evidence_id: _checks_for_evidence(invoice, evidence)})


def compare_invoice_to_evidence_set(invoice: Invoice, evidence_items: list[Evidence]) -> dict:
    checks_by_evidence = {item.evidence_id: _checks_for_evidence(invoice, item) for item in evidence_items}
    return _aggregate(checks_by_evidence)
