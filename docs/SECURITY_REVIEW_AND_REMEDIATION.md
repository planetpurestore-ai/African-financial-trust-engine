# Trust Engine: Security and Verification Assurance Review

**Review type:** source-code review and automated test hardening  
**Branch reviewed:** `build/authenticated-trust-engine-app`  
**Date:** 2026-10-21  
**Status:** partial engineering review; not an independent penetration test, certification, or bank approval.

## Scope

Reviewed authentication/session handling, organisation scoping in the browser API, API-key controls, document intake, verification/risk logic, database configuration, container configuration, and existing test/CI structure. Added adversarial verification regression tests in `tests/test_verification_assurance.py`.

## Confirmed strengths in source

- Passwords are salted and hashed using PBKDF2-HMAC-SHA256 (310,000 rounds in the browser-auth module).
- Browser session tokens are random, stored as hashes, expire after 12 hours, and can be revoked at logout.
- Browser transaction/document queries reviewed use organisation scoping.
- API keys are stored as hashes and support revocation; key-policy middleware enforces scopes and expiry when configured.
- Request middleware sets several security headers and enforces a Content-Length limit.
- Document ingestion has a nominal 10 MiB file limit and accepts a limited set of formats.
- The verification result exposes named checks, conflicts, missing evidence, and a score; missing commercial/payment evidence blocks a verified result.
- Docker image runs as a non-root user and includes a health check.

These are source-level observations, not proof that deployed configuration or every route is safe.

## Findings to resolve before sensitive customer data

### Critical / high priority

1. **No visible login throttling or account lockout.** The login handler verifies passwords but the reviewed code does not rate-limit attempts. Add shared, production-suitable rate limiting and alerting; test brute-force resistance.
2. **SQLite fallback can silently become the production database.** `app/production_db.py` defaults to `sqlite:///./trust_engine.db` if `DATABASE_URL` is absent. For a bank/customer production deployment, fail closed unless the approved managed database is explicitly configured, and verify persistent storage and backup coverage.
3. **Document size check occurs after an unbounded read.** The API reads the entire upload into memory before checking the 10 MiB limit. Change to a bounded/chunked read and enforce limits for chunked requests too.
4. **Evidence provenance/relationship limitations.** Current verification compares selected fields across submitted evidence and requires commercial and payment evidence types, but it does not establish that source records are independently authoritative or that every reference is linked to the invoice by an external system. Until authoritative sources are integrated, results must be described as document consistency checks, not proof that a transaction or payment genuinely occurred.
5. **Security posture has not been independently tested.** Automated tests do not replace a professional penetration test, dependency review, threat model, or customer security review.

### Medium priority

6. **Bootstrap secrets are powerful provisioning credentials.** Ensure `BOOTSTRAP_TOKEN` is a strong random secret, set only in server-side secret storage, never included in browser code/logs, rotated after provisioning, and disabled when no longer required.
7. **Proxy trust and secure-cookie configuration need deployment verification.** Session cookie security and HSTS use request/proxy scheme signals. Verify actual Render proxy behavior and ensure untrusted clients cannot control trusted forwarding headers.
8. **Request-size guard depends on Content-Length.** Confirm upstream limits reject oversized/chunked bodies and add bounded streaming enforcement in the application.
9. **Audit hash chain is not tamper-proof storage by itself.** An actor with write access to the database may be able to rewrite rows and recompute hashes. Consider external immutable/WORM export, restricted database roles, signed checkpoints, and retention controls.
10. **Backup/restore evidence is missing from reviewed repository artifacts.** Define RPO/RTO, automated backups, retention, access control, and prove restoration with a scheduled drill.
11. **Public API documentation is enabled.** Decide whether interactive docs should be public in production; if not, disable or restrict `/docs` and `/redoc`.
12. **CI coverage is branch-dependent.** The reviewed assurance workflow triggers on pushes to `main` and pull requests; ensure the actual release branch has required checks and branch protection before production changes are accepted.

## Verification regression tests added

The new test module covers:
- a consistent invoice/evidence package;
- conflicting payment amounts;
- missing payment evidence;
- missing commercial evidence;
- counterparty conflict;
- risk decision when payment is absent;
- duplicate invoice rejection signal.

These tests exercise the current decision rules; they do not establish statistical accuracy. Accuracy claims require a labelled, representative test corpus, independently adjudicated ground truth, false-positive/false-negative metrics, and thresholds approved by the customer.

## Required next gates

1. Fix findings 1–3 and validate production configuration.
2. Run the complete CI suite and test against the actual release commit.
3. Complete tenant-isolation, upload abuse, session, API-key, webhook and audit-tampering test plans.
4. Run a qualified external penetration test and remediate findings.
5. Demonstrate backup restoration and incident-response readiness.
6. Pilot with synthetic or explicitly authorised low-risk data; do not use sensitive production financial data until the above gates and customer approvals are satisfied.
