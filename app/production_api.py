import hashlib
import hmac
import json
import os
import secrets
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.models import Invoice
from app.evidence import Evidence
from app.verification import compare_invoice_to_evidence_set
from app.production_db import SessionLocal, Organization, ApiKey, Transaction, AuditEvent

router = APIRouter(prefix="/v1", tags=["production"])


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _hash_key(key: str) -> str:
    pepper = os.getenv("API_KEY_PEPPER", "")
    return hashlib.sha256((pepper + key).encode()).hexdigest()


def require_api_key(x_api_key: str | None = Header(default=None), db: Session = Depends(db_session)) -> Organization:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header is required")
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == _hash_key(x_api_key), ApiKey.active == 1))
    if not key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return db.get(Organization, key.organization_id)

class ProductionTransaction(BaseModel):
    invoice: Invoice
    evidence: list[Evidence] = Field(min_length=1, max_length=100)

class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)

@router.post("/organizations", status_code=201)
def create_organization(body: OrganizationCreate, db: Session = Depends(db_session)):
    org = Organization(name=body.name.strip())
    db.add(org)
    db.commit()
    db.refresh(org)
    raw_key = "aft_live_" + secrets.token_urlsafe(32)
    db.add(ApiKey(organization_id=org.id, key_hash=_hash_key(raw_key), label="initial"))
    db.commit()
    return {"organization_id": org.id, "api_key": raw_key, "warning": "Store this API key now; it is shown only once."}

@router.post("/transactions", status_code=201)
def create_transaction(
    body: ProductionTransaction,
    organization: Organization = Depends(require_api_key),
    db: Session = Depends(db_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if idempotency_key:
        existing = db.scalar(select(Transaction).where(Transaction.organization_id == organization.id, Transaction.idempotency_key == idempotency_key))
        if existing:
            return _transaction_response(existing, db)
    evidence_ids = [e.evidence_id for e in body.evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise HTTPException(422, "evidence_id values must be unique")
    result = compare_invoice_to_evidence_set(body.invoice, body.evidence)
    decision = "verified" if result["status"] == "verified" else "review_required"
    if result["passed_checks"] == 0 and not result["conflicts"]:
        decision = "rejected"
    tx = Transaction(id=uuid.uuid4().hex, organization_id=organization.id, invoice_number=body.invoice.invoice_number, payload=json.dumps(body.model_dump(mode="json")), status=decision, idempotency_key=idempotency_key)
    db.add(tx)
    db.flush()
    previous = db.scalar(select(AuditEvent).where(AuditEvent.organization_id == organization.id).order_by(desc(AuditEvent.id)))
    previous_hash = previous.event_hash if previous else "0" * 64
    canonical = f"{previous_hash}|{tx.id}|{decision}|{result['verification_score']}|{json.dumps(result, sort_keys=True, separators=(',', ':'))}"
    event_hash = hashlib.sha256(canonical.encode()).hexdigest()
    db.add(AuditEvent(organization_id=organization.id, transaction_id=tx.id, decision=decision, score=result["verification_score"], result_json=json.dumps(result), previous_hash=previous_hash, event_hash=event_hash))
    db.commit()
    return _transaction_response(tx, db)

def _transaction_response(tx: Transaction, db: Session):
    audit = db.scalar(select(AuditEvent).where(AuditEvent.transaction_id == tx.id).order_by(desc(AuditEvent.id)))
    payload = json.loads(tx.payload)
    return {"transaction_id": tx.id, "invoice_number": tx.invoice_number, "status": tx.status, "audit_id": audit.id if audit else None, "audit_hash": audit.event_hash if audit else None, "verification": json.loads(audit.result_json) if audit else None, "created_at": tx.created_at.isoformat()}

@router.get("/transactions/{transaction_id}")
def get_transaction(transaction_id: str, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    tx = db.scalar(select(Transaction).where(Transaction.id == transaction_id, Transaction.organization_id == organization.id))
    if not tx:
        raise HTTPException(404, "Transaction not found")
    return _transaction_response(tx, db)

@router.get("/transactions")
def list_transactions(organization: Organization = Depends(require_api_key), db: Session = Depends(db_session), limit: int = 50):
    limit = max(1, min(limit, 100))
    rows = db.scalars(select(Transaction).where(Transaction.organization_id == organization.id).order_by(desc(Transaction.created_at)).limit(limit)).all()
    return {"count": len(rows), "transactions": [_transaction_response(row, db) for row in rows]}

@router.get("/audits/{transaction_id}")
def get_audit(transaction_id: str, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    audit = db.scalar(select(AuditEvent).where(AuditEvent.transaction_id == transaction_id, AuditEvent.organization_id == organization.id).order_by(desc(AuditEvent.id)))
    if not audit:
        raise HTTPException(404, "Audit record not found")
    return {"audit_id": audit.id, "transaction_id": transaction_id, "decision": audit.decision, "score": float(audit.score), "previous_hash": audit.previous_hash, "event_hash": audit.event_hash, "result": json.loads(audit.result_json), "created_at": audit.created_at.isoformat()}
