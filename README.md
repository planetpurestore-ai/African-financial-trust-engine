# African Financial Trust — Trust Engine

African Financial Trust is building verification infrastructure for African commerce. The Trust Engine is the core product: it connects fragmented financial and transaction evidence and produces an explainable verification result that institutions can use when assessing business activity.

## Current MVP prototype

The repository currently provides:

- Invoice storage and retrieval
- Evidence storage and retrieval
- Single-evidence invoice verification
- Multi-evidence invoice verification
- Explainable checks for supplier, buyer, amount and currency
- Verification scoring and failed-check reporting
- Evidence attribution showing which evidence supports each check
- Stored-record verification and decision summaries
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

Interactive API documentation is automatically available through FastAPI at `/docs` when the server is running.

### Health

`GET /health`

### Store an invoice

`POST /invoices`

### Store evidence

`POST /evidence`

### Verify one invoice against one evidence record

`POST /verify`

### Verify one invoice against multiple evidence records

`POST /verify-batch`

The batch endpoint accepts up to 100 evidence records and reports which evidence records support each verification check.

### Verify records already stored in the database

`POST /verify-stored/{invoice_number}/{evidence_id}`

### Get a decision-oriented summary

`POST /verification-summary/{invoice_number}/{evidence_id}`

## Testing

Run the full test suite with:

```bash
pytest -q
```

GitHub Actions is configured to run the same test suite on pushes to `main`, pull requests targeting `main`, and manual workflow dispatches.

## Verification philosophy

The engine is deliberately explainable. It does not treat missing evidence as a pass. Each check is explicit, failed checks are returned, and the result includes a verification score.

A `verified` result currently means all defined checks pass. A partial result is `review_required`, while a zero-check result in the stored-record summary is `rejected`. These are prototype verification states, not lending or credit decisions.

For multiple evidence records, a check is supported when at least one supplied evidence record provides a matching value. The response identifies the evidence supporting each check so a human reviewer can inspect the underlying records.

## Important limitation

This is an early engineering MVP, not production financial infrastructure. Before production use it needs strong authentication and authorization, encryption and secrets management, audit and data-retention controls, production-grade database infrastructure, source integrations, richer verification and anomaly rules, observability, security testing, regulatory/compliance review and institutional pilots.

## Vision

The initial wedge is SME invoice and receivable verification for financial institutions. The longer-term ambition is to expand the trust layer across counterparties, payments, logistics and trade so African business activity becomes easier to verify, understand and finance.
