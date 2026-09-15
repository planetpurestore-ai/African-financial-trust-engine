import hashlib
import os
import secrets
import time

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.production_db import SessionLocal, Organization, ApiKey

router = APIRouter(tags=["setup"])


def _hash_key(key: str) -> str:
    pepper = os.getenv("API_KEY_PEPPER")
    if not pepper:
        raise RuntimeError("API_KEY_PEPPER is required")
    return hashlib.sha256((pepper + key).encode()).hexdigest()


def _check_token(token: str, expected_env: str, expires_env: str) -> None:
    expected = os.getenv(expected_env)
    expires = os.getenv(expires_env)
    if not expected or not expires or not secrets.compare_digest(token, expected):
        raise HTTPException(403, "Invalid recovery token")
    try:
        if time.time() >= float(expires):
            raise HTTPException(403, "Recovery token has expired")
    except ValueError:
        raise HTTPException(500, "Recovery configuration is invalid")


@router.get("/setup")
def initial_setup(token: str = Query(..., min_length=10)):
    expected = os.getenv("INITIAL_SETUP_TOKEN")
    if not expected or not secrets.compare_digest(token, expected):
        raise HTTPException(403, "Invalid setup token")

    db = SessionLocal()
    try:
        existing = db.scalar(select(Organization).limit(1))
        if existing:
            raise HTTPException(409, "Initial setup has already been completed")
        org = Organization(name="African Financial Trust")
        db.add(org)
        db.flush()
        raw_key = "aft_live_" + secrets.token_urlsafe(32)
        db.add(ApiKey(organization_id=org.id, key_hash=_hash_key(raw_key), label="initial"))
        db.commit()
        return {"status": "created", "organization_id": org.id, "organization_name": org.name, "api_key": raw_key, "warning": "Save this API key now. It is shown only once."}
    finally:
        db.close()


@router.get("/recover")
def recover_api_key(token: str = Query(..., min_length=20)):
    """Issue a fresh API key only when an explicitly configured, expiring recovery token is supplied."""
    _check_token(token, "RECOVERY_TOKEN", "RECOVERY_EXPIRES_AT")
    db = SessionLocal()
    try:
        org = db.scalar(select(Organization).order_by(Organization.created_at.asc()).limit(1))
        if not org:
            raise HTTPException(404, "No organization has been initialized")
        raw_key = "aft_live_" + secrets.token_urlsafe(32)
        db.add(ApiKey(organization_id=org.id, key_hash=_hash_key(raw_key), label="recovery"))
        db.commit()
        return {"status": "recovered", "organization_id": org.id, "organization_name": org.name, "api_key": raw_key, "warning": "Save this API key now; it is shown only once. Existing API keys remain active."}
    finally:
        db.close()
