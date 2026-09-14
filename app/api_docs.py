from fastapi import APIRouter

router = APIRouter(tags=["system"])

@router.get("/v1/capabilities")
def capabilities():
    return {
        "service": "African Financial Trust Trust Engine",
        "version": "2.1.0",
        "capabilities": [
            "organization_isolation", "api_key_authentication", "idempotent_intake",
            "invoice_evidence_verification", "duplicate_detection", "risk_scoring",
            "explainable_decisioning", "hash_chained_audit", "deterministic_document_intake"
        ],
        "decisions": ["verified", "review_required", "rejected"]
    }
