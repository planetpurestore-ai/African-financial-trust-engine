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
        org = db.query(Organization).order_by(Organization.id).first()
        if org is None:
            org = Organization(name="African Financial Trust")
            db.add(org)
            db.flush()

        # INITIAL_API_KEY is an explicit administrative provisioning input.
        # Keep old credentials inactive and install the supplied key using the
        # current API_KEY_PEPPER. This also repairs deployments where the
        # database survived but the original bootstrap credential did not.
        db.query(ApiKey).filter(ApiKey.organization_id == org.id).update(
            {ApiKey.active: 0}, synchronize_session=False
        )
        db.add(ApiKey(
            organization_id=org.id,
            key_hash=hash_key(raw_key),
            label="primary",
            active=1,
        ))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    bootstrap()
