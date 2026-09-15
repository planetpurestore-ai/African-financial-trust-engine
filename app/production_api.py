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
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(415, "Unsupported document encoding")
        extraction = extract_fields(text)
        extraction["method"] = "text"
    doc = Document(organization_id=organization.id, filename=file.filename or "document", content_type=content_type, sha256=digest, text=text, extraction_json=json.dumps(extraction, sort_keys=True))
    db.add(doc); db.commit(); db.refresh(doc)
    return {"document_id": doc.id, "duplicate": False, "sha256": digest, "extraction": extraction}
