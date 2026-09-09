# African Financial Trust — Trust Engine

African Financial Trust is building verification infrastructure for African commerce. The Trust Engine connects fragmented financial and transaction evidence and produces an explainable verification result that institutions can use when assessing business activity.

## MVP 1.0

The prototype now demonstrates the complete core workflow:

**Transaction submission → evidence persistence → verification → score → decision → evidence attribution → audit record → human review console.**

Included:

- Invoice storage and retrieval
- Evidence storage and retrieval
- Single-evidence invoice verification
- Multi-evidence invoice verification (up to 100 records)
- Explicit supplier, buyer, amount and currency checks
- Missing-evidence detection
- Conflicting-evidence detection
- Verification scoring and failed-check reporting
- Evidence attribution showing which records support each check
- End-to-end `/transactions` intake endpoint that persists and verifies a transaction package
- Stored-record verification and decision summaries
- SQLite persistence with a project-relative database path
- Input normalization and validation
- Browser-based review console at `/` and `/dashboard`
- Audit history view in the review console
- Interactive FastAPI API documentation at `/docs`
- Automated unit and API tests
- GitHub Actions test workflow

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open the review console at `http://127.0.0.1:8000/` or API documentation at `http://127.0.0.1:8000/docs`.

## Core API

### Health

`GET /health`

### End-to-end transaction submission

`POST /transactions`

Accepts one invoice and 1–100 unique evidence records. The transaction is persisted, verified, and written to the audit trail in one operation.

### Store an invoice

`POST /invoices`

### Store evidence

`POST /evidence`

### Verify one invoice against one evidence record

`POST /verify`

### Verify one invoice against multiple evidence records

`POST /verify-batch`

### Retrieve stored records

`GET /invoices/{invoice_number}`

`GET /evidence/{evidence_id}`

### Audit history

`GET /audits/{invoice_number}?limit=50`

### Verify stored records

`POST /verify-stored/{invoice_number}/{evidence_id}`

### Decision summary

`POST /verification-summary/{invoice_number}/{evidence_id}`

## Verification philosophy

The engine is deliberately explainable. Missing evidence is never silently treated as a pass. Each check is explicit, failed and incomplete checks are returned, conflicts are identified, and the result includes a verification score plus evidence attribution.

A `verified` result currently means all defined checks pass without unresolved conflicts or incomplete checks. A partial or conflicting result is `review_required`. A zero-check stored-record result is `rejected`. These are prototype verification states, not lending or credit decisions.

For multiple evidence records, a check is supported when at least one supplied evidence record provides a matching value. When multiple evidence records disagree on a populated field, the engine identifies the conflict and requires review rather than silently choosing a value.

## Testing

Run the full test suite with:

```bash
pytest -q
```

GitHub Actions runs the same suite on pushes to `main`, pull requests targeting `main`, and manual workflow dispatches.

## Prototype boundary

This is a functional engineering MVP, not production financial infrastructure. The prototype is intentionally limited to structured evidence supplied by the caller. It does not yet connect to live bank, mobile-money, accounting, ERP, logistics or government data sources, and it does not make lending or credit decisions.

Production work after the prototype includes authentication and authorization, encryption and secrets management, production database infrastructure, source integrations, richer verification and anomaly rules, observability, security testing, regulatory/compliance review, data-retention controls and institutional pilots.

## Vision

The initial wedge is SME invoice and receivable verification for financial institutions. The longer-term ambition is to expand the trust layer across counterparties, payments, logistics and trade so African business activity becomes easier to verify, understand and finance.
