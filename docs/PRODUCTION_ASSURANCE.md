# Trust Engine — Production Assurance

This document separates software-controlled production assurance from dependencies that require a bank, regulator, auditor, hosting operator, or external provider.

## Implemented in the application

- [x] PostgreSQL persistence with Alembic migrations
- [x] Organization-scoped data access and foreign-key isolation
- [x] API-key authentication with peppered hashes and one-time secret presentation
- [x] Separate operational read/write scopes and distinct administrative scope
- [x] Least-privilege default API-key policies; admin scope is not granted automatically
- [x] API-key revocation and expiry policy support
- [x] Request-size protection and validated request IDs
- [x] Security response headers and HTTPS HSTS behavior behind a reverse proxy
- [x] Idempotency keys and database uniqueness constraints
- [x] Duplicate invoice detection and explicit risk decisions
- [x] Multi-evidence verification for purchase orders, contracts, and payment records
- [x] Evidence conflict/incomplete handling
- [x] Tamper-evident audit hash chain with verification endpoint
- [x] Organization-scoped trust entities and relationships
- [x] Signed webhook verification and integration-event deduplication
- [x] Document SHA-256 fingerprints and extraction provenance
- [x] PDF extraction and OCR adapter boundary
- [x] Database-backed health endpoint
- [x] Non-root production container execution
- [x] Container healthcheck
- [x] Automated Python compilation and core assurance tests in GitHub Actions
- [x] Operational PostgreSQL backup script

## Required before real bank production

These cannot honestly be marked complete merely by changing application source code:

1. Run independent penetration testing and remediate findings.
2. Run production-sized load, concurrency, soak, and failure-injection tests.
3. Establish automated encrypted database backups and complete a documented restore drill.
4. Configure centralized monitoring, alerting, log retention, and incident-response/on-call procedures.
5. Use managed production secret/KMS facilities, rotate bootstrap/API/integration secrets, and document privileged access.
6. Move the current development/free hosting/database configuration to production SLA capacity.
7. Establish and test disaster recovery with explicit RPO/RTO targets.
8. Complete privacy, retention, residency, vendor-risk, legal, and compliance reviews.
9. Integrate and contract with authoritative banking/open-banking, mobile-money, and registry providers where required.
10. Complete customer UAT and bank-specific risk-policy calibration.

## Verification boundary

A 100% verification score means all configured rule checks passed against the supplied evidence. It does not by itself prove that the evidence is authentic or that an external institution has independently attested to the transaction. Authoritative-source integrations and independent controls strengthen that assurance.

## Release gate

Do not label the system bank-production-ready solely because CI is green. The release gate is: application controls implemented + CI green + independent security assessment passed + production infrastructure/DR controls tested + customer UAT passed + required external data-source integrations and contractual approvals completed.
