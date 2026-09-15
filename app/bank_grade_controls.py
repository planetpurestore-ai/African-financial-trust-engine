import hashlib, hmac, os, json, uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.production_db import SessionLocal, Organization
from app.production_api import require_api_key

router = APIRouter(prefix="/v1/bank-grade/controls", tags=["bank-grade-controls"])

class KeyPolicy(BaseModel):
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)
    scopes: list[str] = Field(default_factory=lambda: ["transactions:read","transactions:write","documents:read","documents:write","integrations:read","integrations:write","audits:read","bank-grade:admin"], max_length=30)


def db_session():
    db = SessionLocal()
    try: yield db
    finally: db.close()


def ensure(db):
    db.execute(text("CREATE TABLE IF NOT EXISTS api_key_policies (key_hash VARCHAR(128) PRIMARY KEY, organization_id INTEGER NOT NULL, expires_at TIMESTAMPTZ, scopes TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, last_used_at TIMESTAMPTZ)"))
    db.commit()


def hash_key(value):
    pepper = os.getenv("API_KEY_PEPPER")
    if not pepper: raise RuntimeError("API_KEY_PEPPER is required")
    return hashlib.sha256((pepper + value).encode()).hexdigest()

@router.post("/keys/{key_id}/policy")
def set_key_policy(key_id: int, body: KeyPolicy, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    ensure(db)
    key = db.execute(text("SELECT key_hash, active FROM api_keys WHERE id=:i AND organization_id=:o"), {"i":key_id,"o":organization.id}).mappings().first()
    if not key: raise HTTPException(404,"API key not found")
    expires = None
    if body.expires_in_days: expires = datetime.now(timezone.utc).timestamp() + body.expires_in_days*86400
    db.execute(text("INSERT INTO api_key_policies(key_hash,organization_id,expires_at,scopes,revoked) VALUES (:h,:o,:e,:s,0) ON CONFLICT(key_hash) DO UPDATE SET expires_at=:e, scopes=:s, revoked=0"), {"h":key["key_hash"],"o":organization.id,"e":datetime.fromtimestamp(expires, timezone.utc) if expires else None,"s":",".join(sorted(set(body.scopes)))})
    db.commit()
    return {"key_id":key_id,"expires_at":datetime.fromtimestamp(expires, timezone.utc).isoformat() if expires else None,"scopes":sorted(set(body.scopes)),"revoked":False}

@router.post("/keys/{key_id}/disable")
def disable_key(key_id: int, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    ensure(db)
    key = db.execute(text("SELECT key_hash FROM api_keys WHERE id=:i AND organization_id=:o"), {"i":key_id,"o":organization.id}).mappings().first()
    if not key: raise HTTPException(404,"API key not found")
    db.execute(text("UPDATE api_keys SET active=0 WHERE id=:i"), {"i":key_id})
    db.execute(text("INSERT INTO api_key_policies(key_hash,organization_id,scopes,revoked) VALUES (:h,:o,'',1) ON CONFLICT(key_hash) DO UPDATE SET revoked=1"), {"h":key["key_hash"],"o":organization.id})
    db.commit()
    return {"key_id":key_id,"revoked":True}

@router.get("/keys")
def key_policies(organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    ensure(db)
    rows = db.execute(text("SELECT k.id,k.label,k.active,p.expires_at,p.scopes,p.revoked,p.last_used_at FROM api_keys k LEFT JOIN api_key_policies p ON p.key_hash=k.key_hash WHERE k.organization_id=:o ORDER BY k.created_at DESC"), {"o":organization.id}).mappings().all()
    return {"keys":[dict(r) for r in rows]}

@router.get("/audit-integrity")
def audit_integrity(organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    rows = db.execute(text("SELECT id,transaction_id,decision,score,result_json,previous_hash,event_hash FROM audit_events WHERE organization_id=:o ORDER BY id ASC"), {"o":organization.id}).mappings().all()
    previous="0"*64; invalid=[]
    for r in rows:
        score=str(float(r["score"]))
        canonical=f"{previous}|{r['transaction_id']}|{r['decision']}|{score}|{r['result_json']}"
        expected=hashlib.sha256(canonical.encode()).hexdigest()
        if r["previous_hash"] != previous or not hmac.compare_digest(r["event_hash"], expected): invalid.append(r["id"])
        previous=r["event_hash"]
    return {"valid":not invalid,"events_checked":len(rows),"invalid_event_ids":invalid}
