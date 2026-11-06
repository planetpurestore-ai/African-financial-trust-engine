from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.models import Invoice
from app.evidence import Evidence


DEFAULT_RISK_SETTINGS = {
    "require_commercial_evidence": True,
    "require_payment_evidence": True,
    "reject_duplicate_invoice": True,
    "reject_payment_mismatch": True,
    "reject_counterparty_conflict": True,
    "manual_review_amount_threshold": None,
}


def _norm(value: str | None) -> str | None:
    return " ".join(value.casefold().split()) if value else None


def assess(
    invoice: Invoice,
    evidence: list[Evidence],
    duplicate: bool = False,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = {**DEFAULT_RISK_SETTINGS, **(settings or {})}
    payment = [item for item in evidence if item.evidence_type == "payment_record"]
    payment_matches = [
        item for item in payment
        if item.amount == invoice.amount and (not item.currency or item.currency == invoice.currency)
    ]
    commercial = [item for item in evidence if item.evidence_type in {"purchase_order", "contract"}]
    counterparties = []
    for item in evidence:
        if item.supplier_name:
            counterparties.append(_norm(item.supplier_name))
        if item.buyer_name:
            counterparties.append(_norm(item.buyer_name))
    counterparty_conflict = len(set(value for value in counterparties if value)) > 2

    risk_flags: list[str] = []
    reject_flags: list[str] = []

    if duplicate:
        risk_flags.append("duplicate_invoice_number")
        if policy["reject_duplicate_invoice"]:
            reject_flags.append("duplicate_invoice_number")
    if not commercial and policy["require_commercial_evidence"]:
        risk_flags.append("no_commercial_evidence")
    if payment and not payment_matches:
        risk_flags.append("payment_amount_or_currency_conflict")
        if policy["reject_payment_mismatch"]:
            reject_flags.append("payment_amount_or_currency_conflict")
    if counterparty_conflict:
        risk_flags.append("counterparty_inconsistency")
        if policy["reject_counterparty_conflict"]:
            reject_flags.append("counterparty_inconsistency")
    if not payment and policy["require_payment_evidence"]:
        risk_flags.append("payment_not_verified")

    threshold = policy.get("manual_review_amount_threshold")
    if threshold is not None and invoice.amount > Decimal(str(threshold)):
        risk_flags.append("amount_above_auto_approval_threshold")

    risk_score = min(100, len(risk_flags) * 20)
    if payment_matches and commercial:
        risk_score = max(0, risk_score - 20)
    decision = "reject" if reject_flags else ("review" if risk_flags else "approve")
    return {
        "risk_score": risk_score,
        "risk_level": "high" if risk_score >= 60 else "medium" if risk_score >= 20 else "low",
        "decision": decision,
        "flags": risk_flags,
        "payment_evidence_count": len(payment),
        "payment_matches": len(payment_matches),
        "commercial_evidence_count": len(commercial),
        "policy_applied": policy,
    }
