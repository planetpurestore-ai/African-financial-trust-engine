from __future__ import annotations
import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint_document(document: dict[str, Any]) -> str:
    payload = {k: v for k, v in document.items() if k not in {"raw_text", "filename"}}
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def verify_hash_chain(events: list[dict[str, Any]]) -> dict[str, Any]:
    expected_previous = "0" * 64
    failures = []
    for event in events:
        if event.get("previous_hash") != expected_previous:
            failures.append({"event_id": event.get("audit_id"), "reason": "previous_hash_mismatch"})
        canonical = f"{expected_previous}|{event.get('transaction_id')}|{event.get('decision')}|{event.get('score')}|{canonical_json(event.get('result', {}))}"
        expected = hashlib.sha256(canonical.encode()).hexdigest()
        if event.get("event_hash") != expected:
            failures.append({"event_id": event.get("audit_id"), "reason": "event_hash_mismatch"})
        expected_previous = event.get("event_hash", expected_previous)
    return {"valid": not failures, "checked": len(events), "failures": failures}
