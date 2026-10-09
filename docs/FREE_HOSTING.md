# No-cost hosting path for the current Trust Engine MVP

## Selected route: Antideploy Free

The user's constraint is strict: **no payment and no payment-card verification**. The current candidate is [Antideploy](https://antideploy.com/), whose published Free plan states that it includes one live server app and one PostgreSQL database, with no card required. It also limits the plan to 10 successful deployments per month, and apps sleep when idle. Review the provider's current plan before creating resources because free-tier terms can change.

Official provider information:
- [FastAPI + PostgreSQL deployment guide](https://antideploy.com/blog/how-to-deploy-a-fastapi-app-with-postgres-for-free)
- [Free hosting plan details](https://antideploy.com/blog/free-hosting-for-students-and-first-projects-in-india)
- [Agent/deployment instructions](https://antideploy.com/agent.md)

## Repository readiness

- `.python-version` pins Python 3.12.
- `requirements.txt` already includes FastAPI, Uvicorn, SQLAlchemy, Psycopg 3, multipart upload support, PDF parsing, and Alembic.
- `Procfile` explicitly starts `app.production_entry:app` so the host does not accidentally select the older prototype entry point.
- The production ASGI entry point is `app.production_entry:app`.
- The production database reads `DATABASE_URL` and converts common PostgreSQL URL prefixes to the Psycopg 3 dialect.
- Alembic migrations are stored in `alembic/`. Antideploy's published guide says it runs `alembic upgrade head` before release when Alembic is detected; confirm the deploy log actually shows successful migrations before relying on the service.

## Deployment steps

1. Sign up at Antideploy using its official website, without adding a payment method.
2. Connect GitHub and select `planetpurestore-ai/African-financial-trust-engine`.
3. Select the branch `build/authenticated-trust-engine-app` for this MVP PR, or merge the reviewed changes to `main` first if the provider only deploys the default branch.
4. Confirm the build detects FastAPI and the module `app.production_entry:app`. The server must bind to `0.0.0.0` and use the platform-provided `PORT`.
5. Create/attach the included PostgreSQL database. Confirm the platform injects `DATABASE_URL` and that migrations finish successfully.
6. Add the following environment variables as secrets in the host dashboard. Generate each as a long, random value; do not commit them to GitHub or share them in chat:
   - `API_KEY_PEPPER`
   - `BOOTSTRAP_TOKEN`
   - `DATABASE_URL` should be supplied by the attached database; do not replace it with a guessed value.
   - Leave `ALLOWED_ORIGINS` unset for the same-origin browser app unless a trusted separate origin is needed.
7. Deploy and open `/health`. Continue only if it reports `status: ok` and `database: ok`.
8. Open the root URL and use the first-time setup screen with `BOOTSTRAP_TOKEN` to create the first administrator. Keep the token private.
9. Test sign-up/bootstrap, login/logout, invoice and evidence upload, verification, transaction details, audit hashes, CSV export, and organization isolation on the live service.
10. Export the database and verify a restore procedure before storing any real business information.

## Important limits and safety boundaries

- A live deploy is not the same as production certification. The browser workflow must be tested against the actual hosted database.
- Free services may sleep, enforce usage limits, or change their terms. Keep regular database exports and never assume GitHub contains database records.
- Do not use real confidential financial documents until access control, data retention, backup/restore, security, privacy and incident-response checks have been reviewed.
- Uploaded documents are evidence submitted by a user; they are not independently verified bank records.
- Bank/mobile-money connectors remain disconnected until actual provider credentials, approved access and provider-specific tests exist.
- If Antideploy's account flow requires payment information or its free tier is unavailable, stop rather than accepting a paid trial. A no-card route must be verified in the actual signup flow.
