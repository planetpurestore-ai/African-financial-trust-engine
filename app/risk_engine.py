from __future__ import annotations

from typing import Any
from app.models import Invoice
from app.evidence import Evidence


def _norm(v: str | None) -> str | None:
    return " ".join(v.casefold().split()) if v else None


def assess(invoice: Invoice, evidence: list[Evidence], duplicate: bool = False) -> dict[str, Any]:
    payments = [e for e in evidence if e.evidence_type == "payment_record"]
    payment_matches = [
        e for e in payments
        if e.amount == invoice.amount and e.currency == invoice.currency
    ]
    commercial = [e for e in evidence if e.evidence_type in {"purchase_order", "contract"}]
    commercial_matches = [
        e for e in commercial
        if _norm(e.supplier_name) == _norm(invoice.supplier_name)
        and _norm(e.buyer_name) == _norm(invoice.buyer_name)
        and e.amount == invoice.amount
        and e.currency == invoice.currency
    ]

    counterparty_mismatch = any(
        (e.supplier_name is not None and _norm(e.supplier_name) != _norm(invoice.supplier_name))
        or (e.buyer_name is not None and _norm(e.buyer_name) != _norm(invoice.buyer_name))
        for e in evidence
    )

    risk_flags: list[str] = []
    if duplicate:
        risk_flags.append("duplicate_invoice_number")
    if not commercial_matches:
        risk_flags.append("no_matching_commercial_evidence")
    explicit_payment_conflict = any(
        (e.amount is not None and e.amount != invoice.amount)
        or (e.currency is not None and e.currency.upper() != invoice.currency.upper())
        for e in payments
    )
    if explicit_payment_conflict:
        risk_flags.append("payment_amount_or_currency_conflict")
    if counterparty_mismatch:
        risk_flags.append("counterparty_inconsistency")
    if not payments:
        risk_flags.append("payment_not_verified")
    elif not payment_matches:
        risk_flags.append("payment_not_matched")

    risk_score = min(100, len(risk_flags) * 20)
    if payment_matches and commercial_matches:
        risk_score = max(0, risk_score - 20)
    # A confirmed duplicate or an explicit payment contradiction is a hard stop.
    # Missing or inconsistent commercial-party fields remain human-review cases.
    reject_flags = {"duplicate_invoice_number", "payment_amount_or_currency_conflict"}
    decision = "reject" if reject_flags.intersection(risk_flags) else ("review" if risk_flags else "approve")
    return {
        "risk_score": risk_score,
        "risk_level": "high" if risk_score >= 60 else "medium" if risk_score >= 20 else "low",
        "decision": decision,
        "flags": risk_flags,
        "payment_evidence_count": len(payments),
        "payment_matches": len(payment_matches),
        "commercial_evidence_count": len(commercial),
        "commercial_evidence_matches": len(commercial_matches),
    }
