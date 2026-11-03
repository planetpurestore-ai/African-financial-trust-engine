# Financial-source integration guide

This is the single starting point for adding a real bank, mobile-money, accounting, or payment-provider connection to Trust Engine.

## Current boundary

The connector catalog is a readiness list, not a live connection. A provider marked **Not connected** must never be presented as authoritative. Do not paste provider secrets into the dashboard, source code, issue comments, or this document. Use the hosting platform's encrypted environment variables / secret store.

## Recommended implementation path

1. **Choose one provider and use case.** Record the country/market, account or merchant permissions, data fields, refresh/webhook model, sandbox availability, and commercial approval needed. Do not start with a generic "all banks" connector.
2. **Create a provider adapter.** Add a module under `app/integrations/providers/` implementing the interface below. Keep provider-specific OAuth/token handling, pagination, retries, rate limits, and response parsing inside that adapter.
3. **Normalize without overstating trust.** Map each provider event into the canonical payment-evidence fields: provider, provider transaction ID, reference, status, amount as a decimal string, ISO currency, sender, recipient, timestamp with timezone, provider event ID, source retrieval time, and raw-payload SHA-256. Preserve provenance. A manually uploaded record is not equivalent to a provider-authenticated record.
4. **Secure the connection.** Store credentials only as server-side secrets. Use least-privilege scopes, TLS, token refresh/rotation, timeouts, bounded retries, redacted logs, replay protection, and provider signature verification for webhooks. Never trust a caller-supplied provider name as proof of source.
5. **Make ingestion safe to retry.** Persist a unique key such as `provider + provider_account_id + provider_transaction_id`; repeated deliveries must not duplicate events. Handle out-of-order events, reversals/refunds, pending/failed states, timezone and currency normalization explicitly.
6. **Expose operational state.** Show disconnected, sandbox, connected, stale, degraded, permission denied, and revoked states separately. A green state must mean a real authenticated connection was checked successfully, not simply that credentials exist.
7. **Test before enabling production.** Add sanitized provider fixtures and tests for valid payloads, malformed payloads, invalid signatures, expired tokens, duplicate events, pagination, rate limits, timeouts, reversals, and cross-organization isolation. Test against the provider sandbox and reconcile sample events with the provider's own records.
8. **Review and release.** Obtain provider approval, legal/privacy review, retention rules, an incident procedure, monitoring, backup/restore proof, and a rollback plan. Enable production per institution only after sign-off.

## Adapter contract (implementation target)

Keep the interface intentionally small and provider-neutral:

- `healthcheck()` — return connection status, checked-at time, and non-secret diagnostic code.
- `fetch_transactions(cursor, start_at, end_at)` — fetch one bounded page and return normalized events plus the next cursor.
- `verify_webhook(raw_body, headers)` — validate the provider signature and timestamp before parsing; reject invalid/replayed requests.
- `normalize_event(payload)` — return a canonical event plus provenance, without asserting that the invoice itself is genuine.
- `map_to_evidence(event)` — create payment evidence only when required fields and provider status are acceptable; preserve the provider transaction ID and retrieval metadata.
- `capabilities()` — state exactly which endpoints and event types are supported.

The production adapter should be versioned and registered in `app/payment_adapters.py`. Keep secrets out of the adapter catalog response. The UI should obtain status from a server-side health check and persisted connection state, not from a hard-coded `live=True`.

## Provider onboarding checklist

- [ ] Provider chosen, supported market confirmed, commercial/legal access approved
- [ ] Sandbox credentials stored as encrypted server-side secrets
- [ ] OAuth/signature/authentication flow implemented and tested
- [ ] Canonical mapping and provenance fields documented
- [ ] Idempotency, pagination, retries, rate limits, reversals and replay protection tested
- [ ] Organization-scoped persistence and audit events verified
- [ ] UI health state and operator-facing failure reason implemented
- [ ] Sandbox reconciliation signed off
- [ ] Security/privacy/retention review completed
- [ ] Production credentials separately stored and connection explicitly enabled
- [ ] Live smoke test, monitoring, rollback and backup/restore tested

## Important

This repository currently has a provider-neutral catalog and normalization scaffolding. Those are extension points, not completed integrations. A bank-ready integration requires provider-specific credentials, access rights, implementation, tests, and approval. Do not use real customer financial records until the product's security, privacy, storage, and recovery controls have been reviewed.
