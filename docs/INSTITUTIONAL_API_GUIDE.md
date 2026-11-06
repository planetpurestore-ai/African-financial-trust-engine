# Institutional API integration guide

This guide is for an institution or authorised integration partner evaluating the Trust Engine API. It describes the current engineering-MVP contract; it is not a production certification or a statement that any bank, mobile-money, PSP, registry or ERP provider is connected.

## Base URL and API reference

Use the deployment URL supplied during partner onboarding. The interactive OpenAPI reference is available at `/docs` and the OpenAPI schema at `/openapi.json`.

All production API routes below are under `/v1`.

## Authentication and key handling

- Send the organisation API key in the `X-API-Key` header.
- Send a stable, unique `Idempotency-Key` for transaction submissions and retries.
- API keys are shown only once when created. Store them in a secrets manager; do not place them in browser code, mobile applications, source control or logs.
- Organisation bootstrap uses `POST /v1/organizations` with the deployment bootstrap credential in `X-Bootstrap-Token`. Bootstrap should be performed by an authorised operator, not by a public signup form.
- Revoke a key immediately if it is exposed. The key management routes are organisation-scoped; administrative actions require the appropriate admin-scoped key.
- Never send customer credentials, bank passwords, PINs or one-time codes to AFT.

Example request headers:

```http
X-API-Key: <organisation-api-key>
Idempotency-Key: <unique-request-id>
Content-Type: application/json
```

## Submit an invoice and evidence package

`POST /v1/transactions`

A minimal example:

```json
{
  "invoice": {
    "invoice_number": "INV-2026-0042",
    "supplier_name": "Example Supplier Ltd",
    "buyer_name": "Example Buyer Ltd",
    "amount": "125000.00",
    "subtotal": "100000.00",
    "tax_amount": "25000.00",
    "currency": "RWF",
    "issue_date": "2026-11-01",
    "due_date": "2026-11-30",
    "purchase_order_number": "PO-2026-019",
    "contract_reference": "CON-2026-011",
    "delivery_reference": "DN-2026-088"
  },
  "evidence": [
    {
      "evidence_id": "po-019",
      "evidence_type": "purchase_order",
      "reference_number": "PO-2026-019",
      "supplier_name": "Example Supplier Ltd",
      "buyer_name": "Example Buyer Ltd",
      "amount": "125000.00",
      "currency": "RWF"
    },
    {
      "evidence_id": "contract-011",
      "evidence_type": "contract",
      "reference_number": "CON-2026-011",
      "supplier_name": "Example Supplier Ltd",
      "buyer_name": "Example Buyer Ltd",
      "amount": "125000.00",
      "currency": "RWF"
    },
    {
      "evidence_id": "delivery-088",
      "evidence_type": "delivery_note",
      "reference_number": "DN-2026-088",
      "supplier_name": "Example Supplier Ltd",
      "buyer_name": "Example Buyer Ltd",
      "evidence_date": "2026-11-05"
    },
    {
      "evidence_id": "payment-042",
      "evidence_type": "payment_record",
      "reference_number": "BANK-REF-042",
      "supplier_name": "Example Supplier Ltd",
      "buyer_name": "Example Buyer Ltd",
      "amount": "125000.00",
      "currency": "RWF"
    }
  ]
}
```

Use the transaction response's `status`, `checks`, `failed_checks`, `conflicts`, `supporting_evidence`, `reference_checks` and audit identifiers. A retry with the same idempotency key and identical payload returns the original transaction result. Reusing the key with a different payload returns a conflict.

## Read and share a Trust Record

- `GET /v1/transactions/{transaction_id}` retrieves an organisation-scoped transaction.
- `GET /v1/transactions/{transaction_id}/trust-record` returns the versioned JSON Trust Record.
- `GET /v1/transactions/{transaction_id}/revisions` returns the immutable correction history.
- `POST /v1/transactions/{transaction_id}/share-links` creates an expiring read-only bearer link.
- `POST /v1/transactions/{transaction_id}/share-links/{share_id}/revoke` revokes a share.

Share tokens are bearer credentials. Distribute them only to authorised recipients, set the shortest useful expiry, and revoke them when no longer needed.

## Upload source documents

`POST /v1/documents` accepts a single document. `POST /v1/documents/batch` accepts up to ten files using multipart form field `files`. The current upload limits and accepted content types are enforced by the deployed API. Batch responses report each file separately; partial success is possible.

Document extraction and integrity indicators are aids to review. They do not prove that a document was issued by the named counterparty or that a transaction occurred.

## Institution review and risk controls

- `GET /v1/reviews` lists transactions awaiting review.
- `GET /v1/reviews/{transaction_id}` returns the review history.
- `POST /v1/reviews/{transaction_id}/decision` records a reasoned human disposition.
- `GET /v1/risk-settings` and `PUT /v1/risk-settings` read/update organisation policy.
- `GET /v1/analytics/summary` returns an organisation-scoped summary.

These administrative routes require an API key provisioned with `bank-grade:admin`. Human review is recorded separately and does not rewrite the machine verification result.

## Status interpretation

- `verified`: the configured evidence checks passed for the information submitted.
- `review_required`: required evidence is missing, incomplete, inconsistent or needs human review.
- `rejected`: a configured risk rule rejected the submission.

The numerical verification score is a deterministic rule score, not a probability of authenticity, creditworthiness or repayment. It is not a credit rating, lending decision, guarantee or recommendation to advance funds.

## Source authority and integration limits

A customer-uploaded statement, CSV or webhook payload is customer-submitted evidence and remains unverified unless the provider's identity and source authenticity are independently established. A signed webhook from a customer integration authenticates that integration channel; it does not prove that the original bank or payment provider issued the underlying event.

No bank, mobile-money, PSP, accounting, ERP, registry, tax-authority or logistics connection should be represented as live until provider access, consent, signatures, sandbox tests and production certification are complete. See [External integration readiness](EXTERNAL_INTEGRATION_READINESS.md).

## Error handling and retry guidance

| HTTP status | Meaning | Integration action |
|---|---|---|
| 400 | Malformed request or invalid request semantics | Correct the payload; do not blindly retry. |
| 401 / 403 | Missing/invalid key or insufficient privilege | Check key, scope and operator authorization. |
| 404 | Organisation-scoped record not found | Verify the transaction identifier and tenant context. |
| 409 | Idempotency conflict or invalid transaction state | Reconcile the existing record before retrying with a new key. |
| 413 / 415 | Upload too large or unsupported media | Reduce size or use a supported file format. |
| 422 | Schema or validation failure | Correct the field-level validation issue. |
| 429 | Rate limit exceeded | Respect `Retry-After` and apply exponential backoff with jitter. |
| 5xx | Server-side failure | Retry only with the same idempotency key; alert the integration operator if persistent. |

## Partner pilot checklist

Before a live pilot, both parties should agree on: permitted purposes and legal basis; customer consent and data-sharing terms; data retention and deletion; incident notification; support contacts and escalation; API key custody and rotation; rate limits; source provenance; dispute and correction handling; test scenarios; success metrics; and rollback/disable procedures.

The current deployment still requires live PostgreSQL/Render validation, independent security testing and provider-specific integration approval before production financial use.
