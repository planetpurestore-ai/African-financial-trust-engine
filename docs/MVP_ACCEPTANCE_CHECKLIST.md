# Trust Engine MVP acceptance checklist

This checklist defines the first usable, non-bank-connected MVP. A green CI run is necessary but does not replace a live browser smoke test.

## Core workflow to accept

- [ ] First administrator can be created once using the server-side bootstrap token.
- [ ] Administrator can sign in, refresh the page, and sign out.
- [ ] Each institution sees only its own transactions, documents, metrics, and audit events.
- [ ] A PDF with selectable text, image (when OCR credentials are configured), or text/CSV file can be uploaded.
- [ ] Extracted invoice fields can be copied into the verification form; the user reviews them before submission.
- [ ] A user can submit an invoice with purchase-order, contract, or payment-record evidence.
- [ ] The result explains passed checks, failed checks, missing evidence, conflicts, risk assessment, and decision.
- [ ] The transaction and audit event persist in the configured database.
- [ ] The audit hash chain can be checked and reports tampering/mismatch.
- [ ] The dashboard displays real database-backed metrics and transactions, not seeded figures.
- [ ] Transactions can be exported as CSV.
- [ ] The connection-readiness panel explicitly marks external providers as not connected until configured.

## Financial-source boundary

No bank or mobile-money source is represented as connected by default. The provider-neutral catalog and signed webhook ingestion are scaffolding only; they do not prove the origin or authenticity of an event on their own. A live connector is accepted only after all of the following exist:

1. An authorized provider agreement / supported API and credentials stored server-side.
2. Provider-specific authentication, token refresh and permission handling.
3. A versioned adapter that maps provider payloads into the normalized payment-evidence shape.
4. Signature validation where the provider supports signed webhooks; otherwise a documented authenticated polling flow.
5. Idempotency, duplicate handling, pagination, time-zone/currency normalization and replay protection.
6. Contract tests against provider sandbox fixtures, plus explicit tests for invalid signatures and malformed payloads.
7. Reconciliation against provider-side references and an auditable record of source, retrieval time and raw-payload hash.
8. An operator-visible state distinguishing connected, stale, permission-denied, degraded and disconnected sources.

Never mark a provider event as authoritative just because it was uploaded or accepted by a webhook. Until a live connector is completed and validated, manual evidence remains caller-supplied and must be described that way.

## Deployment acceptance

- [ ] Application is deployed on a free plan whose limits and suspension behaviour are understood.
- [ ] Persistent database and document storage are configured; no important data relies on an ephemeral filesystem.
- [ ] A database export and a restore test have been completed.
- [ ] HTTPS, session cookie settings, secrets, allowed origins and request-size limits are reviewed.
- [ ] The live health endpoint reports database connectivity.
- [ ] Smoke test the full workflow on a phone and a desktop browser.
- [ ] Do not use real customer financial documents until the security and privacy review is complete.

## Known scope limits

This MVP is a verification and evidence-management workflow, not a bank, credit bureau, lender, or regulated credit decision engine. It does not create independent truth from untrusted input. Production use still needs abuse controls, password recovery/MFA, security review, privacy/data-retention policies, monitoring, and tested backup/restore.