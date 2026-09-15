from datetime import datetime, timezone
import hashlib
import os
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.production_db import SessionLocal


def _hash_key(value: str) -> str:
    pepper = os.getenv("API_KEY_PEPPER")
    if not pepper:
        return ""
    return hashlib.sha256((pepper + value).encode()).hexdigest()


def _required_scope(path: str, method: str) -> str | None:
    if path.startswith("/v1/organizations"):
        return None
    if path.endswith("/webhook"):
        return None
    if path.startswith("/v1/audits") or "/audits/" in path:
        return "audits:read"
    if path.startswith("/v1/documents"):
        return "documents:read" if method == "GET" else "documents:write"
    if path.startswith("/v1/transactions"):
        return "transactions:read" if method == "GET" else "transactions:write"
    if path.startswith("/v1/integrations"):
        return "integrations:read" if method == "GET" else "integrations:write"
    return None


async def bank_grade_security(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/v1/"):
        return await call_next(request)
    if path.startswith("/v1/organizations") or path.endswith("/webhook"):
        return await call_next(request)
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return await call_next(request)
    key_hash = _hash_key(api_key)
    db = SessionLocal()
    try:
        row = db.execute(text("SELECT id, organization_id, active FROM api_keys WHERE key_hash=:h"), {"h": key_hash}).mappings().first()
        if not row:
            return JSONResponse({"detail": "Invalid API key"}, status_code=401)
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS api_key_policies (
                key_hash VARCHAR(128) PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                expires_at TIMESTAMPTZ,
                scopes TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0,
                last_used_at TIMESTAMPTZ
            )
        """))
        policy = db.execute(text("SELECT key_hash, expires_at, scopes, revoked FROM api_key_policies WHERE key_hash=:h"), {"h": key_hash}).mappings().first()
        if not policy:
            default_scopes = "transactions:read,transactions:write,documents:read,documents:write,integrations:read,integrations:write,audits:read,bank-grade:admin"
            db.execute(text("INSERT INTO api_key_policies(key_hash,organization_id,scopes) VALUES (:h,:o,:s)"), {"h": key_hash, "o": row["organization_id"], "s": default_scopes})
            db.commit()
            policy = {"expires_at": None, "scopes": default_scopes, "revoked": 0}
        if not row["active"] or policy["revoked"]:
            return JSONResponse({"detail": "API key has been revoked"}, status_code=401)
        expires_at = policy["expires_at"]
        if expires_at is not None and expires_at <= datetime.now(timezone.utc):
            return JSONResponse({"detail": "API key has expired"}, status_code=401)
        scope = _required_scope(path, request.method)
        scopes = set(filter(None, (policy["scopes"] or "").split(",")))
        if scope and scope not in scopes:
            return JSONResponse({"detail": "API key does not have the required scope"}, status_code=403)
        db.execute(text("UPDATE api_key_policies SET last_used_at=CURRENT_TIMESTAMP WHERE key_hash=:h"), {"h": key_hash})
        db.commit()
    finally:
        db.close()
    return await call_next(request)
