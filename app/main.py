from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from app.models import Invoice
from app.evidence import Evidence
from app.verification import compare_invoice_to_evidence, compare_invoice_to_evidence_set
from app.database import get_connection, initialize_database

initialize_database()

APP_VERSION = "0.6.1"

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
    if passed == 0:
        return "rejected"
    return "review_required"


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
    return {"status": "stored", "invoice": invoice.model_dump(mode="json")}


@app.post("/evidence", status_code=status.HTTP_201_CREATED)
def create_evidence(evidence: Evidence):
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
    return {"status": "stored", "evidence": evidence.model_dump(mode="json")}


@app.post("/verify")
def verify_invoice(request: VerificationRequest):
    result = compare_invoice_to_evidence(request.invoice, request.evidence)
    return {"invoice_number": request.invoice.invoice_number, "evidence_id": request.evidence.evidence_id,
            "decision": _decision_from_result(result), "verification": result}


@app.post("/verify-batch")
def verify_invoice_against_multiple_evidence(request: MultiEvidenceVerificationRequest):
    result = compare_invoice_to_evidence_set(request.invoice, request.evidence)
    return {"invoice_number": request.invoice.invoice_number,
            "evidence_ids": [item.evidence_id for item in request.evidence],
            "decision": _decision_from_result(result), "verification": result}


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


@app.post("/verify-stored/{invoice_number}/{evidence_id}")
def verify_stored(invoice_number: str, evidence_id: str):
    invoice, evidence, result = _verify_stored_records(invoice_number, evidence_id)
    return {"invoice_number": invoice.invoice_number, "evidence_id": evidence.evidence_id,
            "decision": _decision_from_result(result), "verification": result}


@app.post("/verification-summary/{invoice_number}/{evidence_id}")
def verification_summary(invoice_number: str, evidence_id: str):
    invoice, evidence, result = _verify_stored_records(invoice_number, evidence_id)
    return {"invoice_number": invoice.invoice_number, "evidence_id": evidence.evidence_id,
            "decision": _decision_from_result(result), "verification_score": result["verification_score"],
            "passed_checks": result["passed_checks"], "total_checks": result["total_checks"],
            "checks": result["checks"], "failed_checks": result["failed_checks"],
            "conflicts": result.get("conflicts", [])}
