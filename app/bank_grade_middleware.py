from datetime import datetime, timezone
import hashlib, os
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.production_db import SessionLocal

def _hash_key(value):
    pepper=os.getenv("API_KEY_PEPPER")
    if not pepper: return ""
    return hashlib.sha256((pepper+value).encode()).hexdigest()

def _required_scope(path, method):
    if path.startswith("/v1/organizations") or path.endswith("/webhook"): return None
    if path.startswith("/v1/bank-grade/controls"): return "bank-grade:admin"
    if path.startswith("/v1/bank-grade"): return "bank-grade:read"
    if path.startswith("/v1/audits") or "/audits/" in path: return "audits:read"
    if path.startswith("/v1/documents"): return "documents:read" if method=="GET" else "documents:write"
    if path.startswith("/v1/transactions"): return "transactions:read" if method=="GET" else "transactions:write"
    if path.startswith("/v1/integrations"): return "integrations:read" if method=="GET" else "integrations:write"
    return None

def _expiry(value):
    if value is None: return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed=datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None

async def bank_grade_security(request: Request, call_next):
    path=request.url.path
    if not path.startswith("/v1/") or path.startswith("/v1/organizations") or path.endswith("/webhook"):
        return await call_next(request)
    api_key=request.headers.get("X-API-Key")
    if not api_key: return await call_next(request)
    db=SessionLocal()
    try:
        row=db.execute(text("SELECT id,organization_id,active FROM api_keys WHERE key_hash=:h"),{"h":_hash_key(api_key)}).mappings().first()
        if not row: return JSONResponse({"detail":"Invalid API key"},status_code=401)
        db.execute(text("CREATE TABLE IF NOT EXISTS api_key_policies (key_hash VARCHAR(128) PRIMARY KEY, organization_id INTEGER NOT NULL, expires_at TIMESTAMPTZ, scopes TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, last_used_at TIMESTAMPTZ)"))
        policy=db.execute(text("SELECT expires_at,scopes,revoked FROM api_key_policies WHERE key_hash=:h"),{"h":_hash_key(api_key)}).mappings().first()
        if not policy:
            scopes="transactions:read,transactions:write,documents:read,documents:write,integrations:read,integrations:write,audits:read,bank-grade:read,bank-grade:admin"
            db.execute(text("INSERT INTO api_key_policies(key_hash,organization_id,scopes) VALUES (:h,:o,:s)"),{"h":_hash_key(api_key),"o":row["organization_id"],"s":scopes}); db.commit()
            policy={"expires_at":None,"scopes":scopes,"revoked":0}
        if not row["active"] or policy["revoked"]: return JSONResponse({"detail":"API key has been revoked"},status_code=401)
        expires_at=_expiry(policy["expires_at"])
        if expires_at is not None and expires_at <= datetime.now(timezone.utc): return JSONResponse({"detail":"API key has expired"},status_code=401)
        scope=_required_scope(path,request.method); scopes=set(filter(None,(policy["scopes"] or "").split(",")))
        if scope and scope not in scopes: return JSONResponse({"detail":"API key does not have the required scope"},status_code=403)
        db.execute(text("UPDATE api_key_policies SET last_used_at=CURRENT_TIMESTAMP WHERE key_hash=:h"),{"h":_hash_key(api_key)}); db.commit()
    finally: db.close()
    return await call_next(request)
