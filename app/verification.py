from __future__ import annotations

from app.models import Invoice
from app.evidence import Evidence

CHECK_NAMES = ("supplier_match", "buyer_match", "amount_match", "currency_match")
CHECK_WEIGHTS = {
    "supplier_match": 15.0,
    "buyer_match": 15.0,
    "amount_match": 15.0,
    "currency_match": 15.0,
}
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


def _aggregate(
    checks_by_evidence: dict[str, dict[str, bool | None]],
    evidence_items: list[Evidence] | None = None,
    policy: dict | None = None,
) -> dict:
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

    policy = policy or {"require_commercial_evidence": True, "require_payment_evidence": True}
    require_commercial = bool(policy.get("require_commercial_evidence", True))
    require_payment = bool(policy.get("require_payment_evidence", True))
    items = evidence_items or []
    has_commercial = any(
        e.evidence_type in {"purchase_order", "contract"}
        and any(value is not None for value in (e.supplier_name, e.buyer_name, e.amount, e.currency))
        for e in items
    )
    has_payment = any(
        e.evidence_type == "payment_record"
        and any(value is not None for value in (e.supplier_name, e.buyer_name, e.amount, e.currency))
        for e in items
    )
    has_delivery = any(
        e.evidence_type == "delivery_note"
        and any(value is not None for value in (e.supplier_name, e.buyer_name, e.amount, e.currency, e.evidence_date))
        for e in items
    )

    verification_score = core_score
    if has_commercial:
        verification_score += COMMERCIAL_EVIDENCE_WEIGHT
    if has_payment:
        verification_score += PAYMENT_EVIDENCE_WEIGHT

    # Conflicting evidence must materially reduce confidence. Missing evidence
    # reduces confidence as well, rather than producing a misleading 75/100.
    verification_score -= len(conflicts) * 15.0
    verification_score = round(max(0.0, min(100.0, verification_score)), 2)

    hard_conflict = bool(conflicts)
    complete_core_checks = passed == len(CHECK_NAMES) and not incomplete_checks and not hard_conflict
    evidence_complete = (has_commercial or not require_commercial) and (has_payment or not require_payment)
    verified = complete_core_checks and evidence_complete
    status = "verified" if verified else "review_required"

    failed_checks = [name for name, value in checks.items() if not value]
    failed_checks.extend(f"conflict:{name}" for name in conflicts)
    if not has_commercial and require_commercial:
        failed_checks.append("missing_commercial_evidence")
    if not has_payment and require_payment:
        failed_checks.append("missing_payment_evidence")

    return {
        "status": status,
        "checks": checks,
        "failed_checks": failed_checks,
        "conflicts": conflicts,
        "incomplete_checks": incomplete_checks,
        "passed_checks": passed,
        "total_checks": len(CHECK_NAMES),
        "verification_score": verification_score,
        "evidence_count": len(checks_by_evidence),
        "supporting_evidence": supporting_evidence,
        "commercial_evidence_present": has_commercial,
        "payment_evidence_present": has_payment,
        "delivery_evidence_present": has_delivery,
        "policy_applied": {
            "require_commercial_evidence": require_commercial,
            "require_payment_evidence": require_payment,
        },
    }


def _apply_reference_checks(result: dict, invoice: Invoice, evidence_items: list[Evidence]) -> dict:
    reference_rules = (
        ("purchase_order_number", "purchase_order"),
        ("contract_reference", "contract"),
        ("delivery_reference", "delivery_note"),
    )
    reference_checks = {}
    for invoice_field, evidence_type in reference_rules:
        expected = getattr(invoice, invoice_field, None)
        if not expected:
            continue
        matches = [
            item.evidence_id
            for item in evidence_items
            if item.evidence_type == evidence_type
            and _normalize_text(item.reference_number) == _normalize_text(expected)
        ]
        matched = bool(matches)
        check_name = f"{invoice_field}_match"
        result["checks"][check_name] = matched
        result["supporting_evidence"][check_name] = matches
        result["total_checks"] += 1
        if matched:
            result["passed_checks"] += 1
        else:
            result["failed_checks"].append(check_name)
            result["verification_score"] = round(max(0.0, result["verification_score"] - 10.0), 2)
            result["status"] = "review_required"
        reference_checks[invoice_field] = {
            "expected_reference": expected,
            "evidence_type": evidence_type,
            "matched": matched,
            "matching_evidence_ids": matches,
        }
    result["reference_checks"] = reference_checks
    return result


def compare_invoice_to_evidence(invoice: Invoice, evidence: Evidence, policy: dict | None = None) -> dict:
    result = _aggregate(
        {evidence.evidence_id: _checks_for_evidence(invoice, evidence)},
        [evidence],
        policy,
    )
    return _apply_reference_checks(result, invoice, [evidence])


def compare_invoice_to_evidence_set(invoice: Invoice, evidence_items: list[Evidence], policy: dict | None = None) -> dict:
    checks_by_evidence = {item.evidence_id: _checks_for_evidence(invoice, item) for item in evidence_items}
    result = _aggregate(checks_by_evidence, evidence_items, policy)
    return _apply_reference_checks(result, invoice, evidence_items)
