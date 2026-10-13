# Browser authentication and deployment notes

## What this increment adds

- Human sign-in with email and password
- PBKDF2-SHA256 password hashing (passwords are not stored in plain text)
- Random, hashed, revocable browser sessions with a 12-hour lifetime
- HttpOnly session cookies; HTTPS deployments mark the cookie Secure
- Organization-scoped dashboard, transaction, document and audit endpoints
- First-organization setup plus protected provisioning of additional organization administrators
- Dashboard identity and greeting from the authenticated account; system status from `/health`
- No seeded KPI numbers or sample transactions

The existing `X-API-Key` API remains for server-to-server integrations.

## Required deployment steps

1. Use the Render web service that points to this repository and runs Alembic migrations before starting the app.
2. Confirm `DATABASE_URL` points to the managed PostgreSQL database. Do not use the SQLite fallback for a multi-instance or production deployment.
3. Configure a long, random `BOOTSTRAP_TOKEN` as a Render secret. It authorizes initial setup and the provisioning of additional organization administrators. Never put it in frontend code or commit it to Git.
4. Deploy the migration through the normal reviewed deployment process.
5. Open the dashboard, choose **First-time setup**, and submit the bootstrap token, administrator details and organization name. This route only creates the first account once.
6. To provision another institution, an authorized operator must call `POST /v1/auth/organizations` with `X-Bootstrap-Token` and that institution's admin details. The admin then signs in normally.
7. Check `GET /health`, then test sign-in, sign-out, document upload, transaction verification and tenant isolation before using real institutional records.

## Current boundaries — not a claim of production certification

This is a foundation, not a completed regulated-finance product. Before a real institutional pilot, still add and test user invitations and lifecycle management, password reset, MFA, login throttling and abuse monitoring, CSRF defenses appropriate to the final deployment, formal security review, data-retention controls, backups/restore drills, monitoring/alerting, and provider credentials for OCR and external financial integrations. The current OCR path uses Google Vision only when its API key is configured. No live bank or mobile-money connection is implied by the UI.

The free Render PostgreSQL instance has a scheduled expiration date in Render; verify its status and arrange a suitable database plan or migration before that date. Do not rely on an expiring free database for production records.
