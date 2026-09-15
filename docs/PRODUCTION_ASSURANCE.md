# Production Assurance Baseline

This checklist separates software-controlled production assurance from dependencies that require a bank, regulator, or external provider.

## Software-controlled controls

- [x] Organization isolation
- [x] API-key authentication
- [x] Read/write authorization separation
- [x] Idempotency support
- [x] Audit hash-chain support
- [x] Document ingestion and extraction
- [x] Multi-evidence verification
- [x] Risk decisioning
- [x] Signed webhook support
- [x] Trust graph
- [x] Security event logging
- [x] Request IDs and baseline security headers
- [x] Automated production smoke/security tests added
- [ ] Concurrency/load testing in a production-like environment
- [ ] Backup restore drill
- [ ] Disaster-recovery runbook and recovery objective validation
- [ ] Centralized monitoring and alerting
- [ ] Secret rotation procedure and production KMS/secret manager
- [ ] Dependency/container vulnerability scanning
- [ ] Independent penetration test

## External dependencies

- [ ] Authoritative bank/open-banking connectivity
- [ ] Authoritative mobile-money connectivity
- [ ] External business/KYC/registry sources
- [ ] Production provider credentials and commercial agreements
- [ ] Bank UAT/security/vendor approval
- [ ] Data-processing/privacy/legal review

A successful verification score is a result of the configured evidence rules; it is not by itself proof that an external source is truthful. Authoritative integrations and bank controls are required for that assurance level.
