# No-card hosting path for the Trust Engine MVP

## Selected route: Render Free web service + Neon Free PostgreSQL

This route is intended to avoid both charges and payment-card verification:
- **Web/API:** Render Free Web Service. Render's official first-deploy guide says no payment is required to create a free web service. Free instances sleep after 15 minutes idle and have an ephemeral filesystem.
- **Database:** Neon Free PostgreSQL. Neon states its free tier does not require a credit card; it has finite compute/storage quotas and can scale to zero.
- **Source control:** GitHub stores application code and schema migrations, not database records.

Official plan references:
- Render free deployment: https://render.com/docs/your-first-deploy
- Render free-service limitations: https://render.com/docs/free
- Neon free-plan details: https://neon.com/blog/neon-free-plan-1-gb-per-project

## Why a separate database matters

Do not rely on SQLite stored inside a free Render web service. Render's free web filesystem is ephemeral: data may disappear on restart, spin-down, or redeploy. Use Neon PostgreSQL for persistent transaction and audit data. Do not use the expiring Render Postgres instance as the permanent database.

## Service configuration

The production ASGI entry point is `app.production_entry:app`. The existing root Dockerfile installs requirements, runs `alembic upgrade head`, runs the runtime bootstrap, and starts Uvicorn on the platform-provided port.

Required secret environment variables:
- `DATABASE_URL`: Neon PostgreSQL connection string (use Neon’s pooled connection string for the app if available).
- `API_KEY_PEPPER`: a long, random secret.
- `BOOTSTRAP_TOKEN`: a separate long, random secret used for first-admin setup and authorized institution provisioning.
- `ALLOWED_ORIGINS`: leave unset for same-origin browser use unless a trusted separate origin is required.

Never commit secrets to GitHub or post them in issues. Set them in the Render dashboard.

## Deployment and verification checklist

1. Create a Neon account and a Free PostgreSQL project at https://neon.tech/; do not enter payment details.
2. Copy the PostgreSQL connection string from Neon. Keep it private.
3. Open the Render service dashboard, select **Environment**, and set the three required variables above. Set `DATABASE_URL` to the Neon connection string. Generate the two application secrets in your password manager or another trusted random-secret generator.
4. Confirm the service deploys from branch `build/authenticated-trust-engine-app` and the build log shows successful Alembic migrations.
5. Open `/health`; continue only if it reports `status: ok` and `database: ok`.
6. Open the root URL and use the first-time setup screen with `BOOTSTRAP_TOKEN` to create the first administrator. Keep the token private.
7. Test login/logout, document upload and extraction, evidence submission, verification, transaction details, CSV export, audit-chain checks, and organization isolation.
8. Verify persistence by creating a test transaction, restarting/redeploying the service, and confirming the record still exists in Neon.
9. Export the database and test a restore before storing any real business information.

## Current deployment status and safety boundary

The new free Render web service has been created from the authenticated MVP branch. Until Neon is connected, the app falls back to local SQLite, which is only suitable for a short smoke test and **must not be used for real records** because Render's free filesystem is ephemeral. The service is not considered complete until Neon is connected, the secrets are configured, the migrations succeed against Neon, and live browser tests pass.

Uploaded documents are evidence supplied by a user, not independently authenticated bank records. Bank/mobile-money connectors remain disconnected until real provider credentials, approved access and provider-specific tests exist. Free hosting is suitable for a prototype and acceptance testing, not production financial workloads.
