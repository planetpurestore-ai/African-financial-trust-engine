from fastapi import FastAPI
from pydantic import BaseModel

from app.models import Invoice
from app.evidence import Evidence
from app.verification import compare_invoice_to_evidence

app = FastAPI(
    title="African Financial Trust — Trust Engine",
    version="0.1.0"
)


class VerificationRequest(BaseModel):
    invoice: Invoice
    evidence: Evidence


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "trust-engine",
        "version": "0.1.0"
    }


@app.post("/invoices")
def create_invoice(invoice: Invoice):
    return {
        "status": "received",
        "invoice": invoice.model_dump(mode="json")
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
