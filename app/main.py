import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from app.models import Invoice
from app.evidence import Evidence
from app.verification import compare_invoice_to_evidence, compare_invoice_to_evidence_set
from app.database import get_connection, initialize_database, list_verification_audits, record_verification_audit

initialize_database()

APP_VERSION = "1.0.0"
DASHBOARD_PATH = Path(__file__).resolve().parent / "dashboard.html"

app = FastAPI(
    title="African Financial Trust — Trust Engine",
    version=APP_VERSION,
    description="Evidence verification infrastructure for African commercial transactions.",
)


class VerificationRequest(BaseModel):
    invoice: Invoice
    evidence: Evidence


class MultiEvidenceVerificationRequest(BaseModel):
    invoice: Invoice
    evidence: list[Evidence] = Field(min_length=1, max_length=100)

    @field_validator("evidence")
    @classmethod
    def validate_unique_evidence_ids(cls, value):
        ids = [item.evidence_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence_id values must be unique within a batch")
        return value


class TransactionSubmissionRequest(MultiEvidenceVerificationRequest):
    """End-to-end MVP transaction intake: persist evidence, verify it, and create an audit record."""


def _store_invoice(invoice: Invoice):
    connection = get_connection()
    try:
        connection.execute(
            """INSERT OR REPLACE INTO invoices
            (invoice_number, supplier_name, buyer_name, amount, currency, issue_date, due_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (invoice.invoice_number, invoice.supplier_name, invoice.buyer_name, str(invoice.amount), invoice.currency,
             invoice.issue_date.isoformat(), invoice.due_date.isoformat()),
        )
        connection.commit()
    finally:
        connection.close()


def _store_evidence(evidence: Evidence):
    connection = get_connection()
    try:
        connection.execute(
            """INSERT OR REPLACE INTO evidence
            (evidence_id, evidence_type, reference_number, supplier_name,
             buyer_name, amount, currency, evidence_date, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (evidence.evidence_id, evidence.evidence_type, evidence.reference_number, evidence.supplier_name,
             evidence.buyer_name, str(evidence.amount) if evidence.amount is not None else None, evidence.currency,
             evidence.evidence_date.isoformat() if evidence.evidence_date else None, evidence.description),
        )
        connection.commit()
    finally:
        connection.close()


def _load_stored_records(invoice_number: str, evidence_id: str):
    connection = get_connection()
    try:
        invoice_row = connection.execute("SELECT * FROM invoices WHERE invoice_number = ?", (invoice_number,)).fetchone()
        evidence_row = connection.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
        return invoice_row, evidence_row
    finally:
        connection.close()


def _verify_stored_records(invoice_number: str, evidence_id: str):
    invoice_row, evidence_row = _load_stored_records(invoice_number, evidence_id)
    if invoice_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice '{invoice_number}' not found")
    if evidence_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Evidence '{evidence_id}' not found")
    invoice = Invoice(**dict(invoice_row))
    evidence = Evidence(**dict(evidence_row))
    result = compare_invoice_to_evidence(invoice, evidence)
    return invoice, evidence, result


def _decision_from_result(result: dict) -> str:
    if result.get("status") == "review_required":
        return "review_required"
    passed = result["passed_checks"]
    if passed == result["total_checks"]:
        return "verified"
    return "rejected" if passed == 0 else "review_required"


def _record_audit(invoice_number: str, evidence_ids: list[str], result: dict) -> int:
    return record_verification_audit(
        invoice_number=invoice_number,
        evidence_ids=json.dumps(evidence_ids),
        decision=_decision_from_result(result),
        verification_score=result["verification_score"],
        passed_checks=result["passed_checks"],
        total_checks=result["total_checks"],
        failed_checks=json.dumps(result["failed_checks"]),
    )


def _verification_response(invoice_number: str, evidence_ids: list[str], result: dict, audit_id: int):
    return {
        "invoice_number": invoice_number,
        "evidence_ids": evidence_ids,
        "decision": _decision_from_result(result),
        "audit_id": audit_id,
        "verification": result,
    }


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(DASHBOARD_PATH, media_type="text/html")


@app.get("/dashboard", include_in_schema=False)
def dashboard_alias():
    return FileResponse(DASHBOARD_PATH, media_type="text/html")


@app.get("/health")
def health():
    connection = get_connection()
    try:
        connection.execute("SELECT 1").fetchone()
    finally:
        connection.close()
    return {"status": "ok", "service": "trust-engine", "version": APP_VERSION, "database": "ok"}


@app.post("/invoices", status_code=status.HTTP_201_CREATED)
def create_invoice(invoice: Invoice):
    _store_invoice(invoice)
    return {"status": "stored", "invoice": invoice.model_dump(mode="json")}


@app.post("/evidence", status_code=status.HTTP_201_CREATED)
def create_evidence(evidence: Evidence):
    _store_evidence(evidence)
    return {"status": "stored", "evidence": evidence.model_dump(mode="json")}


@app.post("/verify")
def verify_invoice(request: VerificationRequest):
    result = compare_invoice_to_evidence(request.invoice, request.evidence)
    audit_id = _record_audit(request.invoice.invoice_number, [request.evidence.evidence_id], result)
    return _verification_response(request.invoice.invoice_number, [request.evidence.evidence_id], result, audit_id)


@app.post("/verify-batch")
def verify_invoice_against_multiple_evidence(request: MultiEvidenceVerificationRequest):
    result = compare_invoice_to_evidence_set(request.invoice, request.evidence)
    evidence_ids = [item.evidence_id for item in request.evidence]
    audit_id = _record_audit(request.invoice.invoice_number, evidence_ids, result)
    return _verification_response(request.invoice.invoice_number, evidence_ids, result, audit_id)


@app.post("/transactions", status_code=status.HTTP_201_CREATED)
def submit_transaction(request: TransactionSubmissionRequest):
    """Persist a transaction package and immediately produce its auditable verification result."""
    _store_invoice(request.invoice)
    for evidence in request.evidence:
        _store_evidence(evidence)
    result = compare_invoice_to_evidence_set(request.invoice, request.evidence)
    evidence_ids = [item.evidence_id for item in request.evidence]
    audit_id = _record_audit(request.invoice.invoice_number, evidence_ids, result)
    return _verification_response(request.invoice.invoice_number, evidence_ids, result, audit_id)


@app.get("/invoices/{invoice_number}")
def get_invoice(invoice_number: str):
    connection = get_connection()
    try:
        row = connection.execute("SELECT * FROM invoices WHERE invoice_number = ?", (invoice_number,)).fetchone()
    finally:
        connection.close()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invoice '{invoice_number}' not found")
    return {"status": "found", "invoice": dict(row)}


@app.get("/evidence/{evidence_id}")
def get_evidence(evidence_id: str):
    connection = get_connection()
    try:
        row = connection.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
    finally:
        connection.close()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Evidence '{evidence_id}' not found")
    return {"status": "found", "evidence": dict(row)}


@app.get("/audits/{invoice_number}")
def get_verification_audits(invoice_number: str, limit: int = Query(default=50, ge=1, le=100)):
    audits = list_verification_audits(invoice_number, limit=limit)
    return {"invoice_number": invoice_number, "count": len(audits), "audits": audits}


@app.post("/verify-stored/{invoice_number}/{evidence_id}")
def verify_stored(invoice_number: str, evidence_id: str):
    invoice, evidence, result = _verify_stored_records(invoice_number, evidence_id)
    audit_id = _record_audit(invoice.invoice_number, [evidence.evidence_id], result)
    return _verification_response(invoice.invoice_number, [evidence.evidence_id], result, audit_id)


@app.post("/verification-summary/{invoice_number}/{evidence_id}")
def verification_summary(invoice_number: str, evidence_id: str):
    invoice, evidence, result = _verify_stored_records(invoice_number, evidence_id)
    audit_id = _record_audit(invoice.invoice_number, [evidence.evidence_id], result)
    return {
        "invoice_number": invoice.invoice_number,
        "evidence_id": evidence.evidence_id,
        "audit_id": audit_id,
        "decision": _decision_from_result(result),
        "verification_score": result["verification_score"],
        "passed_checks": result["passed_checks"],
        "total_checks": result["total_checks"],
        "checks": result["checks"],
        "failed_checks": result["failed_checks"],
        "conflicts": result.get("conflicts", []),
        "incomplete_checks": result.get("incomplete_checks", []),
    }
