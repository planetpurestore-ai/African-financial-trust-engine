# Trust Engine — 50-point implementation status

This register distinguishes code that exists from capabilities that have been independently tested, deployed, or validated with an external provider. "Implemented" does not mean production-certified.

## Reliability and security

| # | Improvement | Current assessment |
|---:|---|---|
| 1 | Test the production application independently | **In progress** — production entrypoint tests are being expanded; CI is running on the hardening branch. |
| 2 | Database persistence and migrations | **Implemented in code; deployment validation pending** — PostgreSQL support and Alembic migrations exist. |
| 3 | Organisation isolation | **Implemented in core queries; coverage needs expansion** — transaction, document, audit, and source queries are organisation-scoped. |
| 4 | API authentication and key controls | **Partially implemented** — hashed keys, expiry, scopes, revocation and bootstrap provisioning exist; operational policy needs further review. |
| 5 | Audit integrity | **Implemented in code; regression tests added** — hash-chain verification is being aligned with the writer and appends are serialized per organisation on PostgreSQL. |
| 6 | Consistent error handling | **Partial** — validation and endpoint errors exist; a unified production error policy is still needed. |
| 7 | Automated production tests | **In progress** — production tests and CI are being repaired and expanded. |
| 8 | Rate limiting | **Basic implementation** — fixed-window counters are stored in the shared database, with separate per-API-key and anonymous-IP limits; load testing and tuning remain. |
| 9 | Structured application logging | **Partial implementation** — request method/path/status/duration and request ID are logged; bearer share tokens are redacted from paths. Central log shipping and alerting remain. |
| 10 | Health monitoring | **Basic implementation** — database health endpoint and container health check exist; external uptime/alerting is not configured. |

## Verification engine

| # | Improvement | Current assessment |
|---:|---|---|
| 11 | Better invoice field extraction | **Partial** — PDF text, OCR adapter and deterministic extraction exist; layout coverage and extraction accuracy need a labelled test corpus. |
| 12 | Authenticity/manipulation indicators | **Partial implementation** — PDF active actions/scripts, embedded files, encryption, multiple revision markers, signature-field presence and text control characters can trigger review; these are heuristics, not authenticity proof or cryptographic signature verification. |
| 13 | Duplicate invoice detection | **Basic implementation** — duplicate invoice numbers are flagged within an organisation; cross-source/fuzzy duplicate detection remains. |
| 14 | Mathematical validation | **Partial implementation** — exact-decimal subtotal + tax = invoice total validation is available when those fields are supplied/extracted; line-item, discount, withholding and multi-currency tax rules remain. |
| 15 | Supplier/buyer consistency | **Implemented for supplied evidence** — populated party names are compared and conflicting values require review. |
| 16 | Purchase-order matching | **Partial** — PO evidence can support the invoice checks; line-item, quantity and delivery matching remain. |
| 17 | Contract matching | **Partial** — contract evidence is accepted as commercial evidence; clause/term-level matching remains. |
| 18 | Delivery evidence matching | **Not implemented** — delivery notes, proof of delivery and logistics events are not integrated into verification. |
| 19 | Confidence levels | **Partial** — a deterministic score is returned; it is not a calibrated probability and should not be presented as one. |
| 20 | Institution-configurable risk rules | **Basic implementation** — organisation-scoped policies configure evidence requirements, duplicate/conflict decisions and an amount threshold; more granular, versioned rule builders remain. |
| 21 | Explainability | **Implemented at MVP level** — checks, failed checks, conflicts and supporting evidence are returned. |
| 22 | Human review workflow | **Basic implementation** — admin-scoped review queue, reasoned decisions, review history and hash-chained audit events exist; named reviewer roles, assignment and maker-checker approval remain. Machine verification status is not overwritten. |

## SME experience

| # | Improvement | Current assessment |
|---:|---|---|
| 23 | Simplified SME submission | **Partial** — document and transaction intake APIs exist; a complete guided SME onboarding/submission flow remains. |
| 24 | Multiple-document upload | **Basic implementation** — batch endpoint accepts up to ten files and reports per-file success/failure; overall request size remains capped. |
| 25 | Document categorisation | **Basic implementation** — rule-based invoice, PO, contract, payment-record and delivery-note suggestions are persisted and returned; user override and classifier accuracy testing remain. |
| 26 | Upload progress indicators | **Not independently verified** — requires browser-level UX testing and implementation if absent. |
| 27 | Verification status tracking | **Basic implementation** — transaction status is stored and returned. |
| 28 | Downloadable Trust Record | **Basic implementation** — a versioned JSON export includes submitted evidence, verification, audit hashes and limitations; PDF signing and external verification remain. |
| 29 | Transaction history | **Implemented at API level** — organisation-scoped transaction listing exists. |
| 30 | Correction/resubmission | **Not implemented** — immutable versioning and resubmission workflow remain. |
| 31 | Secure record sharing | **Basic implementation** — random token links expire, can be revoked, are stored hashed, and record access is counted; shared links are bearer credentials and need rate limiting/penetration testing. |
| 32 | Mobile responsiveness | **Needs device testing** — no claim of complete mobile QA is made. |

## Institutional partner experience

| # | Improvement | Current assessment |
|---:|---|---|
| 33 | Institutional dashboard | **Partial** — dashboard variants exist; role-based, institution-ready workflows need validation. |
| 34 | Reviewer permissions | **Partial** — human review routes are restricted to admin-scoped keys; named users, reviewer roles and granular separation of duties remain. |
| 35 | Institution-specific risk settings | **Basic implementation** — admin-only GET/PUT settings are persisted per organisation; reviewer roles, version history and maker-checker approval remain. |
| 36 | API integration documentation | **Partial** — OpenAPI docs and API documentation exist; partner onboarding guides and examples need completion. |
| 37 | API sandbox | **Not implemented** — a separate isolated sandbox environment and test data are required. |
| 38 | Webhook notifications | **Partial** — signed inbound webhook intake and event deduplication exist; outbound notifications and retry handling remain. |
| 39 | Bulk transaction processing | **Basic implementation** — batch endpoint accepts up to 50 transactions with per-item idempotency and partial outcomes; asynchronous jobs, progress polling and retry queues remain. |
| 40 | Reporting and analytics | **Basic implementation** — organisation-scoped API summary reports transaction status, review rate, invoice totals by currency and common failed checks; large-scale pagination, scheduled exports and institution-specific reporting remain. |

## External dependencies and trust network

| # | Improvement | Current assessment |
|---:|---|---|
| 41 | Live bank connections | **External dependency** — adapter framework only; no live bank connection is active. |
| 42 | Live mobile-money connections | **External dependency** — no live M-Pesa, MTN MoMo or Airtel Money connection is active. |
| 43 | Live Flutterwave/Paystack connections | **External dependency** — provider-specific credentials, contracts and verified webhook configuration are required. |
| 44 | Accounting integrations | **Not connected** — provider-specific integration and customer access are required. |
| 45 | ERP integrations | **Not connected** — customer-specific API access and mapping are required. |
| 46 | Government business-registration verification | **External dependency** — official registry access or authorised data provider is required. |
| 47 | Tax-invoice verification | **External dependency** — country-specific tax authority access and legal approval are required. |
| 48 | Logistics/delivery verification | **External dependency** — carrier, logistics platform or buyer/supplier evidence partnerships are required. |
| 49 | Independent counterparty verification | **Partial** — a tenant-scoped trust graph exists; independent registry/identity evidence is not connected. |
| 50 | Regulatory and compliance validation | **External professional work** — jurisdiction-specific legal, privacy, security and financial-sector review is required. |

## Current hardening branch

The working branch `aft/production-hardening-2026-11` contains:
- Bounded document reads and basic file-signature checks.
- Audit-chain canonicalization correction and per-organisation transaction serialization.
- Financial-source ingestion mounted in the production app, with client-submitted records forced to `unverified`.
- API scope enforcement for financial-source routes.
- Bootstrap-token provisioning for the first admin key, with admin removed from ordinary default scopes.
- Idempotency-key payload conflict detection.
- Exact decimal preservation in invoice extraction and source-record persistence.
- Versioned downloadable Trust Record JSON export.
- Expiring, revocable Trust Record share links with hashed tokens, access counts and a database migration.
- Structured request logs with request IDs, timing, status and share-token redaction.
- Database-backed fixed-window API rate limits for authenticated and anonymous requests.
- Per-organisation risk settings with admin-only policy updates and policy-aware verification decisions.
- Admin-scoped human review queue and reasoned review decisions appended to the audit hash chain without rewriting machine outcomes.
- Multi-document upload endpoint with per-file partial-success reporting.
- Exact-decimal subtotal/tax/total validation and extraction fields.
- Conservative PDF/text integrity anomaly indicators attached to document extraction results.
- Persisted rule-based document categories for invoice, PO, contract, payment and delivery-note files.
- Bulk transaction intake endpoint with per-item idempotency and partial-success results.
- Organisation-scoped analytics summary for statuses, review rates, submitted invoice totals and failed checks.
- Regression tests for upload validation, audit verification, source authority, admin bootstrap, and idempotency.

This branch is not yet merged or deployed. Passing CI is not a substitute for production database testing, penetration testing, external provider certification, or a live institutional pilot.
