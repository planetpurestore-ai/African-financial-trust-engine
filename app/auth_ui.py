import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func
from sqlalchemy.orm import Session

from app.production_db import SessionLocal, Organization, UserAccount, UserSession, Transaction, AuditEvent, Document
from app.document_engine import sha256_bytes, extract_pdf_text, extract_fields
from app.integrations import image_ocr, OCRProviderError
from app.production_api import ProductionTransaction, create_transaction

router = APIRouter(tags=["browser-auth"])
COOKIE = "aft_session"
SESSION_HOURS = 12
ROUNDS = 310_000

def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ROUNDS).hex()
    return "pbkdf2_sha256$" + str(ROUNDS) + "$" + salt.hex() + "$" + digest

def _verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt, expected = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

def _valid_email(email: str) -> bool:
    parts = email.strip().lower().split("@")
    return len(parts) == 2 and bool(parts[0]) and "." in parts[1] and not any(ch.isspace() for ch in email)

def _user_json(user, org):
    return {"id": user.id, "full_name": user.full_name, "email": user.email,
            "role": user.role, "organization_id": org.id, "organization_name": org.name}

def _issue_session(user, org, db, request, response):
    raw = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    db.add(UserSession(id=uuid.uuid4().hex, user_id=user.id,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        expires_at=now + timedelta(hours=SESSION_HOURS), revoked=False, created_at=now))
    db.commit()
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"
    response.set_cookie(COOKIE, raw, max_age=SESSION_HOURS * 3600, httponly=True,
                        secure=secure, samesite="lax", path="/")
    return {"user": _user_json(user, org)}

def current_user(request: Request, db: Session = Depends(db_session)):
    raw = request.cookies.get(COOKIE)
    if not raw:
        raise HTTPException(401, "Please sign in")
    digest = hashlib.sha256(raw.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    sess = db.scalar(select(UserSession).where(UserSession.token_hash == digest,
        UserSession.revoked.is_(False), UserSession.expires_at > now))
    if not sess:
        raise HTTPException(401, "Session expired; please sign in again")
    user = db.get(UserAccount, sess.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Account inactive")
    org = db.get(Organization, user.organization_id)
    if not org:
        raise HTTPException(403, "Organization unavailable")
    return user, org, db

class BootstrapBody(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    organization_name: str = Field(min_length=2, max_length=200)

class OrganizationBootstrapBody(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    organization_name: str = Field(min_length=2, max_length=200)

class LoginBody(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)

@router.post("/v1/auth/bootstrap", status_code=201)
def bootstrap(body: BootstrapBody, request: Request, response: Response,
              x_bootstrap_token: str | None = Header(default=None, alias="X-Bootstrap-Token"),
              db: Session = Depends(db_session)):
    expected = os.getenv("BOOTSTRAP_TOKEN")
    if not expected or not x_bootstrap_token or not hmac.compare_digest(x_bootstrap_token, expected):
        raise HTTPException(403, "Account setup is not authorized")
    if db.scalar(select(UserAccount.id).limit(1)):
        raise HTTPException(409, "Initial account setup has already been completed")
    email = str(body.email).strip().lower()
    org = db.scalar(select(Organization).order_by(Organization.id.asc()).limit(1))
    if org is None:
        org = Organization(name=body.organization_name.strip())
        db.add(org)
        db.flush()
    user = UserAccount(organization_id=org.id, full_name=body.full_name.strip(),
        email=email, email_normalized=email, password_hash=_hash_password(body.password),
        role="admin", active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue_session(user, org, db, request, response)

@router.post("/v1/auth/organizations", status_code=201)
def create_organization_account(
    body: OrganizationBootstrapBody,
    x_bootstrap_token: str | None = Header(default=None, alias="X-Bootstrap-Token"),
    db: Session = Depends(db_session),
):
    expected = os.getenv("BOOTSTRAP_TOKEN")
    if not expected or not x_bootstrap_token or not hmac.compare_digest(x_bootstrap_token, expected):
        raise HTTPException(403, "Organization provisioning is not authorized")
    email = str(body.email).strip().lower()
    if not _valid_email(email):
        raise HTTPException(422, "Enter a valid email address")
    if db.scalar(select(UserAccount.id).where(UserAccount.email_normalized == email)):
        raise HTTPException(409, "An account with this email already exists")
    org = Organization(name=body.organization_name.strip())
    db.add(org)
    db.flush()
    user = UserAccount(organization_id=org.id, full_name=body.full_name.strip(),
        email=email, email_normalized=email, password_hash=_hash_password(body.password),
        role="admin", active=True)
    db.add(user)
    db.commit()
    return {"organization": {"id": org.id, "name": org.name},
            "admin": {"id": user.id, "full_name": user.full_name, "email": user.email, "role": user.role},
            "next_step": "Sign in with the admin email and password."}


@router.post("/v1/auth/login")
def login(body: LoginBody, request: Request, response: Response, db: Session = Depends(db_session)):
    email = str(body.email).strip().lower()
    user = db.scalar(select(UserAccount).where(UserAccount.email_normalized == email))
    if not user:
        raise HTTPException(401, "Email or password is incorrect")
    if not user.active or not _verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect")
    org = db.get(Organization, user.organization_id)
    if not org:
        raise HTTPException(403, "Organization unavailable")
    return _issue_session(user, org, db, request, response)

@router.post("/v1/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(db_session)):
    raw = request.cookies.get(COOKIE)
    if raw:
        digest = hashlib.sha256(raw.encode()).hexdigest()
        sess = db.scalar(select(UserSession).where(UserSession.token_hash == digest))
        if sess:
            sess.revoked = True
            db.commit()
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax")
    return {"ok": True}

@router.get("/v1/auth/me")
def me(ctx=Depends(current_user)):
    user, org, _ = ctx
    return {"user": _user_json(user, org)}

@router.get("/v1/ui/dashboard")
def dashboard(ctx=Depends(current_user)):
    user, org, db = ctx
    txs = db.scalars(select(Transaction).where(Transaction.organization_id == org.id)
                     .order_by(desc(Transaction.created_at)).limit(100)).all()
    rows = []
    for tx in txs:
        try:
            inv = (json.loads(tx.payload or "{}").get("invoice") or {})
        except (ValueError, TypeError):
            inv = {}
        rows.append({"transaction_id": tx.id, "invoice_number": tx.invoice_number,
            "status": tx.status, "supplier_name": inv.get("supplier_name"),
            "buyer_name": inv.get("buyer_name"), "amount": inv.get("amount"),
            "currency": inv.get("currency"), "created_at": tx.created_at.isoformat()})
    audits = db.scalars(select(AuditEvent).where(AuditEvent.organization_id == org.id)
                        .order_by(desc(AuditEvent.created_at)).limit(8)).all()
    activity = [{"decision": a.decision, "score": float(a.score),
        "transaction_id": a.transaction_id, "created_at": a.created_at.isoformat()} for a in audits]
    scoped = Transaction.organization_id == org.id
    total = db.scalar(select(func.count()).select_from(Transaction).where(scoped)) or 0
    verified = db.scalar(select(func.count()).select_from(Transaction).where(scoped, Transaction.status == "verified")) or 0
    review_required = db.scalar(select(func.count()).select_from(Transaction).where(scoped, Transaction.status == "review_required")) or 0
    rejected = db.scalar(select(func.count()).select_from(Transaction).where(scoped, Transaction.status == "rejected")) or 0
    return {"user": _user_json(user, org), "transactions": rows, "activity": activity,
        "metrics": {"total": total, "verified": verified,
                    "review_required": review_required, "rejected": rejected},
        "generated_at": datetime.now(timezone.utc).isoformat()}

@router.get("/v1/ui/transactions")
def list_transactions(limit: int = 100, ctx=Depends(current_user)):
    _, org, db = ctx
    limit = max(1, min(limit, 100))
    txs = db.scalars(select(Transaction).where(Transaction.organization_id == org.id)
                     .order_by(desc(Transaction.created_at)).limit(limit)).all()
    rows = []
    for tx in txs:
        try:
            inv = (json.loads(tx.payload or "{}").get("invoice") or {})
        except (ValueError, TypeError):
            inv = {}
        rows.append({"transaction_id": tx.id, "invoice_number": tx.invoice_number,
            "status": tx.status, "supplier_name": inv.get("supplier_name"),
            "buyer_name": inv.get("buyer_name"), "amount": inv.get("amount"),
            "currency": inv.get("currency"), "created_at": tx.created_at.isoformat()})
    return {"count": len(rows), "transactions": rows}

@router.post("/v1/ui/transactions", status_code=201)
def create_ui_transaction(body: ProductionTransaction, response: Response, ctx=Depends(current_user),
                          idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    _, org, db = ctx
    return create_transaction(body, response, org, db, idempotency_key)

@router.get("/v1/ui/documents")
def ui_list_documents(limit: int = 100, ctx=Depends(current_user)):
    _, org, db = ctx
    limit = max(1, min(limit, 100))
    docs = db.scalars(select(Document).where(Document.organization_id == org.id)
                      .order_by(desc(Document.created_at)).limit(limit)).all()
    return {"count": len(docs), "documents": [{
        "document_id": d.id, "filename": d.filename, "content_type": d.content_type,
        "sha256": d.sha256, "extraction": json.loads(d.extraction_json or "{}"),
        "created_at": d.created_at.isoformat(),
    } for d in docs]}

@router.post("/v1/ui/documents", status_code=201)
def ui_upload_document(file: UploadFile = File(...), ctx=Depends(current_user)):
    _, org, db = ctx
    data = file.file.read()
    if not data:
        raise HTTPException(422, "Empty document")
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Document exceeds 10MB limit")
    digest = sha256_bytes(data)
    existing = db.scalar(select(Document).where(Document.organization_id == org.id, Document.sha256 == digest))
    if existing:
        return {"document_id": existing.id, "duplicate": True, "sha256": digest,
                "filename": existing.filename, "extraction": json.loads(existing.extraction_json or "{}")}
    content_type = file.content_type or "application/octet-stream"
    if content_type == "application/pdf" or (file.filename or "").lower().endswith(".pdf"):
        try:
            extracted_text = extract_pdf_text(data)
            extraction = extract_fields(extracted_text)
            extraction["method"] = "pdf_text"
        except Exception as exc:
            raise HTTPException(422, "PDF extraction failed: " + type(exc).__name__)
    elif content_type.startswith("image/"):
        try:
            ocr = image_ocr(data, content_type)
            extracted_text = ocr["text"]
            extraction = extract_fields(extracted_text)
            extraction["method"] = "ocr"
            extraction["ocr_provider"] = ocr["provider"]
        except OCRProviderError as exc:
            raise HTTPException(503, str(exc))
    elif content_type.startswith("text/") or (file.filename or "").lower().endswith((".txt", ".csv")):
        extracted_text = data.decode("utf-8", errors="replace")
        extraction = extract_fields(extracted_text)
        extraction["method"] = "text"
    else:
        raise HTTPException(415, "Supported document types: PDF, images, and text/CSV")
    doc = Document(id=uuid.uuid4().hex, organization_id=org.id,
        filename=(file.filename or "document")[:255], content_type=content_type,
        sha256=digest, text=extracted_text, extraction_json=json.dumps(extraction, sort_keys=True))
    db.add(doc)
    db.commit()
    return {"document_id": doc.id, "duplicate": False, "sha256": digest,
            "filename": file.filename, "extraction": extraction}


@router.get("/v1/ui/audits/verify-chain")
def ui_verify_chain(ctx=Depends(current_user)):
    _, org, db = ctx
    events = db.scalars(select(AuditEvent).where(AuditEvent.organization_id == org.id)
                        .order_by(AuditEvent.id.asc())).all()
    previous = "0" * 64
    errors = []
    for event in events:
        try:
            result = json.loads(event.result_json or "{}")
            score = result.get("verification_score")
        except (ValueError, TypeError):
            score = None
        canonical = str(previous) + "|" + str(event.transaction_id) + "|" + str(event.decision) + "|" + str(score) + "|" + str(event.result_json)
        expected = hashlib.sha256(canonical.encode()).hexdigest()
        if event.previous_hash != previous or event.event_hash != expected:
            errors.append({"audit_id": event.id, "issue": "hash_chain_mismatch"})
        previous = event.event_hash
    return {"valid": not errors, "checked": len(events), "errors": errors}
