from __future__ import annotations

from app.models import Invoice
from app.evidence import Evidence

CHECK_NAMES = ("supplier_match", "buyer_match", "amount_match", "currency_match")
CHECK_WEIGHTS = {name: 15.0 for name in CHECK_NAMES}
COMMERCIAL_EVIDENCE_WEIGHT = 20.0
PAYMENT_EVIDENCE_WEIGHT = 20.0


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


def _aggregate(checks_by_evidence: dict[str, dict[str, bool | None]], evidence_items: list[Evidence] | None = None) -> dict:
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
    core_score = sum(CHECK_WEIGHTS[name] for name, value in checks.items() if value)
    items = evidence_items or []
    commercial = [e for e in items if e.evidence_type in {"purchase_order", "contract"}]
    payments = [e for e in items if e.evidence_type == "payment_record"]

    # Evidence classes earn credit only when a single record of that class
    # contains the required matching fields. Presence alone is not proof.
    commercial_valid = any(
        all(_checks_for_evidence_from_map(checks_by_evidence, e.evidence_id).get(k) is True
            for k in CHECK_NAMES)
        for e in commercial
    )
    payment_valid = any(
        checks_by_evidence.get(e.evidence_id, {}).get("amount_match") is True
        and checks_by_evidence.get(e.evidence_id, {}).get("currency_match") is True
        for e in payments
    )

    verification_score = core_score
    if commercial_valid:
        verification_score += COMMERCIAL_EVIDENCE_WEIGHT
    if payment_valid:
        verification_score += PAYMENT_EVIDENCE_WEIGHT
    verification_score -= len(conflicts) * 15.0
    verification_score = round(max(0.0, min(100.0, verification_score)), 2)

    complete_core_checks = passed == len(CHECK_NAMES) and not incomplete_checks and not conflicts
    verified = complete_core_checks and commercial_valid and payment_valid
    failed_checks = [name for name, value in checks.items() if not value]
    failed_checks.extend(f"conflict:{name}" for name in conflicts)
    if not commercial:
        failed_checks.append("missing_commercial_evidence")
    elif not commercial_valid:
        failed_checks.append("commercial_evidence_not_matched")
        if any(any(value is None for value in checks_by_evidence.get(e.evidence_id, {}).values()) for e in commercial):
            failed_checks.append("missing_commercial_evidence_fields")
    if not payments:
        failed_checks.append("missing_payment_evidence")
    elif not payment_valid:
        failed_checks.append("payment_evidence_not_matched")

    return {
        "status": "verified" if verified else "review_required",
        "checks": checks,
        "failed_checks": failed_checks,
        "conflicts": conflicts,
        "incomplete_checks": incomplete_checks,
        "passed_checks": passed,
        "total_checks": len(CHECK_NAMES),
        "verification_score": verification_score,
        "evidence_count": len(checks_by_evidence),
        "supporting_evidence": supporting_evidence,
        "commercial_evidence_present": bool(commercial),
        "payment_evidence_present": bool(payments),
        "commercial_evidence_matched": commercial_valid,
        "payment_evidence_matched": payment_valid,
        "evidence_provenance": "caller_supplied_unverified",
        "authenticity_note": "Field consistency is not independent proof that a document or payment record is genuine.",
    }


def _checks_for_evidence_from_map(checks_by_evidence: dict[str, dict[str, bool | None]], evidence_id: str) -> dict[str, bool | None]:
    return checks_by_evidence.get(evidence_id, {})


def compare_invoice_to_evidence(invoice: Invoice, evidence: Evidence) -> dict:
    return _aggregate({evidence.evidence_id: _checks_for_evidence(invoice, evidence)}, [evidence])


def compare_invoice_to_evidence_set(invoice: Invoice, evidence_items: list[Evidence]) -> dict:
    checks_by_evidence = {item.evidence_id: _checks_for_evidence(invoice, item) for item in evidence_items}
    return _aggregate(checks_by_evidence, evidence_items)
