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

### Document upload

`POST /v1/documents` accepts one PDF, supported image, or UTF-8 text/CSV file. `POST /v1/documents/batch` accepts up to ten files and returns an outcome for each file; partial success is explicit and each file is subject to the upload-size and content checks. PDF active content, embedded files, encryption, incremental revisions, unverified signature fields and suspicious text controls can add review flags. These are anomaly indicators only: AFT does not yet cryptographically validate issuer signatures or prove invoice authenticity.

### Download and securely share a Trust Record

`GET /v1/transactions/{transaction_id}/trust-record` returns a versioned JSON export containing the submitted invoice/evidence, verification result, audit hashes and limitations.

- `POST /v1/transactions/{transaction_id}/share-links` creates a random, expiring share token (1–720 hours; default 72).
- `GET /v1/transactions/{transaction_id}/share-links` lists share metadata without exposing tokens.
- `POST /v1/transactions/{transaction_id}/share-links/{share_id}/revoke` revokes a share.
- `GET /v1/shared/trust-records/{token}` returns the record to anyone holding the token until expiry or revocation.

The raw token is shown only once. Treat it as a bearer credential. Shared records are read-only and are not evidence of provider-authoritative verification.

### Correct and resubmit a transaction

`POST /v1/transactions/{transaction_id}/resubmit` accepts a corrected invoice/evidence payload and requires a new `Idempotency-Key`. Only review-required or rejected records can be superseded, and the invoice number must remain the same. The original transaction remains in history; the replacement links to it through `revision_of`. `GET /v1/transactions/{transaction_id}/revisions` returns the full revision chain. Supersession is appended to the audit hash chain and does not erase the original machine result or human review history.

### Organisation analytics

`GET /v1/analytics/summary` returns transaction counts by status, review rate, submitted invoice totals by currency and the most common failed checks. Optional `from_date` and `to_date` filters use UTC transaction creation dates. Amount totals represent submitted invoice values, not collected cash, revenue, receivables balances or lending exposure.

### Bulk transaction intake

`POST /v1/transactions/batch` accepts 1–50 transaction items. Each item must provide its own idempotency key and transaction payload. Results are reported per item, so a conflict on one item does not hide successful commits for other items. This is synchronous partial-success processing, not an asynchronous job queue.

### Human review workflow

- `GET /v1/reviews` lists organisation-scoped transactions awaiting human review.
- `GET /v1/reviews/{transaction_id}` returns the review decision history.
- `POST /v1/reviews/{transaction_id}/decision` records either `accepted_for_further_processing` or `rejected`, with a mandatory reason.

These routes require an API key with `bank-grade:admin`. A human disposition is stored separately and appended to the audit hash chain; it does not change the machine verification status or convert a `review_required` result into a machine-verified result.

### Institution risk settings

`GET /v1/risk-settings` and `PUT /v1/risk-settings` are restricted to API keys provisioned with `bank-grade:admin`. Policies are stored per organisation and can configure whether commercial/payment evidence is required, whether duplicate invoices/payment mismatches/counterparty conflicts are rejected, and an amount threshold that forces manual review. Defaults require both commercial and payment evidence and reject duplicate/conflicting records. Policy changes should be controlled by the institution's own approval process.

### API rate limits

The production middleware applies database-backed fixed one-minute windows. Defaults are 120 requests per minute per API key and 60 requests per minute per anonymous client IP. Configure with `API_RATE_LIMIT_PER_MINUTE` and `ANON_RATE_LIMIT_PER_MINUTE`. Requests over the limit receive HTTP `429` and a `Retry-After` header. Tune these limits with measured partner traffic before a production pilot.

### Production financial-source evidence

`POST /v1/sources/records` stores customer-submitted financial-source records as `unverified`. Customer-supplied provenance cannot promote a record to independently verified. Use `GET /v1/sources/records` to retrieve stored records and `GET /v1/sources/reconcile/{transaction_id}` for decision-support comparisons. A live provider adapter must establish authority separately.

### Verify stored records

`POST /verify-stored/{invoice_number}/{evidence_id}`

### Decision summary

`POST /verification-summary/{invoice_number}/{evidence_id}`

## Verification philosophy

The engine is deliberately explainable. Missing evidence is never silently treated as a pass. Each check is explicit, failed and incomplete checks are returned, conflicts are identified, and the result includes a verification score plus evidence attribution.

A `verified` result requires all four core invoice checks to pass without unresolved conflicts or incomplete fields, plus substantive commercial evidence (a purchase order or contract) and substantive payment evidence. A missing evidence category or conflicting result is `review_required`; a zero-check stored-record result is `rejected`. The score is a deterministic rule score, not a calibrated probability. These are verification states, not lending or credit decisions.

For multiple evidence records, a check is supported when at least one supplied evidence record provides a matching value. When multiple evidence records disagree on a populated field, the engine identifies the conflict and requires review rather than silently choosing a value.

## Testing

Run the full test suite with:

```bash
pytest -q
```

GitHub Actions runs the same suite on pushes to `main`, pull requests targeting `main`, and manual workflow dispatches.

## Production-readiness boundary

The repository contains a functional engineering MVP and a separate production-hardening branch. The branch adds API controls, database-backed rate limits, audit-chain improvements, batch intake, document integrity indicators, organisation-level risk policies, human review records, Trust Record exports/shares and analytics. Those changes are not live until merged and deployed.

The engine is not yet production-certified financial infrastructure. It has no live bank, mobile-money, PSP, accounting, ERP, registry, tax-authority or logistics provider connections. Its rule score is not a calibrated probability, and it does not make lending or credit decisions. Document anomaly signals are not proof of authenticity.

Institutional API onboarding and integration examples are documented in [docs/INSTITUTIONAL_API_GUIDE.md](docs/INSTITUTIONAL_API_GUIDE.md). External provider prerequisites and source-authority rules are documented in [docs/EXTERNAL_INTEGRATION_READINESS.md](docs/EXTERNAL_INTEGRATION_READINESS.md). The full 50-point implementation register is in [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md).

## Vision

The initial wedge is SME invoice and receivable verification for financial institutions. The longer-term ambition is to expand the trust layer across counterparties, payments, logistics and trade so African business activity becomes easier to verify, understand and finance.
