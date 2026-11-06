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


def _required_scope(path: str, method: str):
    if path.startswith("/v1/organizations") or path.endswith("/webhook"):
        return None
    if path.startswith("/v1/bank-grade/controls") or path.startswith("/v1/risk-settings"):
        return "bank-grade:admin"
    if path.startswith("/v1/bank-grade"):
        return "bank-grade:read" if method in {"GET", "HEAD", "OPTIONS"} else "bank-grade:write"
    if path.startswith("/v1/audits") or "/audits/" in path:
        return "audits:read"
    if path.startswith("/v1/documents"):
        return "documents:read" if method == "GET" else "documents:write"
    if path.startswith("/v1/transactions"):
        return "transactions:read" if method == "GET" else "transactions:write"
    if path.startswith("/v1/integrations"):
        return "integrations:read" if method == "GET" else "integrations:write"
    if path.startswith("/v1/sources"):
        return "integrations:read" if method == "GET" else "integrations:write"
    return None


def _expiry(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def _rate_limit_bucket(request: Request, api_key: str | None) -> str:
    if api_key:
        identity = "api-key:" + hashlib.sha256(api_key.encode()).hexdigest()
    else:
        identity = "client-ip:" + (request.client.host if request.client else "unknown")
    return hashlib.sha256(identity.encode()).hexdigest()


async def bank_grade_security(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/v1/"):
        return await call_next(request)

    api_key = request.headers.get("X-API-Key")
    now = datetime.now(timezone.utc)
    window_key = str(int(now.timestamp() // 60))
    api_limit = max(1, int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "120")))
    anonymous_limit = max(1, int(os.getenv("ANON_RATE_LIMIT_PER_MINUTE", "60")))
    limit = api_limit if api_key else anonymous_limit

    db = SessionLocal()
    try:
        bucket = _rate_limit_bucket(request, api_key)
        db.execute(text("""
            INSERT INTO api_rate_limits (bucket_key, window_key, request_count)
            VALUES (:b, :w, 1)
            ON CONFLICT(bucket_key) DO UPDATE SET
                request_count = CASE
                    WHEN api_rate_limits.window_key = :w THEN api_rate_limits.request_count + 1
                    ELSE 1
                END,
                window_key = :w
        """), {"b": bucket, "w": window_key})
        count = db.execute(
            text("SELECT request_count FROM api_rate_limits WHERE bucket_key=:b"),
            {"b": bucket},
        ).scalar_one()
        db.commit()

        if count > limit:
            retry_after = 60 - (int(now.timestamp()) % 60)
            return JSONResponse(
                {"detail": "Rate limit exceeded; retry after the current minute window"},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

        # These routes have their own bootstrap-token or provider-signature
        # authentication. They still pass through the IP-based rate limiter.
        if (
            path.startswith("/v1/organizations")
            or path.endswith("/webhook")
            or path.startswith("/v1/bank-grade/controls/bootstrap/")
        ):
            db.close()
            return await call_next(request)

        if not api_key:
            db.close()
            return await call_next(request)

        key_hash = _hash_key(api_key)
        row = db.execute(
            text("SELECT id,organization_id,active FROM api_keys WHERE key_hash=:h"),
            {"h": key_hash},
        ).mappings().first()
        if not row:
            return JSONResponse({"detail": "Invalid API key"}, status_code=401)

        # Policy tables are created by Alembic migrations, never lazily during a request.
        policy = db.execute(
            text("SELECT expires_at,scopes,revoked FROM api_key_policies WHERE key_hash=:h"),
            {"h": key_hash},
        ).mappings().first()
        if not policy:
            scopes = (
                "transactions:read,transactions:write,documents:read,documents:write,"
                "integrations:read,integrations:write,audits:read,bank-grade:read,bank-grade:write"
            )
            db.execute(
                text("INSERT INTO api_key_policies(key_hash,organization_id,scopes) VALUES (:h,:o,:s)"),
                {"h": key_hash, "o": row["organization_id"], "s": scopes},
            )
            db.commit()
            policy = {"expires_at": None, "scopes": scopes, "revoked": 0}

        if not row["active"] or policy["revoked"]:
            return JSONResponse({"detail": "API key has been revoked"}, status_code=401)
        expires_at = _expiry(policy["expires_at"])
        if expires_at is not None and expires_at <= now:
            return JSONResponse({"detail": "API key has expired"}, status_code=401)
        scope = _required_scope(path, request.method)
        scopes = set(filter(None, (policy["scopes"] or "").split(",")))
        if scope and scope not in scopes:
            return JSONResponse({"detail": "API key does not have the required scope"}, status_code=403)
        db.execute(
            text("UPDATE api_key_policies SET last_used_at=CURRENT_TIMESTAMP WHERE key_hash=:h"),
            {"h": key_hash},
        )
        db.commit()
    finally:
        db.close()

    return await call_next(request)
