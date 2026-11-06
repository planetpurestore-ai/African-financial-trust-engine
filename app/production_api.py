import hashlib
import json
import os
import secrets
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Response, UploadFile, File, Request
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy import select, desc, text, func
from sqlalchemy.orm import Session
from app.models import Invoice
from app.evidence import Evidence
from app.verification import compare_invoice_to_evidence_set
from app.risk_engine import assess, DEFAULT_RISK_SETTINGS
from app.production_db import SessionLocal, Organization, OrganizationRiskSettings, ApiKey, Transaction, AuditEvent, ReviewDecision, Document, IntegrationCredential, IntegrationEvent
from app.document_engine import sha256_bytes, extract_pdf_text, extract_fields, inspect_document_integrity, classify_document
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

class ShareLinkCreate(BaseModel):
    expires_in_hours: int = Field(default=72, ge=1, le=720)

class BulkTransactionItem(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=255)
    transaction: ProductionTransaction


class BulkTransactionRequest(BaseModel):
    items: list[BulkTransactionItem] = Field(min_length=1, max_length=50)


class ReviewDecisionCreate(BaseModel):
    decision: Literal["accepted_for_further_processing", "rejected"]
    reason: str = Field(min_length=10, max_length=2000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("reason must contain at least 10 non-whitespace characters")
        return value


class RiskSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    require_commercial_evidence: bool | None = None
    require_payment_evidence: bool | None = None
    reject_duplicate_invoice: bool | None = None
    reject_payment_mismatch: bool | None = None
    reject_counterparty_conflict: bool | None = None
    manual_review_amount_threshold: Decimal | None = Field(default=None, ge=0)


def _risk_settings_for_org(db: Session, organization_id: int) -> dict:
    row = db.get(OrganizationRiskSettings, organization_id)
    if not row:
        return dict(DEFAULT_RISK_SETTINGS)
    try:
        stored = json.loads(row.settings_json or "{}")
    except (TypeError, json.JSONDecodeError):
        stored = {}
    return {**DEFAULT_RISK_SETTINGS, **stored}


@router.get("/risk-settings")
def get_risk_settings(
    organization: Organization = Depends(require_api_key),
    db: Session = Depends(db_session),
):
    return {"settings": _risk_settings_for_org(db, organization.id)}


@router.put("/risk-settings")
def update_risk_settings(
    body: RiskSettingsUpdate,
    organization: Organization = Depends(require_api_key),
    db: Session = Depends(db_session),
):
    settings = _risk_settings_for_org(db, organization.id)
    settings.update(body.model_dump(mode="json", exclude_unset=True))
    row = db.get(OrganizationRiskSettings, organization.id)
    if row:
        row.settings_json = json.dumps(settings, sort_keys=True)
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(OrganizationRiskSettings(
            organization_id=organization.id,
            settings_json=json.dumps(settings, sort_keys=True),
            updated_at=datetime.now(timezone.utc),
        ))
    db.commit()
    return {"settings": settings, "updated": True}


def _share_token_hash(token: str) -> str:
    pepper = os.getenv("API_KEY_PEPPER")
    if not pepper:
        raise RuntimeError("API_KEY_PEPPER is required")
    return hashlib.sha256(("trust-record-share:" + pepper + token).encode()).hexdigest()


def _ensure_share_link_table(db: Session) -> None:
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS transaction_share_links (
            id VARCHAR(64) PRIMARY KEY,
            organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            transaction_id VARCHAR(64) NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
            token_hash VARCHAR(64) NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0,
            access_count INTEGER NOT NULL DEFAULT 0,
            last_accessed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.commit()


def _as_utc_datetime(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    raise ValueError("Invalid stored timestamp")


def _trust_record_payload(tx: Transaction, db: Session) -> dict:
    audits = db.scalars(select(AuditEvent).where(
        AuditEvent.transaction_id == tx.id,
        AuditEvent.organization_id == tx.organization_id,
    ).order_by(desc(AuditEvent.id))).all()
    latest_audit = audits[0] if audits else None
    machine_audit = next((item for item in audits if not item.decision.startswith("manual_review:")), None)
    latest_review = db.scalar(select(ReviewDecision).where(
        ReviewDecision.transaction_id == tx.id,
        ReviewDecision.organization_id == tx.organization_id,
    ).order_by(desc(ReviewDecision.created_at)))
    try:
        payload = json.loads(tx.payload or "{}")
        invoice = payload.get("invoice") or {}
        evidence = payload.get("evidence") or []
    except (TypeError, json.JSONDecodeError):
        raise HTTPException(500, "Stored transaction payload could not be read")
    return {
        "record_type": "african_financial_trust.trust_record",
        "record_version": "1.0",
        "issuer": "African Financial Trust",
        "transaction_id": tx.id,
        "invoice_number": tx.invoice_number,
        "status": tx.status,
        "invoice": invoice,
        "evidence_submitted": evidence,
        "verification": json.loads(machine_audit.result_json) if machine_audit else None,
        "human_review": {
            "decision": latest_review.decision,
            "reason": latest_review.reason,
            "reviewer_api_key_id": latest_review.reviewer_api_key_id,
            "created_at": latest_review.created_at.isoformat(),
        } if latest_review else None,
        "audit": {
            "audit_id": latest_audit.id if latest_audit else None,
            "previous_hash": latest_audit.previous_hash if latest_audit else None,
            "event_hash": latest_audit.event_hash if latest_audit else None,
            "created_at": latest_audit.created_at.isoformat() if latest_audit else None,
        },
        "created_at": tx.created_at.isoformat(),
        "limitations": [
            "This record reports checks performed on evidence submitted to the Trust Engine.",
            "It is not a lending decision, credit rating, guarantee, or proof that an underlying transaction is genuine.",
            "A human review disposition is recorded separately and does not rewrite the machine verification result.",
            "External source authority is only established when an authorised provider integration independently verifies the source.",
        ],
    }

@router.post("/organizations", status_code=201)
def create_organization(body: OrganizationCreate, x_bootstrap_token: str | None = Header(default=None, alias="X-Bootstrap-Token"), db: Session = Depends(db_session)):
    expected = os.getenv("BOOTSTRAP_TOKEN")
    if not expected or not x_bootstrap_token or not secrets.compare_digest(x_bootstrap_token, expected):
        raise HTTPException(403, "Bootstrap authorization required")
    org = Organization(name=body.name.strip())
    db.add(org); db.flush()
    raw_key = "aft_live_" + secrets.token_urlsafe(32)
    db.add(ApiKey(organization_id=org.id, key_hash=_hash_key(raw_key), label="initial")); db.commit()
    return {"organization": {"id": org.id, "name": org.name, "created_at": org.created_at.isoformat()}, "organization_id": org.id, "api_key": raw_key, "warning": "Store this API key now; it is shown only once."}

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
async def upload_document(file: UploadFile = File(...), organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    # Read at most one byte beyond the limit. Checking size after an unbounded
    # read allows a large upload to exhaust worker memory before it is rejected.
    max_bytes = 10 * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if not data:
        raise HTTPException(422, "Empty document")
    if len(data) > max_bytes:
        raise HTTPException(413, "Document exceeds 10MB limit")

    content_type = (file.content_type or "application/octet-stream").lower().split(";", 1)[0].strip()
    filename = (file.filename or "document")[:255]
    is_pdf = data.startswith(b"%PDF-")
    is_png = data.startswith(bytes.fromhex("89504e470d0a1a0a"))
    is_jpeg = data.startswith(bytes.fromhex("ffd8ff"))
    is_gif = data.startswith((b"GIF87a", b"GIF89a"))
    is_webp = len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"

    if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
        if not is_pdf:
            raise HTTPException(415, "File content does not match PDF type")
    elif content_type.startswith("image/"):
        supported_image = (
            (content_type == "image/png" and is_png)
            or (content_type in {"image/jpeg", "image/jpg"} and is_jpeg)
            or (content_type == "image/gif" and is_gif)
            or (content_type == "image/webp" and is_webp)
        )
        if not supported_image:
            raise HTTPException(415, "Unsupported or mismatched image type; use PNG, JPEG, GIF, or WebP")
    elif not (content_type.startswith("text/") or filename.lower().endswith((".txt", ".csv"))):
        raise HTTPException(415, "Supported document types: PDF, PNG/JPEG/GIF/WebP images, and text/CSV")

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
        if existing.category == "other":
            existing.category = classify_document(filename, existing.text or "")
        db.commit()
        return {"document_id": existing.id, "duplicate": True, "refreshed": True, "sha256": digest, "category": existing.category, "extraction": refreshed}

    if is_pdf:
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
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(415, "Text documents must use UTF-8 encoding")
        extraction = extract_fields(text)
        extraction["method"] = "text"

    integrity = inspect_document_integrity(data, content_type)
    extraction["integrity"] = integrity
    if integrity["signals"]:
        extraction["requires_review"] = True
        extraction.setdefault("review_reasons", []).extend(
            f"document_integrity:{signal}" for signal in integrity["signals"]
        )

    doc_id = uuid.uuid4().hex
    category = classify_document(filename, text)
    db.add(Document(id=doc_id, organization_id=organization.id, filename=filename, content_type=content_type, category=category, sha256=digest, text=text, extraction_json=json.dumps(extraction, sort_keys=True)))
    db.commit()
    return {"document_id": doc_id, "duplicate": False, "sha256": digest, "filename": filename, "category": category, "extraction": extraction}

@router.post("/documents/batch")
async def upload_documents_batch(
    files: list[UploadFile] = File(...),
    organization: Organization = Depends(require_api_key),
    db: Session = Depends(db_session),
):
    """Upload up to ten documents with explicit per-file success/failure results."""
    if not files or len(files) > 10:
        raise HTTPException(422, "Submit between 1 and 10 documents per batch")
    results = []
    for file in files:
        try:
            result = await upload_document(file, organization, db)
            results.append({"filename": file.filename, "success": True, "result": result})
        except HTTPException as exc:
            results.append({
                "filename": file.filename,
                "success": False,
                "status_code": exc.status_code,
                "error": exc.detail,
            })
    return {
        "count": len(results),
        "successful": sum(1 for item in results if item["success"]),
        "failed": sum(1 for item in results if not item["success"]),
        "results": results,
    }


@router.get("/documents")
def list_documents(organization: Organization = Depends(require_api_key), db: Session = Depends(db_session), limit: int = 50):
    limit = max(1, min(limit, 100)); rows = db.scalars(select(Document).where(Document.organization_id == organization.id).order_by(desc(Document.created_at)).limit(limit)).all()
    return {"count": len(rows), "documents": [{"document_id": d.id, "filename": d.filename, "content_type": d.content_type, "category": d.category, "sha256": d.sha256, "extraction": json.loads(d.extraction_json), "created_at": d.created_at.isoformat()} for d in rows]}

@router.post("/integrations/{provider}", status_code=201)
def create_integration(provider: str, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    provider = provider.strip().lower()
    if not provider or len(provider) > 100 or not provider.replace("_", "").replace("-", "").isalnum(): raise HTTPException(422, "Invalid provider name")
    existing = db.scalar(select(IntegrationCredential).where(IntegrationCredential.organization_id == organization.id, IntegrationCredential.provider == provider, IntegrationCredential.active == 1))
    if existing: raise HTTPException(409, "Active integration already exists; rotate/revoke it before creating another")
    secret = webhook_secret_for(organization.id, provider)
    db.add(IntegrationCredential(organization_id=organization.id, provider=provider, secret_hash=_hash_secret(secret), active=1)); db.commit()
    return {"provider": provider, "webhook_secret": secret, "webhook_url": f"/v1/integrations/{provider}/webhook", "signature_header": "X-Webhook-Signature", "signature_format": "sha256=<hex-hmac-sha256-body>", "warning": "Store the webhook secret now; it is shown only once."}

@router.get("/integrations")
def list_integrations(organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    rows = db.scalars(select(IntegrationCredential).where(IntegrationCredential.organization_id == organization.id).order_by(desc(IntegrationCredential.created_at))).all()
    return {"integrations": [{"id": x.id, "provider": x.provider, "active": bool(x.active), "created_at": x.created_at.isoformat()} for x in rows]}

@router.post("/integrations/{provider}/webhook", status_code=202)
async def receive_financial_webhook(provider: str, request: Request, x_organization_id: int | None = Header(default=None, alias="X-Organization-ID"), x_webhook_signature: str | None = Header(default=None, alias="X-Webhook-Signature"), db: Session = Depends(db_session)):
    if not x_organization_id: raise HTTPException(400, "X-Organization-ID header is required")
    provider = provider.strip().lower(); credential = db.scalar(select(IntegrationCredential).where(IntegrationCredential.organization_id == x_organization_id, IntegrationCredential.provider == provider, IntegrationCredential.active == 1))
    if not credential: raise HTTPException(404, "Active integration not found")
    raw = await request.body(); payload_signature = (x_webhook_signature or "").removeprefix("sha256=").strip()
    if len(payload_signature) != 64: raise HTTPException(401, "Invalid webhook signature")
    payload = hashlib.sha256(raw).hexdigest(); secret = webhook_secret_for(x_organization_id, provider)
    if not verify_webhook_signature(raw, x_webhook_signature, secret): raise HTTPException(401, "Invalid webhook signature")
    try: body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError): raise HTTPException(400, "Webhook body must be valid JSON")
    if not isinstance(body, dict): raise HTTPException(400, "Webhook JSON must be an object")
    normalized = normalize_financial_event(provider, body); event_key = str(normalized.get("provider_transaction_id") or normalized.get("reference") or payload); event_type = str(body.get("event_type") or body.get("type") or "financial.transaction")
    existing = db.scalar(select(IntegrationEvent).where(IntegrationEvent.organization_id == x_organization_id, IntegrationEvent.provider == provider, IntegrationEvent.event_key == event_key))
    if existing: return {"accepted": True, "duplicate": True, "event_id": existing.id, "normalized": json.loads(existing.normalized_json)}
    event = IntegrationEvent(id=uuid.uuid4().hex, organization_id=x_organization_id, provider=provider, event_key=event_key, event_type=event_type, normalized_json=json.dumps(normalized, sort_keys=True)); db.add(event); db.commit()
    return {"accepted": True, "duplicate": False, "event_id": event.id, "normalized": normalized}

@router.get("/integrations/events")
def list_integration_events(organization: Organization = Depends(require_api_key), db: Session = Depends(db_session), limit: int = 100):
    limit = max(1, min(limit, 200)); rows = db.scalars(select(IntegrationEvent).where(IntegrationEvent.organization_id == organization.id).order_by(desc(IntegrationEvent.received_at)).limit(limit)).all()
    return {"count": len(rows), "events": [{"event_id": e.id, "provider": e.provider, "event_type": e.event_type, "event_key": e.event_key, "normalized": json.loads(e.normalized_json), "received_at": e.received_at.isoformat()} for e in rows]}

@router.post("/transactions", status_code=201)
def create_transaction(body: ProductionTransaction, response: Response, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    # Serialize transaction intake per organization on PostgreSQL. This makes
    # idempotency checks, duplicate detection, and audit-chain append atomic
    # with respect to other requests for the same organization.
    db.execute(select(Organization).where(Organization.id == organization.id).with_for_update()).scalar_one()
    normalized_payload = body.model_dump(mode="json")
    if idempotency_key:
        if len(idempotency_key) > 255 or not idempotency_key.strip():
            raise HTTPException(422, "Idempotency-Key must contain 1–255 non-whitespace characters")
        existing = db.scalar(select(Transaction).where(Transaction.organization_id == organization.id, Transaction.idempotency_key == idempotency_key))
        if existing:
            if json.loads(existing.payload or "{}") != normalized_payload:
                raise HTTPException(409, "Idempotency-Key was already used with a different request payload")
            response.status_code = 200
            return _transaction_response(existing, db)
    evidence_ids = [e.evidence_id for e in body.evidence]
    if len(evidence_ids) != len(set(evidence_ids)): raise HTTPException(422, "evidence_id values must be unique")
    duplicate = db.scalar(select(Transaction).where(
        Transaction.organization_id == organization.id,
        func.lower(Transaction.invoice_number) == body.invoice.invoice_number.casefold(),
    )) is not None
    risk_settings = _risk_settings_for_org(db, organization.id)
    verification = compare_invoice_to_evidence_set(body.invoice, body.evidence, policy=risk_settings)
    risk = assess(body.invoice, body.evidence, duplicate=duplicate, settings=risk_settings)
    decision = "verified" if verification["status"] == "verified" and risk["decision"] == "approve" else ("rejected" if risk["decision"] == "reject" else "review_required"); verification["risk"] = risk
    tx = Transaction(id=uuid.uuid4().hex, organization_id=organization.id, invoice_number=body.invoice.invoice_number, payload=json.dumps(body.model_dump(mode="json")), status=decision, idempotency_key=idempotency_key); db.add(tx); db.flush()
    previous = db.scalar(select(AuditEvent).where(AuditEvent.organization_id == organization.id).order_by(desc(AuditEvent.id))); previous_hash = previous.event_hash if previous else "0" * 64
    result_json = json.dumps(verification, sort_keys=True, separators=(",", ":")); canonical = f"{previous_hash}|{tx.id}|{decision}|{verification['verification_score']}|{result_json}"; event_hash = hashlib.sha256(canonical.encode()).hexdigest()
    db.add(AuditEvent(organization_id=organization.id, transaction_id=tx.id, decision=decision, score=verification["verification_score"], result_json=result_json, previous_hash=previous_hash, event_hash=event_hash)); db.commit()
    return _transaction_response(tx, db)

@router.post("/transactions/batch")
def create_transactions_batch(
    body: BulkTransactionRequest,
    organization: Organization = Depends(require_api_key),
    db: Session = Depends(db_session),
):
    results = []
    for item in body.items:
        item_response = Response(status_code=201)
        try:
            result = create_transaction(
                item.transaction,
                item_response,
                organization,
                db,
                item.idempotency_key,
            )
            results.append({
                "success": True,
                "status_code": item_response.status_code,
                "idempotency_key": item.idempotency_key,
                "transaction": result,
            })
        except HTTPException as exc:
            db.rollback()
            results.append({
                "success": False,
                "status_code": exc.status_code,
                "idempotency_key": item.idempotency_key,
                "error": exc.detail,
            })
    return {
        "count": len(results),
        "successful": sum(1 for result in results if result["success"]),
        "failed": sum(1 for result in results if not result["success"]),
        "results": results,
    }


def _transaction_response(tx: Transaction, db: Session):
    audit = db.scalar(select(AuditEvent).where(AuditEvent.transaction_id == tx.id).order_by(desc(AuditEvent.id)))
    try:
        payload = json.loads(tx.payload or "{}")
        invoice = payload.get("invoice") or {}
    except (TypeError, json.JSONDecodeError):
        invoice = {}
    return {
        "transaction_id": tx.id,
        "invoice_number": tx.invoice_number,
        "status": tx.status,
        "supplier_name": invoice.get("supplier_name"),
        "buyer_name": invoice.get("buyer_name"),
        "amount": invoice.get("amount"),
        "currency": invoice.get("currency"),
        "issue_date": invoice.get("issue_date"),
        "due_date": invoice.get("due_date"),
        "audit_id": audit.id if audit else None,
        "audit_hash": audit.event_hash if audit else None,
        "verification": json.loads(audit.result_json) if audit else None,
        "created_at": tx.created_at.isoformat()
    }

@router.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: str, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    tx = db.scalar(select(Transaction).where(Transaction.id == transaction_id, Transaction.organization_id == organization.id))
    if not tx: raise HTTPException(404, "Transaction not found")
    return _transaction_response(tx, db)

@router.get("/transactions/{transaction_id}/trust-record")
def download_trust_record(transaction_id: str, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    """Download a versioned, auditable JSON record for an organisation's transaction."""
    tx = db.scalar(select(Transaction).where(Transaction.id == transaction_id, Transaction.organization_id == organization.id))
    if not tx:
        raise HTTPException(404, "Transaction not found")
    record = _trust_record_payload(tx, db)
    filename = f"aft-trust-record-{tx.id}.json"
    return Response(
        content=json.dumps(record, sort_keys=True, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



@router.post("/transactions/{transaction_id}/share-links", status_code=201)
def create_trust_record_share(
    transaction_id: str,
    body: ShareLinkCreate,
    organization: Organization = Depends(require_api_key),
    db: Session = Depends(db_session),
):
    tx = db.scalar(select(Transaction).where(
        Transaction.id == transaction_id,
        Transaction.organization_id == organization.id,
    ))
    if not tx:
        raise HTTPException(404, "Transaction not found")
    _ensure_share_link_table(db)
    raw_token = "aft_share_" + secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=body.expires_in_hours)
    share_id = uuid.uuid4().hex
    db.execute(text("""
        INSERT INTO transaction_share_links
        (id, organization_id, transaction_id, token_hash, expires_at, revoked, access_count)
        VALUES (:i, :o, :t, :h, :e, 0, 0)
    """), {
        "i": share_id,
        "o": organization.id,
        "t": tx.id,
        "h": _share_token_hash(raw_token),
        "e": expires_at.isoformat(),
    })
    db.commit()
    return {
        "share_id": share_id,
        "share_path": f"/v1/shared/trust-records/{raw_token}",
        "expires_at": expires_at.isoformat(),
        "warning": "The share token is shown only once. Anyone holding it can view this Trust Record until it expires or is revoked.",
    }


@router.get("/transactions/{transaction_id}/share-links")
def list_trust_record_shares(
    transaction_id: str,
    organization: Organization = Depends(require_api_key),
    db: Session = Depends(db_session),
):
    tx = db.scalar(select(Transaction).where(
        Transaction.id == transaction_id,
        Transaction.organization_id == organization.id,
    ))
    if not tx:
        raise HTTPException(404, "Transaction not found")
    _ensure_share_link_table(db)
    rows = db.execute(text("""
        SELECT id, expires_at, revoked, access_count, last_accessed_at, created_at
        FROM transaction_share_links
        WHERE organization_id=:o AND transaction_id=:t
        ORDER BY created_at DESC
    """), {"o": organization.id, "t": tx.id}).mappings().all()
    return {"share_links": [dict(row) for row in rows]}


@router.post("/transactions/{transaction_id}/share-links/{share_id}/revoke")
def revoke_trust_record_share(
    transaction_id: str,
    share_id: str,
    organization: Organization = Depends(require_api_key),
    db: Session = Depends(db_session),
):
    _ensure_share_link_table(db)
    result = db.execute(text("""
        UPDATE transaction_share_links
        SET revoked=1
        WHERE id=:s AND transaction_id=:t AND organization_id=:o
    """), {"s": share_id, "t": transaction_id, "o": organization.id})
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Share link not found")
    return {"share_id": share_id, "revoked": True}


@router.get("/shared/trust-records/{token}")
def access_shared_trust_record(token: str, db: Session = Depends(db_session)):
    _ensure_share_link_table(db)
    row = db.execute(text("""
        SELECT id, organization_id, transaction_id, expires_at, revoked
        FROM transaction_share_links
        WHERE token_hash=:h
    """), {"h": _share_token_hash(token)}).mappings().first()
    if not row or row["revoked"]:
        raise HTTPException(404, "Share link not found or revoked")
    try:
        expires_at = _as_utc_datetime(row["expires_at"])
    except (TypeError, ValueError):
        raise HTTPException(404, "Share link not found or expired")
    if expires_at <= datetime.now(timezone.utc):
        raise HTTPException(404, "Share link not found or expired")
    tx = db.scalar(select(Transaction).where(
        Transaction.id == row["transaction_id"],
        Transaction.organization_id == row["organization_id"],
    ))
    if not tx:
        raise HTTPException(404, "Share link not found")
    db.execute(text("""
        UPDATE transaction_share_links
        SET access_count=access_count+1, last_accessed_at=:now
        WHERE id=:i
    """), {"now": datetime.now(timezone.utc).isoformat(), "i": row["id"]})
    db.commit()
    return _trust_record_payload(tx, db)


@router.get("/reviews")
def list_review_queue(
    organization: Organization = Depends(require_api_key),
    db: Session = Depends(db_session),
    limit: int = 50,
):
    limit = max(1, min(limit, 100))
    transactions = db.scalars(select(Transaction).where(
        Transaction.organization_id == organization.id,
        Transaction.status == "review_required",
    ).order_by(Transaction.created_at.asc()).limit(limit)).all()
    items = []
    for tx in transactions:
        audit = db.scalar(select(AuditEvent).where(
            AuditEvent.transaction_id == tx.id,
            AuditEvent.organization_id == organization.id,
            ~AuditEvent.decision.startswith("manual_review:"),
        ).order_by(desc(AuditEvent.id)))
        review = db.scalar(select(ReviewDecision).where(
            ReviewDecision.transaction_id == tx.id,
            ReviewDecision.organization_id == organization.id,
        ).order_by(desc(ReviewDecision.created_at)))
        result = json.loads(audit.result_json) if audit else {}
        items.append({
            "transaction_id": tx.id,
            "invoice_number": tx.invoice_number,
            "status": tx.status,
            "failed_checks": result.get("failed_checks", []),
            "risk": result.get("risk"),
            "latest_human_decision": review.decision if review else None,
            "created_at": tx.created_at.isoformat(),
        })
    return {"count": len(items), "reviews": items}


@router.get("/reviews/{transaction_id}")
def get_review_history(
    transaction_id: str,
    organization: Organization = Depends(require_api_key),
    db: Session = Depends(db_session),
):
    tx = db.scalar(select(Transaction).where(
        Transaction.id == transaction_id,
        Transaction.organization_id == organization.id,
    ))
    if not tx:
        raise HTTPException(404, "Transaction not found")
    rows = db.scalars(select(ReviewDecision).where(
        ReviewDecision.transaction_id == tx.id,
        ReviewDecision.organization_id == organization.id,
    ).order_by(desc(ReviewDecision.created_at))).all()
    return {
        "transaction_id": tx.id,
        "machine_status": tx.status,
        "review_history": [{
            "decision": row.decision,
            "reason": row.reason,
            "reviewer_api_key_id": row.reviewer_api_key_id,
            "created_at": row.created_at.isoformat(),
        } for row in rows],
    }


@router.post("/reviews/{transaction_id}/decision", status_code=201)
def record_review_decision(
    transaction_id: str,
    body: ReviewDecisionCreate,
    x_api_key: str = Header(alias="X-API-Key"),
    organization: Organization = Depends(require_api_key),
    db: Session = Depends(db_session),
):
    db.execute(select(Organization).where(Organization.id == organization.id).with_for_update()).scalar_one()
    tx = db.scalar(select(Transaction).where(
        Transaction.id == transaction_id,
        Transaction.organization_id == organization.id,
    ))
    if not tx:
        raise HTTPException(404, "Transaction not found")
    if tx.status != "review_required":
        raise HTTPException(409, "Only review-required transactions can receive a human disposition")
    reviewer = db.scalar(select(ApiKey).where(
        ApiKey.key_hash == _hash_key(x_api_key),
        ApiKey.organization_id == organization.id,
        ApiKey.active == 1,
    ))
    if not reviewer:
        raise HTTPException(401, "Reviewer API key is invalid")
    machine_audit = db.scalar(select(AuditEvent).where(
        AuditEvent.transaction_id == tx.id,
        AuditEvent.organization_id == organization.id,
        ~AuditEvent.decision.startswith("manual_review:"),
    ).order_by(desc(AuditEvent.id)))
    latest_org_audit = db.scalar(select(AuditEvent).where(
        AuditEvent.organization_id == organization.id,
    ).order_by(desc(AuditEvent.id)))
    previous_hash = latest_org_audit.event_hash if latest_org_audit else "GENESIS"
    score = float(machine_audit.score) if machine_audit else 0.0
    created_at = datetime.now(timezone.utc)
    result = {
        "event_type": "human_review_disposition",
        "transaction_id": tx.id,
        "machine_status": tx.status,
        "decision": body.decision,
        "reason": body.reason,
        "reviewer_api_key_id": reviewer.id,
        "created_at": created_at.isoformat(),
    }
    result_json = json.dumps(result, sort_keys=True, separators=(",", ":"))
    decision_label = f"manual_review:{body.decision}"
    canonical = f"{previous_hash}|{tx.id}|{decision_label}|{score}|{result_json}"
    event_hash = hashlib.sha256(canonical.encode()).hexdigest()
    review_id = uuid.uuid4().hex
    db.add(ReviewDecision(
        id=review_id,
        organization_id=organization.id,
        transaction_id=tx.id,
        reviewer_api_key_id=reviewer.id,
        decision=body.decision,
        reason=body.reason,
        created_at=created_at,
    ))
    db.add(AuditEvent(
        organization_id=organization.id,
        transaction_id=tx.id,
        decision=decision_label,
        score=score,
        result_json=result_json,
        previous_hash=previous_hash,
        event_hash=event_hash,
        created_at=created_at,
    ))
    db.commit()
    return {
        "review_id": review_id,
        "transaction_id": tx.id,
        "machine_status": tx.status,
        "human_decision": body.decision,
        "reason": body.reason,
        "audit_hash": event_hash,
        "created_at": created_at.isoformat(),
    }


@router.get("/transactions")
def list_transactions(organization: Organization = Depends(require_api_key), db: Session = Depends(db_session), limit: int = 50):
    limit = max(1, min(limit, 100)); rows = db.scalars(select(Transaction).where(Transaction.organization_id == organization.id).order_by(desc(Transaction.created_at)).limit(limit)).all()
    return {"count": len(rows), "transactions": [_transaction_response(row, db) for row in rows]}

@router.get("/audits/{transaction_id}")
def get_audit(transaction_id: str, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    audit = db.scalar(select(AuditEvent).where(AuditEvent.transaction_id == transaction_id, AuditEvent.organization_id == organization.id).order_by(desc(AuditEvent.id)))
    if not audit: raise HTTPException(404, "Audit record not found")
    return {"audit_id": audit.id, "transaction_id": transaction_id, "decision": audit.decision, "score": float(audit.score), "previous_hash": audit.previous_hash, "event_hash": audit.event_hash, "result": json.loads(audit.result_json), "created_at": audit.created_at.isoformat()}
