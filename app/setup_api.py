import hashlib
import os
import secrets
import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.production_db import SessionLocal, Organization, ApiKey

router = APIRouter(tags=["setup"])


def _hash_key(key: str) -> str:
    pepper = os.getenv("API_KEY_PEPPER")
    if not pepper:
        raise RuntimeError("API_KEY_PEPPER is required")
    return hashlib.sha256((pepper + key).encode()).hexdigest()


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
        return {
            "status": "created",
            "organization_id": org.id,
            "organization_name": org.name,
            "api_key": raw_key,
            "warning": "Save this API key now. It is shown only once."
        }
    finally:
        db.close()
