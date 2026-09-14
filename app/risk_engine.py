from __future__ import annotations
from decimal import Decimal
from typing import Any
from app.models import Invoice
from app.evidence import Evidence


def _norm(v: str | None) -> str | None:
    return " ".join(v.casefold().split()) if v else None


def assess(invoice: Invoice, evidence: list[Evidence], duplicate: bool = False) -> dict[str, Any]:
    payment = [e for e in evidence if e.evidence_type == "payment_record"]
    payment_matches = [e for e in payment if e.amount == invoice.amount and (not e.currency or e.currency == invoice.currency)]
    contract_or_po = [e for e in evidence if e.evidence_type in {"purchase_order", "contract"}]
    counterparties = []
    for e in evidence:
        if e.supplier_name: counterparties.append(_norm(e.supplier_name))
        if e.buyer_name: counterparties.append(_norm(e.buyer_name))
    counterparty_conflict = len(set(x for x in counterparties if x)) > 2
    risk_flags: list[str] = []
    if duplicate: risk_flags.append("duplicate_invoice_number")
    if not contract_or_po: risk_flags.append("no_commercial_evidence")
    if payment and not payment_matches: risk_flags.append("payment_amount_or_currency_conflict")
    if counterparty_conflict: risk_flags.append("counterparty_inconsistency")
    if not payment: risk_flags.append("payment_not_verified")
    risk_score = min(100, len(risk_flags) * 20)
    if payment_matches and contract_or_po: risk_score = max(0, risk_score - 20)
    decision = "reject" if any(x in risk_flags for x in ("duplicate_invoice_number", "payment_amount_or_currency_conflict", "counterparty_inconsistency")) else ("review" if risk_flags else "approve")
    return {"risk_score": risk_score, "risk_level": "high" if risk_score >= 60 else "medium" if risk_score >= 20 else "low", "decision": decision, "flags": risk_flags, "payment_evidence_count": len(payment), "payment_matches": len(payment_matches), "commercial_evidence_count": len(contract_or_po)}
