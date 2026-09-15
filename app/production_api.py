import hashlib
import json
import os
import secrets
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Response, UploadFile, File, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.orm import Session
from app.models import Invoice
from app.evidence import Evidence
from app.verification import compare_invoice_to_evidence_set
from app.risk_engine import assess
from app.production_db import SessionLocal, Organization, ApiKey, Transaction, AuditEvent, Document, IntegrationCredential, IntegrationEvent
from app.document_engine import sha256_bytes, extract_pdf_text, extract_fields
from app.integrations import image_ocr, OCRProviderError, verify_webhook_signature, normalize_financial_event, webhook_secret_for

router = APIRouter(prefix="/v1", tags=["production"])

def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _hash_key(key: str) -> str:
    pepper = os.getenv("API_KEY_PEPPER")
    if not pepper:
        raise RuntimeError("API_KEY_PEPPER is required")
    return hashlib.sha256((pepper + key).encode()).hexdigest()

def _hash_secret(secret: str) -> str:
    pepper = os.getenv("API_KEY_PEPPER")
    if not pepper:
        raise RuntimeError("API_KEY_PEPPER is required")
    return hashlib.sha256((pepper + secret).encode()).hexdigest()

def require_api_key(x_api_key: str | None = Header(default=None), db: Session = Depends(db_session)) -> Organization:
    if not x_api_key:
        raise HTTPException(401, "X-API-Key header is required")
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == _hash_key(x_api_key), ApiKey.active == 1))
    if not key:
        raise HTTPException(401, "Invalid API key")
    return db.get(Organization, key.organization_id)

class ProductionTransaction(BaseModel):
    invoice: Invoice
    evidence: list[Evidence] = Field(min_length=1, max_length=100)

class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)

class KeyCreate(BaseModel):
    label: str = Field(default="api", min_length=1, max_length=100)

@router.post("/organizations", status_code=201)
def create_organization(body: OrganizationCreate, x_bootstrap_token: str | None = Header(default=None, alias="X-Bootstrap-Token"), db: Session = Depends(db_session)):
    expected = os.getenv("BOOTSTRAP_TOKEN")
    if not expected or not x_bootstrap_token or not secrets.compare_digest(x_bootstrap_token, expected):
        raise HTTPException(403, "Bootstrap authorization required")
    org = Organization(name=body.name.strip())
    db.add(org); db.flush()
    raw_key = "aft_live_" + secrets.token_urlsafe(32)
    db.add(ApiKey(organization_id=org.id, key_hash=_hash_key(raw_key), label="initial")); db.commit()
    return {"organization_id": org.id, "api_key": raw_key, "warning": "Store this API key now; it is shown only once."}

@router.post("/keys", status_code=201)
def create_key(body: KeyCreate, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    raw_key = "aft_live_" + secrets.token_urlsafe(32)
    db.add(ApiKey(organization_id=organization.id, key_hash=_hash_key(raw_key), label=body.label.strip())); db.commit()
    return {"api_key": raw_key, "label": body.label.strip(), "warning": "Store this API key now; it is shown only once."}

@router.post("/keys/{key_id}/revoke")
def revoke_key(key_id: int, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    key = db.scalar(select(ApiKey).where(ApiKey.id == key_id, ApiKey.organization_id == organization.id))
    if not key:
        raise HTTPException(404, "API key not found")
    key.active = 0; db.commit()
    return {"key_id": key_id, "revoked": True}

@router.get("/keys")
def list_keys(organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    rows = db.scalars(select(ApiKey).where(ApiKey.organization_id == organization.id).order_by(desc(ApiKey.created_at))).all()
    return {"keys": [{"id": k.id, "label": k.label, "active": bool(k.active), "created_at": k.created_at.isoformat()} for k in rows]}

@router.post("/documents", status_code=201)
def upload_document(file: UploadFile = File(...), organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    data = file.file.read()
    if not data:
        raise HTTPException(422, "Empty document")
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Document exceeds 10MB limit")
    digest = sha256_bytes(data)
    existing = db.scalar(select(Document).where(Document.organization_id == organization.id, Document.sha256 == digest))
    if existing:
        refreshed = extract_fields(existing.text or "")
        old = json.loads(existing.extraction_json or "{}")
        if old.get("method"):
            refreshed["method"] = old["method"]
        if old.get("ocr_provider"):
            refreshed["ocr_provider"] = old["ocr_provider"]
        existing.extraction_json = json.dumps(refreshed, sort_keys=True)
        db.commit()
        return {"document_id": existing.id, "duplicate": True, "refreshed": True, "sha256": digest, "extraction": refreshed}
    content_type = file.content_type or "application/octet-stream"
    if content_type == "application/pdf" or (file.filename or "").lower().endswith(".pdf"):
        try:
            text = extract_pdf_text(data)
            extraction = extract_fields(text)
            extraction["method"] = "pdf_text"
        except Exception as exc:
            raise HTTPException(422, f"PDF extraction failed: {type(exc).__name__}")
    elif content_type.startswith("image/"):
        try:
            ocr = image_ocr(data, content_type)
            text = ocr["text"]
            extraction = extract_fields(text)
            extraction["method"] = "ocr"
            extraction["ocr_provider"] = ocr["provider"]
        except OCRProviderError as exc:
            raise HTTPException(503, str(exc))
    elif content_type.startswith("text/") or (file.filename or "").lower().endswith((".txt", ".csv")):
        text = data.decode("utf-8", errors="replace")
        extraction = extract_fields(text)
        extraction["method"] = "text"
    else:
        raise HTTPException(415, "Supported document types: PDF, images, and text/CSV")
    doc_id = uuid.uuid4().hex
    db.add(Document(id=doc_id, organization_id=organization.id, filename=(file.filename or "document")[:255], content_type=content_type, sha256=digest, text=text, extraction_json=json.dumps(extraction, sort_keys=True)))
    db.commit()
    return {"document_id": doc_id, "duplicate": False, "sha256": digest, "filename": file.filename, "extraction": extraction}

@router.get("/documents")
def list_documents(organization: Organization = Depends(require_api_key), db: Session = Depends(db_session), limit: int = 50):
    limit = max(1, min(limit, 100))
    rows = db.scalars(select(Document).where(Document.organization_id == organization.id).order_by(desc(Document.created_at)).limit(limit)).all()
    return {"count": len(rows), "documents": [{"document_id": d.id, "filename": d.filename, "content_type": d.content_type, "sha256": d.sha256, "extraction": json.loads(d.extraction_json), "created_at": d.created_at.isoformat()} for d in rows]}

@router.post("/integrations/{provider}", status_code=201)
def create_integration(provider: str, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    provider = provider.strip().lower()
    if not provider or len(provider) > 100 or not provider.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(422, "Invalid provider name")
    existing = db.scalar(select(IntegrationCredential).where(IntegrationCredential.organization_id == organization.id, IntegrationCredential.provider == provider, IntegrationCredential.active == 1))
    if existing:
        raise HTTPException(409, "Active integration already exists; rotate/revoke it before creating another")
    secret = webhook_secret_for(organization.id, provider)
    db.add(IntegrationCredential(organization_id=organization.id, provider=provider, secret_hash=_hash_secret(secret), active=1)); db.commit()
    return {"provider": provider, "webhook_secret": secret, "webhook_url": f"/v1/integrations/{provider}/webhook", "signature_header": "X-Webhook-Signature", "signature_format": "sha256=<hex-hmac-sha256-body>", "warning": "Store the webhook secret now; it is shown only once."}

@router.get("/integrations")
def list_integrations(organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    rows = db.scalars(select(IntegrationCredential).where(IntegrationCredential.organization_id == organization.id).order_by(desc(IntegrationCredential.created_at))).all()
    return {"integrations": [{"id": x.id, "provider": x.provider, "active": bool(x.active), "created_at": x.created_at.isoformat()} for x in rows]}

@router.post("/integrations/{provider}/webhook", status_code=202)
async def receive_financial_webhook(provider: str, request: Request, x_organization_id: int | None = Header(default=None, alias="X-Organization-ID"), x_webhook_signature: str | None = Header(default=None, alias="X-Webhook-Signature"), db: Session = Depends(db_session)):
    if not x_organization_id:
        raise HTTPException(400, "X-Organization-ID header is required")
    provider = provider.strip().lower()
    credential = db.scalar(select(IntegrationCredential).where(IntegrationCredential.organization_id == x_organization_id, IntegrationCredential.provider == provider, IntegrationCredential.active == 1))
    if not credential:
        raise HTTPException(404, "Active integration not found")
    raw = await request.body()
    payload_signature = (x_webhook_signature or "").removeprefix("sha256=").strip()
    if len(payload_signature) != 64:
        raise HTTPException(401, "Invalid webhook signature")
    payload = hashlib.sha256(raw).hexdigest()
    secret = webhook_secret_for(x_organization_id, provider)
    if not verify_webhook_signature(raw, x_webhook_signature, secret):
        raise HTTPException(401, "Invalid webhook signature")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(400, "Webhook body must be valid JSON")
    if not isinstance(body, dict):
        raise HTTPException(400, "Webhook JSON must be an object")
    normalized = normalize_financial_event(provider, body)
    event_key = str(normalized.get("provider_transaction_id") or normalized.get("reference") or payload)
    event_type = str(body.get("event_type") or body.get("type") or "financial.transaction")
    existing = db.scalar(select(IntegrationEvent).where(IntegrationEvent.organization_id == x_organization_id, IntegrationEvent.provider == provider, IntegrationEvent.event_key == event_key))
    if existing:
        return {"accepted": True, "duplicate": True, "event_id": existing.id, "normalized": json.loads(existing.normalized_json)}
    event = IntegrationEvent(id=uuid.uuid4().hex, organization_id=x_organization_id, provider=provider, event_key=event_key, event_type=event_type, normalized_json=json.dumps(normalized, sort_keys=True))
    db.add(event); db.commit()
    return {"accepted": True, "duplicate": False, "event_id": event.id, "normalized": normalized}

@router.get("/integrations/events")
def list_integration_events(organization: Organization = Depends(require_api_key), db: Session = Depends(db_session), limit: int = 100):
    limit = max(1, min(limit, 200))
    rows = db.scalars(select(IntegrationEvent).where(IntegrationEvent.organization_id == organization.id).order_by(desc(IntegrationEvent.received_at)).limit(limit)).all()
    return {"count": len(rows), "events": [{"event_id": e.id, "provider": e.provider, "event_type": e.event_type, "event_key": e.event_key, "normalized": json.loads(e.normalized_json), "received_at": e.received_at.isoformat()} for e in rows]}

@router.post("/transactions", status_code=201)
def create_transaction(body: ProductionTransaction, response: Response, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    if idempotency_key:
        existing = db.scalar(select(Transaction).where(Transaction.organization_id == organization.id, Transaction.idempotency_key == idempotency_key))
        if existing:
            response.status_code = 200
            return _transaction_response(existing, db)
    evidence_ids = [e.evidence_id for e in body.evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise HTTPException(422, "evidence_id values must be unique")
    duplicate = db.scalar(select(Transaction).where(Transaction.organization_id == organization.id, Transaction.invoice_number == body.invoice.invoice_number)) is not None
    verification = compare_invoice_to_evidence_set(body.invoice, body.evidence)
    risk = assess(body.invoice, body.evidence, duplicate=duplicate)
    decision = "verified" if verification["status"] == "verified" and risk["decision"] == "approve" else ("rejected" if risk["decision"] == "reject" else "review_required")
    verification["risk"] = risk
    tx = Transaction(id=uuid.uuid4().hex, organization_id=organization.id, invoice_number=body.invoice.invoice_number, payload=json.dumps(body.model_dump(mode="json")), status=decision, idempotency_key=idempotency_key)
    db.add(tx); db.flush()
    previous = db.scalar(select(AuditEvent).where(AuditEvent.organization_id == organization.id).order_by(desc(AuditEvent.id)))
    previous_hash = previous.event_hash if previous else "0" * 64
    result_json = json.dumps(verification, sort_keys=True, separators=(",", ":"))
    canonical = f"{previous_hash}|{tx.id}|{decision}|{verification['verification_score']}|{result_json}"
    event_hash = hashlib.sha256(canonical.encode()).hexdigest()
    db.add(AuditEvent(organization_id=organization.id, transaction_id=tx.id, decision=decision, score=verification["verification_score"], result_json=result_json, previous_hash=previous_hash, event_hash=event_hash)); db.commit()
    return _transaction_response(tx, db)

def _transaction_response(tx: Transaction, db: Session):
    audit = db.scalar(select(AuditEvent).where(AuditEvent.transaction_id == tx.id).order_by(desc(AuditEvent.id)))
    return {"transaction_id": tx.id, "invoice_number": tx.invoice_number, "status": tx.status, "audit_id": audit.id if audit else None, "audit_hash": audit.event_hash if audit else None, "verification": json.loads(audit.result_json) if audit else None, "created_at": tx.created_at.isoformat()}

@router.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: str, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    tx = db.scalar(select(Transaction).where(Transaction.id == transaction_id, Transaction.organization_id == organization.id))
    if not tx:
        raise HTTPException(404, "Transaction not found")
    return _transaction_response(tx, db)

@router.get("/transactions")
def list_transactions(organization: Organization = Depends(require_api_key), db: Session = Depends(db_session), limit: int = 50):
    limit = max(1, min(limit, 100)); rows = db.scalars(select(Transaction).where(Transaction.organization_id == organization.id).order_by(desc(Transaction.created_at)).limit(limit)).all()
    return {"count": len(rows), "transactions": [_transaction_response(row, db) for row in rows]}

@router.get("/audits/{transaction_id}")
def get_audit(transaction_id: str, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    audit = db.scalar(select(AuditEvent).where(AuditEvent.transaction_id == transaction_id, AuditEvent.organization_id == organization.id).order_by(desc(AuditEvent.id)))
    if not audit:
        raise HTTPException(404, "Audit record not found")
    return {"audit_id": audit.id, "transaction_id": transaction_id, "decision": audit.decision, "score": float(audit.score), "previous_hash": audit.previous_hash, "event_hash": audit.event_hash, "result": json.loads(audit.result_json), "created_at": audit.created_at.isoformat()}
