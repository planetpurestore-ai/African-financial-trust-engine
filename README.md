# African Financial Trust — Trust Engine

African Financial Trust is building verification infrastructure for African commerce. The Trust Engine is the core product: it connects fragmented financial and transaction evidence and produces an explainable verification result that institutions can use when assessing business activity.

## Current prototype

The prototype currently provides:

- Invoice storage and retrieval
- Evidence storage and retrieval
- Invoice-to-evidence verification
- Explainable verification checks for supplier, buyer, amount and currency
- Verification scoring and failed-check reporting
- Stored-record verification and verification summaries
- SQLite persistence with a stable project-relative database path
- Input normalization and validation
- Automated unit and API tests
- GitHub Actions test workflow

## API

Run locally with:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Health check:

`GET /health`

Store an invoice:

`POST /invoices`

Store evidence:

`POST /evidence`

Verify an invoice directly against evidence:

`POST /verify`

Verify records already stored in the database:

`POST /verify-stored/{invoice_number}/{evidence_id}`

Get a decision-oriented summary:

`POST /verification-summary/{invoice_number}/{evidence_id}`

## Verification philosophy

The engine is deliberately explainable. It does not treat missing evidence as a pass. Each check is explicit, failed checks are returned, and the result includes a verification score.

A `verified` result currently means all defined checks pass. A partial result is `review_required`. This is a prototype rule, not a lending or credit decision.

## Important limitation

This is an early engineering prototype, not production financial infrastructure. Before production use it needs stronger authentication and authorization, encryption and secrets management, audit and data-retention controls, robust database infrastructure, source integrations, richer verification rules, observability, security testing, regulatory/compliance review and institutional pilots.

## Vision

The initial wedge is SME invoice and receivable verification for financial institutions. The longer-term ambition is to expand the trust layer across counterparties, payments, logistics and trade so African business activity becomes easier to verify, understand and finance.
