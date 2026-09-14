from fastapi import APIRouter

router = APIRouter(tags=["system"])

@router.get("/v1/capabilities")
def capabilities():
    return {
        "service": "African Financial Trust Trust Engine",
        "version": "2.3.0",
        "capabilities": [
            "organization_isolation", "api_key_authentication", "key_rotation_and_revocation",
            "idempotent_intake", "invoice_evidence_verification", "duplicate_detection",
            "risk_scoring", "explainable_decisioning", "hash_chained_audit",
            "deterministic_document_intake", "pdf_text_extraction", "image_ocr_adapter",
            "financial_webhook_normalization", "event_deduplication", "security_headers",
            "request_size_limits"
        ],
        "decisions": ["verified", "review_required", "rejected"],
        "partnership_dependent": [
            "live_bank_account_connections", "live_mobile_money_connections",
            "external_business_registry_connections", "external_kyc_identity_connections"
        ]
    }
