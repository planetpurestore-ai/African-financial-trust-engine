import hashlib
import os

from app.production_db import SessionLocal, Organization, ApiKey


def hash_key(value: str) -> str:
    pepper = os.getenv("API_KEY_PEPPER")
    if not pepper:
        raise RuntimeError("API_KEY_PEPPER is required")
    return hashlib.sha256((pepper + value).encode()).hexdigest()


def bootstrap() -> None:
    raw_key = os.getenv("INITIAL_API_KEY")
    if not raw_key:
        return
    db = SessionLocal()
    try:
        if db.query(Organization).first():
            return
        org = Organization(name="African Financial Trust")
        db.add(org)
        db.flush()
        db.add(ApiKey(organization_id=org.id, key_hash=hash_key(raw_key), label="initial"))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    bootstrap()
