"""Independent financial-source evidence and reconciliation API.

This module deliberately separates provider-attested evidence from documents supplied
by the applicant. A record is never marked authoritative merely because a caller says
so; authoritative status is reserved for adapters that have independently verified the
record with the provider.
"""
import hashlib
import json
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.production_api import require_api_key
from app.production_db import Organization
from app.bank_grade_api import ensure_bank_grade_tables

router = APIRouter(prefix="/v1/sources", tags=["financial-sources"])


def ensure_source_tables(db: Session) -> None:
    db.execute(text("""
    CREATE TABLE IF NOT EXISTS external_financial_records (
        id VARCHAR(64) PRIMARY KEY,
        organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        provider VARCHAR(100) NOT NULL,
        authority VARCHAR(30) NOT NULL DEFAULT 'unverified',
        record_type VARCHAR(60) NOT NULL,
        provider_record_id VARCHAR(255) NOT NULL,
        reference VARCHAR(255),
        amount NUMERIC(18,2),
        currency VARCHAR(10),
        sender VARCHAR(255),
        recipient VARCHAR(255),
        occurred_at TIMESTAMPTZ,
        raw_hash VARCHAR(64) NOT NULL,
        payload_json TEXT NOT NULL,
        provenance_json TEXT NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(organization_id, provider, provider_record_id)
    )"""))
    db.commit()


class FinancialSourceRecord(BaseModel):
    provider: str = Field(min_length=2, max_length=100)
    record_type: str = Field(default="payment", min_length=2, max_length=60)
    provider_record_id: str = Field(min_length=1, max_length=255)
    reference: str | None = Field(default=None, max_length=255)
    amount: Decimal | None = None
    currency: str | None = Field(default=None, max_length=10)
    sender: str | None = Field(default=None, max_length=255)
    recipient: str | None = Field(default=None, max_length=255)
    occurred_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    authority: str = Field(default="provider_attested", pattern="^(provider_attested|independently_verified)$")
    provenance: dict[str, Any] = Field(default_factory=dict)


@router.post("/records", status_code=201)
def ingest_source_record(
    body: FinancialSourceRecord,
    organization: Organization = Depends(require_api_key),
    db: Session = Depends(__import__("app.production_api", fromlist=["db_session"]).db_session),
):
    ensure_source_tables(db)
    if body.authority == "independently_verified":
        verified = body.provenance.get("verification")
        if verified != "provider_api_signature" and verified != "provider_direct_query":
            raise HTTPException(422, "independently_verified requires provider_api_signature or provider_direct_query provenance")
    canonical = json.dumps(body.payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    existing = db.execute(text("SELECT id, authority FROM external_financial_records WHERE organization_id=:o AND provider=:p AND provider_record_id=:r"), {"o": organization.id, "p": body.provider.strip().lower(), "r": body.provider_record_id}).mappings().first()
    if existing:
        return {"record_id": existing["id"], "duplicate": True, "authority": existing["authority"], "raw_hash": digest}
    rid = uuid.uuid4().hex
    db.execute(text("""INSERT INTO external_financial_records
        (id,organization_id,provider,authority,record_type,provider_record_id,reference,amount,currency,sender,recipient,occurred_at,raw_hash,payload_json,provenance_json)
        VALUES (:i,:o,:p,:a,:t,:r,:ref,:amt,:cur,:s,:rec,:dt,:h,:payload,:prov)"""), {
        "i": rid, "o": organization.id, "p": body.provider.strip().lower(), "a": body.authority,
        "t": body.record_type, "r": body.provider_record_id, "ref": body.reference,
        "amt": body.amount, "cur": body.currency.upper() if body.currency else None,
        "s": body.sender, "rec": body.recipient, "dt": body.occurred_at, "h": digest,
        "payload": json.dumps(body.payload, sort_keys=True, default=str),
        "prov": json.dumps(body.provenance, sort_keys=True, default=str),
    })
    db.commit()
    return {"record_id": rid, "duplicate": False, "authority": body.authority, "raw_hash": digest}


@router.get("/records")
def list_source_records(
    organization: Organization = Depends(require_api_key),
    db: Session = Depends(__import__("app.production_api", fromlist=["db_session"]).db_session),
    reference: str | None = None,
    provider: str | None = None,
    limit: int = 100,
):
    ensure_source_tables(db)
    limit = max(1, min(limit, 200))
    clauses = ["organization_id=:o"]
    params: dict[str, Any] = {"o": organization.id, "l": limit}
    if reference:
        clauses.append("reference=:r"); params["r"] = reference
    if provider:
        clauses.append("provider=:p"); params["p"] = provider.strip().lower()
    rows = db.execute(text(f"SELECT id,provider,authority,record_type,provider_record_id,reference,amount,currency,sender,recipient,occurred_at,raw_hash,provenance_json,created_at FROM external_financial_records WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT :l"), params).mappings().all()
    return {"count": len(rows), "records": [{**{k: r[k] for k in ("id","provider","authority","record_type","provider_record_id","reference","amount","currency","sender","recipient","occurred_at","raw_hash")}, "provenance": json.loads(r["provenance_json"]), "created_at": r["created_at"].isoformat()} for r in rows]}


@router.get("/reconcile/{transaction_id}")
def reconcile_transaction(
    transaction_id: str,
    organization: Organization = Depends(require_api_key),
    db: Session = Depends(__import__("app.production_api", fromlist=["db_session"]).db_session),
):
    ensure_source_tables(db)
    tx = db.execute(text("SELECT id,invoice_number,payload,status FROM transactions WHERE id=:i AND organization_id=:o"), {"i": transaction_id, "o": organization.id}).mappings().first()
    if not tx:
        raise HTTPException(404, "Transaction not found")
    payload = json.loads(tx["payload"])
    invoice = payload.get("invoice", {})
    invoice_number = str(invoice.get("invoice_number") or tx["invoice_number"])
    amount_raw = invoice.get("amount")
    currency = str(invoice.get("currency") or "").upper()
    try: invoice_amount = Decimal(str(amount_raw)) if amount_raw is not None else None
    except InvalidOperation: invoice_amount = None
    evidence = db.execute(text("SELECT provider,authority,provider_record_id,reference,amount,currency,sender,recipient,occurred_at,provenance_json FROM external_financial_records WHERE organization_id=:o AND (reference=:ref OR provider_record_id=:ref) ORDER BY created_at DESC"), {"o": organization.id, "ref": invoice_number}).mappings().all()
    matches = []
    for row in evidence:
        amount_match = invoice_amount is not None and row["amount"] is not None and Decimal(str(row["amount"])) == invoice_amount
        currency_match = bool(currency and row["currency"] and str(row["currency"]).upper() == currency)
        authoritative = row["authority"] == "independently_verified"
        score = (50 if authoritative else 20) + (30 if amount_match else 0) + (20 if currency_match else 0)
        matches.append({"provider": row["provider"], "authority": row["authority"], "provider_record_id": row["provider_record_id"], "reference": row["reference"], "amount": float(row["amount"]) if row["amount"] is not None else None, "currency": row["currency"], "amount_match": amount_match, "currency_match": currency_match, "confidence": score, "provenance": json.loads(row["provenance_json"])})
    authoritative_match = any(m["authority"] == "independently_verified" and m["amount_match"] and m["currency_match"] for m in matches)
    return {"transaction_id": transaction_id, "invoice_number": invoice_number, "independent_records_found": len(matches), "authoritative_payment_match": authoritative_match, "matches": matches, "decision_support": "independently_verified_payment_match" if authoritative_match else ("independent_evidence_review" if matches else "no_independent_financial_evidence")}
