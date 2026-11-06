# External integration readiness — Trust Engine

The current adapter catalogue is a capability inventory, not evidence of live connectivity. Every provider adapter must remain marked as not live until its sandbox and production paths have been exercised with authorised credentials and provider-confirmed webhooks.

## Provider onboarding checklist

Before enabling any source as provider-authoritative, complete all of the following:

1. Obtain the provider's current API/webhook documentation and sandbox access.
2. Obtain customer-authorised credentials, consent, scopes and data-processing permissions.
3. Configure credentials in the deployment secret manager; never commit them to Git or return them from the API.
4. Validate provider signatures using the provider's own signing scheme, timestamp tolerance and replay protections.
5. Map provider identifiers, amount, currency, status, transaction time, counterparty and reversals/refunds.
6. Persist the raw event hash, provider event ID, signature-validation result, source, retrieval time and normalised record.
7. Test duplicate delivery, out-of-order events, retries, reversals, partial failures and credential rotation.
8. Keep the source marked unverified until the provider's identity and signature have been independently validated.
9. Complete a production smoke test and partner sign-off before changing the adapter's live status.

## Integration dependencies

| Area | Candidate integration path | Required before implementation can be certified |
|---|---|---|
| Banks | Direct bank API or authorised open-banking aggregator | Provider selection, bank sandbox, OAuth/client credentials, account-holder consent, scopes, statement/transaction schema, production approval and data-processing agreement. |
| Mobile money | MTN MoMo, Airtel Money, M-Pesa or local operator APIs | Merchant/customer API access, sandbox and production credentials, callback registration, signature scheme, settlement/reversal semantics and operator approval. |
| PSPs | Flutterwave, Paystack or a country-specific PSP | Merchant account, test/live API keys, webhook signing documentation, event catalogue, refund/chargeback behaviour and production approval. |
| Accounting | QuickBooks, Xero, Sage or local accounting platforms | OAuth app registration, tenant consent, chart-of-accounts mapping, invoice/credit-note schemas, rate limits and customer test tenant. |
| ERP | SAP, Oracle NetSuite or other customer ERP | Customer-authorised integration account, environment access, journal-entry mapping, idempotency contract, approval controls and change-management sign-off. |
| Business registry | Official company registry or authorised data provider | Official API or permitted access method, terms of use, identifiers, update frequency, entity status semantics and legal approval. |
| Tax invoices | Rwanda Revenue Authority or the relevant national tax authority/e-invoicing provider | Official integration access, tax invoice schema, signature/QR validation method, sandbox, taxpayer consent and jurisdiction-specific legal review. |
| Logistics | Carrier, 3PL, warehouse or proof-of-delivery provider | Partner API/webhook, shipment/order references, delivery status vocabulary, timestamps, quantity/partial-delivery semantics and proof artefacts. |
| Counterparties | Official registry plus authorised identity/business-data providers | Legal basis, entity identifiers, consent/permissions, matching thresholds, correction/dispute path and source provenance. |
| Compliance | Independent legal, privacy and security specialists | Jurisdictional legal opinion, data-protection impact assessment, retention policy, cross-border transfer review, threat model, penetration test and incident-response plan. |

## Source-authority rules

- Customer-uploaded files and customer-submitted API records are unverified.
- A customer-signed webhook sent to AFT authenticates the customer integration channel; it does not by itself prove the original bank, mobile-money or PSP issued the event.
- Provider-authoritative status requires a verified provider identity/signature or an authenticated direct provider query, with provenance recorded.
- AFT must preserve the original payload hash and normalised representation so later corrections do not erase what was originally received.
- A provider's sandbox response is not production certification.

## Current state

The code contains adapter catalogue entries and generic signed webhook intake. The provider adapters are not live. No bank, mobile-money, PSP, registry, tax authority, accounting, ERP or logistics integration should be marketed as connected until the checklist above is completed and tested.
