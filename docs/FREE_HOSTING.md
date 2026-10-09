# No-cost hosting path for the current Python MVP

## Recommended architecture

- **Web/API:** one Koyeb Free Web Service built from this repository's existing Dockerfile.
- **Database:** Neon Free PostgreSQL, kept separate from the app host so it does not disappear when the web instance sleeps or restarts.
- **Source control:** GitHub remains the source of truth for code and migrations.

This preserves the current FastAPI + SQLAlchemy + PostgreSQL design. The app uses a database URL and runs Alembic migrations in its container start command. Do not use SQLite or a local filesystem database on a sleeping/ephemeral host for important records.

## Free-tier caveats to understand before setup

- Koyeb's free web service is limited (512 MB RAM, 0.1 vCPU, 2 GB ephemeral disk) and scales to zero after an hour without traffic. It is appropriate for a small MVP/test, not production financial workloads.
- Koyeb documents a payment-method validation step. Its documentation says the Free Web Service itself is not charged, but if you do not want to enter a payment card at all, stop here rather than proceeding.
- Do not provision a paid Koyeb instance or a Koyeb database. Koyeb's free database has a small active-time allowance; use Neon Free PostgreSQL for persistent database storage instead.
- Neon Free has finite compute and storage quotas and can scale to zero. No free plan can be guaranteed unchanged forever; keep periodic exports and stay within quotas.
- This is a deployment plan, not proof that the app has already been deployed. It still needs account-specific setup and a live browser smoke test.

## Koyeb service settings

1. Create a Koyeb Web Service from GitHub and select this repository.
2. Choose Dockerfile build, use the repository root as the build context, and select the **Free** instance only.
3. Set the start command to the Dockerfile default; it runs Alembic migrations before starting FastAPI.
4. Set these environment variables as secrets, never in the repository:
   - `DATABASE_URL`: the Neon PostgreSQL connection string (prefer Neon’s pooled connection string for the web app).
   - `API_KEY_PEPPER`: a long, random secret used to hash API keys.
   - `BOOTSTRAP_TOKEN`: a separate long, random token used only for first-admin setup and authorized institution provisioning.
   - `ALLOWED_ORIGINS`: leave unset for same-origin browser use unless specific trusted origins are required.
5. Deploy, then check `/health`. It must report `status: ok` and `database: ok`.
6. Open the root URL, choose **First-time setup**, enter the `BOOTSTRAP_TOKEN` value and create the first administrator. Never paste that token into a public issue, chat, or source file.
7. Test login/logout, upload a text/PDF invoice, transfer extracted fields into the verification form, submit commercial and payment evidence, inspect the audit hash, export CSV, and test that a second institution cannot see the first institution's data.
8. Export the Neon database before major schema changes and verify that a restore is possible.

## Before using real financial records

Do not treat manual uploads as bank-verified facts. Keep all provider connectors marked disconnected until approved credentials, provider-specific authentication, contract tests, reconciliation and provenance logging have been implemented. Also complete a security/privacy review, rate limiting, password recovery/MFA, monitoring, retention policy, and backup/restore testing before an institutional pilot.

## Official plan references

- Koyeb free instance limits and scale-to-zero: https://www.koyeb.com/docs/reference/instances
- Koyeb pricing FAQ and payment-method validation: https://www.koyeb.com/docs/faqs/pricing
- Neon free-plan details: https://neon.com/blog/neon-free-plan-1-gb-per-project