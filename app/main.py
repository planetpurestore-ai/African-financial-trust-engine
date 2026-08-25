from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.models import Invoice
from app.evidence import Evidence
from app.verification import compare_invoice_to_evidence
from app.database import get_connection, initialize_database

initialize_database()

app = FastAPI(title="African Financial Trust — Trust Engine", version="0.4.0", description="Evidence verification infrastructure for African commercial transactions.")

class VerificationRequest(BaseModel):
    invoice: Invoice
    evidence: Evidence

def _load_stored_records(invoice_number: str, evidence_id: str):
    connection = get_connection()
    try:
        invoice_row = connection.execute("SELECT * FROM invoices WHERE invoice_number = ?", (invoice_number,)).fetchone()
        evidence_row = connection.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
    finally:
        connection.close()
    return invoice_row, evidence_row

def _verify_stored_records(invoice_number: str, evidence_id: str):
    invoice_row, evidence_row = _load_stored_records(invoice_number, evidence_id)
    if invoice_row is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if evidence_row is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    invoice = Invoice(**dict(invoice_row))
    evidence = Evidence(**dict(evidence_row))
    return invoice, evidence, compare_invoice_to_evidence(invoice, evidence)

@app.get("/health")
def health():
    try:
        connection = get_connection()
        connection.execute("SELECT 1").fetchone()
        connection.close()
        database = "ok"
    except Exception:
        database = "error"
    return {"status": "ok" if database == "ok" else "degraded", "service": "trust-engine", "version": app.version, "database": database}

@app.post("/invoices", status_code=201)
def create_invoice(invoice: Invoice):
    connection = get_connection()
    try:
        connection.execute("""INSERT OR REPLACE INTO invoices (invoice_number, supplier_name, buyer_name, amount, currency, issue_date, due_date) VALUES (?, ?, ?, ?, ?, ?, ?)""", (invoice.invoice_number, invoice.supplier_name, invoice.buyer_name, str(invoice.amount), invoice.currency, invoice.issue_date.isoformat(), invoice.due_date.isoformat()))
        connection.commit()
    finally:
        connection.close()
    return {"status": "stored", "invoice": invoice.model_dump(mode="json")}

@app.post("/evidence", status_code=201)
def create_evidence(evidence: Evidence):
    connection = get_connection()
    try:
        connection.execute("""INSERT OR REPLACE INTO evidence (evidence_id, evidence_type, reference_number, supplier_name, buyer_name, amount, currency, evidence_date, description) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (evidence.evidence_id, evidence.evidence_type, evidence.reference_number, evidence.supplier_name, evidence.buyer_name, str(evidence.amount) if evidence.amount is not None else None, evidence.currency, evidence.evidence_date.isoformat() if evidence.evidence_date else None, evidence.description))
        connection.commit()
    finally:
        connection.close()
    return {"status": "stored", "evidence": evidence.model_dump(mode="json")}

@app.post("/verify")
def verify_invoice(request: VerificationRequest):
    return {"invoice_number": request.invoice.invoice_number, "evidence_id": request.evidence.evidence_id, "verification": compare_invoice_to_evidence(request.invoice, request.evidence)}

@app.get("/invoices/{invoice_number}")
def get_invoice(invoice_number: str):
    connection = get_connection()
    try:
        row = connection.execute("SELECT * FROM invoices WHERE invoice_number = ?", (invoice_number,)).fetchone()
    finally:
        connection.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"status": "found", "invoice": dict(row)}

@app.get("/evidence/{evidence_id}")
def get_evidence(evidence_id: str):
    connection = get_connection()
    try:
        row = connection.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
    finally:
        connection.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return {"status": "found", "evidence": dict(row)}

@app.post("/verify-stored/{invoice_number}/{evidence_id}")
def verify_stored(invoice_number: str, evidence_id: str):
    invoice, evidence, result = _verify_stored_records(invoice_number, evidence_id)
    return {"invoice_number": invoice.invoice_number, "evidence_id": evidence.evidence_id, "verification": result}

@app.post("/verification-summary/{invoice_number}/{evidence_id}")
def verification_summary(invoice_number: str, evidence_id: str):
    invoice, evidence, result = _verify_stored_records(invoice_number, evidence_id)
    passed, total = result["passed_checks"], result["total_checks"]
    return {"invoice_number": invoice.invoice_number, "evidence_id": evidence.evidence_id, "decision": "verified" if passed == total else "review_required", "verification_score": result["verification_score"], "passed_checks": passed, "total_checks": total, "checks": result["checks"], "failed_checks": result["failed_checks"]}
