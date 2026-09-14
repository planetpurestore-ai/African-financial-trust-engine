from __future__ import annotations
from typing import Any


def build_review_reasons(verification: dict[str, Any], risk: dict[str, Any]) -> list[dict[str, Any]]:
    reasons = []
    for check in verification.get("failed_checks", []):
        reasons.append({"type": "verification_failure", "code": check, "severity": "high"})
    for flag in risk.get("flags", []):
        reasons.append({"type": "risk_flag", "code": flag, "severity": "high" if risk.get("risk_level") == "high" else "medium"})
    return reasons


def recommended_action(decision: str) -> str:
    return {"approve": "proceed", "reject": "decline", "review": "human_review"}.get(decision, "human_review")
