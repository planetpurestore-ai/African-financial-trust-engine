from fastapi import FastAPI
from pydantic import BaseModel

from app.models import Invoice
from app.evidence import Evidence
from app.verification import compare_invoice_to_evidence
from app.database import get_connection, initialize_database

initialize_database()

app = FastAPI(
    title="African Financial Trust — Trust Engine",
    version="0.2.0"
)


class VerificationRequest(BaseModel):
    invoice: Invoice
    evidence: Evidence


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "trust-engine",
        "version": "0.2.0"
    }


@app.post("/invoices")
def create_invoice(invoice: Invoice):
    connection = get_connection()

    connection.execute(
        """
        INSERT OR REPLACE INTO invoices
        (invoice_number, supplier_name, buyer_name, amount, currency, issue_date, due_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            invoice.invoice_number,
            invoice.supplier_name,
            invoice.buyer_name,
            str(invoice.amount),
            invoice.currency,
            invoice.issue_date.isoformat(),
            invoice.due_date.isoformat(),
        ),
    )

    connection.commit()
    connection.close()

    return {
        "status": "stored",
        "invoice": invoice.model_dump(mode="json")
    }


@app.post("/evidence")
def create_evidence(evidence: Evidence):
    connection = get_connection()

    connection.execute(
        """
        INSERT OR REPLACE INTO evidence
        (evidence_id, evidence_type, reference_number, supplier_name,
         buyer_name, amount, currency, evidence_date, description)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            evidence.evidence_id,
            evidence.evidence_type,
            evidence.reference_number,
            evidence.supplier_name,
            evidence.buyer_name,
            str(evidence.amount) if evidence.amount is not None else None,
            evidence.currency,
            evidence.evidence_date.isoformat() if evidence.evidence_date else None,
            evidence.description,
        ),
    )

    connection.commit()
    connection.close()

    return {
        "status": "stored",
        "evidence": evidence.model_dump(mode="json")
    }


@app.post("/verify")
def verify_invoice(request: VerificationRequest):
    result = compare_invoice_to_evidence(
        request.invoice,
        request.evidence
    )

    return {
        "invoice_number": request.invoice.invoice_number,
        "evidence_id": request.evidence.evidence_id,
        "verification": result
    }


@app.get("/invoices/{invoice_number}")
def get_invoice(invoice_number: str):
    connection = get_connection()

    row = connection.execute(
        "SELECT * FROM invoices WHERE invoice_number = ?",
        (invoice_number,),
    ).fetchone()

    connection.close()

    if row is None:
        return {"status": "not_found"}

    return {
        "status": "found",
        "invoice": dict(row),
    }


@app.get("/evidence/{evidence_id}")
def get_evidence(evidence_id: str):
    connection = get_connection()

    row = connection.execute(
        "SELECT * FROM evidence WHERE evidence_id = ?",
        (evidence_id,),
    ).fetchone()

    connection.close()

    if row is None:
        return {"status": "not_found"}

    return {
        "status": "found",
        "evidence": dict(row),
    }
