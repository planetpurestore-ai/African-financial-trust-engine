import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.production_db import SessionLocal, Organization, ApiKey
from app.production_api import _hash_key, require_api_key

router = APIRouter(prefix="/v1/bank-grade", tags=["bank-grade"])


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_bank_grade_tables(db: Session) -> None:
    db.execute(text("""
    CREATE TABLE IF NOT EXISTS trust_entities (
        id VARCHAR(64) PRIMARY KEY,
        organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        entity_type VARCHAR(60) NOT NULL,
        external_id VARCHAR(255) NOT NULL,
        name VARCHAR(255),
        attributes_json TEXT NOT NULL DEFAULT '{}',
        verified INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(organization_id, entity_type, external_id)
    )
    """))
    db.execute(text("""
    CREATE TABLE IF NOT EXISTS trust_relationships (
        id VARCHAR(64) PRIMARY KEY,
        organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        source_entity_id VARCHAR(64) NOT NULL REFERENCES trust_entities(id) ON DELETE CASCADE,
        relationship_type VARCHAR(80) NOT NULL,
        target_entity_id VARCHAR(64) NOT NULL REFERENCES trust_entities(id) ON DELETE CASCADE,
        evidence_id VARCHAR(64),
        confidence NUMERIC(5,2) NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """))
    db.execute(text("""
    CREATE TABLE IF NOT EXISTS security_events (
        id VARCHAR(64) PRIMARY KEY,
        organization_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
        event_type VARCHAR(100) NOT NULL,
        subject VARCHAR(255),
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """))
    db.commit()


class EntityIn(BaseModel):
    entity_type: str = Field(min_length=2, max_length=60)
    external_id: str = Field(min_length=1, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    attributes: dict[str, Any] = Field(default_factory=dict)
    verified: bool = False


class RelationshipIn(BaseModel):
    source_entity_id: str = Field(min_length=1, max_length=64)
    relationship_type: str = Field(min_length=2, max_length=80)
    target_entity_id: str = Field(min_length=1, max_length=64)
    evidence_id: str | None = Field(default=None, max_length=64)
    confidence: float = Field(default=0, ge=0, le=100)


class ConnectorRegistration(BaseModel):
    provider: str = Field(min_length=2, max_length=100)
    category: str = Field(min_length=2, max_length=50)
    capabilities: list[str] = Field(default_factory=list, max_length=20)
    mode: str = Field(default="sandbox", pattern="^(sandbox|production)$")


@router.get("/status")
def bank_grade_status(organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    ensure_bank_grade_tables(db)
    return {
        "status": "operational",
        "organization_id": organization.id,
        "capabilities": {
            "versioned_database_schema": True,
            "document_ingestion": True,
            "ocr_adapter": True,
            "signed_webhooks": True,
            "idempotent_events": True,
            "trust_graph": True,
            "audit_hash_chain": True,
            "authoritative_bank_connections": False,
            "authoritative_mobile_money_connections": False,
            "external_counterparty_registry_connections": False,
        },
        "note": "Provider credentials and regulatory/commercial access are required before an external financial source becomes authoritative."
    }


@router.post("/entities", status_code=201)
def create_entity(body: EntityIn, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    ensure_bank_grade_tables(db)
    existing = db.execute(text("SELECT id, verified FROM trust_entities WHERE organization_id=:o AND entity_type=:t AND external_id=:e"), {"o": organization.id, "t": body.entity_type, "e": body.external_id}).mappings().first()
    if existing:
        return {"entity_id": existing["id"], "duplicate": True, "verified": bool(existing["verified"])}
    entity_id = uuid.uuid4().hex
    db.execute(text("INSERT INTO trust_entities(id, organization_id, entity_type, external_id, name, attributes_json, verified) VALUES (:i,:o,:t,:e,:n,:a,:v)"), {"i": entity_id, "o": organization.id, "t": body.entity_type, "e": body.external_id, "n": body.name, "a": json.dumps(body.attributes, sort_keys=True), "v": int(body.verified)})
    db.commit()
    return {"entity_id": entity_id, "duplicate": False, "verified": body.verified}


@router.post("/relationships", status_code=201)
def create_relationship(body: RelationshipIn, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    ensure_bank_grade_tables(db)
    for entity_id in (body.source_entity_id, body.target_entity_id):
        exists = db.execute(text("SELECT 1 FROM trust_entities WHERE id=:i AND organization_id=:o"), {"i": entity_id, "o": organization.id}).first()
        if not exists:
            raise HTTPException(404, "Trust entity not found in this organization")
    rid = uuid.uuid4().hex
    db.execute(text("INSERT INTO trust_relationships(id, organization_id, source_entity_id, relationship_type, target_entity_id, evidence_id, confidence) VALUES (:i,:o,:s,:r,:t,:e,:c)"), {"i": rid, "o": organization.id, "s": body.source_entity_id, "r": body.relationship_type, "t": body.target_entity_id, "e": body.evidence_id, "c": body.confidence})
    db.commit()
    return {"relationship_id": rid, **body.model_dump()}


@router.get("/entities/{entity_id}/graph")
def entity_graph(entity_id: str, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    ensure_bank_grade_tables(db)
    entity = db.execute(text("SELECT id, entity_type, external_id, name, attributes_json, verified FROM trust_entities WHERE id=:i AND organization_id=:o"), {"i": entity_id, "o": organization.id}).mappings().first()
    if not entity:
        raise HTTPException(404, "Trust entity not found")
    rows = db.execute(text("""
        SELECT r.id, r.relationship_type, r.evidence_id, r.confidence,
               s.id source_id, s.entity_type source_type, s.external_id source_external_id, s.name source_name,
               t.id target_id, t.entity_type target_type, t.external_id target_external_id, t.name target_name
        FROM trust_relationships r
        JOIN trust_entities s ON s.id=r.source_entity_id
        JOIN trust_entities t ON t.id=r.target_entity_id
        WHERE r.organization_id=:o AND (r.source_entity_id=:i OR r.target_entity_id=:i)
        ORDER BY r.created_at DESC
    """), {"o": organization.id, "i": entity_id}).mappings().all()
    return {"entity": {"id": entity["id"], "entity_type": entity["entity_type"], "external_id": entity["external_id"], "name": entity["name"], "attributes": json.loads(entity["attributes_json"]), "verified": bool(entity["verified"])}, "relationships": [dict(r) for r in rows]}


@router.post("/connectors/register", status_code=201)
def register_connector(body: ConnectorRegistration, organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    ensure_bank_grade_tables(db)
    provider = body.provider.strip().lower()
    # Connector registrations are deliberately metadata-only. Secrets are never accepted in this endpoint.
    event_id = uuid.uuid4().hex
    db.execute(text("INSERT INTO security_events(id, organization_id, event_type, subject, metadata_json) VALUES (:i,:o,:t,:s,:m)"), {"i": event_id, "o": organization.id, "t": "connector_registered", "s": provider, "m": json.dumps(body.model_dump(), sort_keys=True)})
    db.commit()
    return {"provider": provider, "category": body.category, "capabilities": body.capabilities, "mode": body.mode, "status": "registered", "credentials_required": True, "event_id": event_id}


@router.get("/security/events")
def security_events(organization: Organization = Depends(require_api_key), db: Session = Depends(db_session), limit: int = Query(default=100, ge=1, le=200)):
    ensure_bank_grade_tables(db)
    rows = db.execute(text("SELECT id,event_type,subject,metadata_json,created_at FROM security_events WHERE organization_id=:o ORDER BY created_at DESC LIMIT :l"), {"o": organization.id, "l": limit}).mappings().all()
    return {"events": [{"id": r["id"], "event_type": r["event_type"], "subject": r["subject"], "metadata": json.loads(r["metadata_json"]), "created_at": r["created_at"].isoformat()} for r in rows]}


def verify_audit_chain(db: Session, organization_id: int) -> dict[str, Any]:
    rows = db.execute(text("SELECT id,transaction_id,decision,score,result_json,previous_hash,event_hash FROM audit_events WHERE organization_id=:o ORDER BY id ASC"), {"o": organization_id}).mappings().all()
    previous = "0" * 64
    failures = []
    for row in rows:
        canonical = f"{previous}|{row['transaction_id']}|{row['decision']}|{row['score']}|{row['result_json']}"
        expected = hashlib.sha256(canonical.encode()).hexdigest()
        if row["previous_hash"] != previous or not hmac.compare_digest(row["event_hash"], expected):
            failures.append(row["id"])
        previous = row["event_hash"]
    return {"valid": not failures, "events_checked": len(rows), "invalid_event_ids": failures}


@router.get("/audits/verify-chain")
def verify_chain(organization: Organization = Depends(require_api_key), db: Session = Depends(db_session)):
    return verify_audit_chain(db, organization.id)
