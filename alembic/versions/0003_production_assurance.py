"""Production assurance constraints and least-privilege policy cleanup."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0003_production_assurance"
down_revision = "0002_bank_grade_controls"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "api_key_policies" in tables:
        # Administrative scope must never be granted automatically to ordinary API keys.
        rows = bind.execute(sa.text("SELECT key_hash, scopes FROM api_key_policies"))
        for key_hash, scopes in rows:
            cleaned = ",".join(s for s in (scopes or "").split(",") if s and s != "bank-grade:admin")
            bind.execute(sa.text("UPDATE api_key_policies SET scopes=:s WHERE key_hash=:h"), {"s": cleaned, "h": key_hash})
        op.create_index("ix_api_key_policies_org", "api_key_policies", ["organization_id"])
        op.create_index("ix_api_key_policies_expiry", "api_key_policies", ["expires_at"])
    if "security_events" in tables:
        op.create_index("ix_security_events_org_created", "security_events", ["organization_id", "created_at"])
    if "trust_relationships" in tables:
        op.create_index("ix_trust_relationships_org_created", "trust_relationships", ["organization_id", "created_at"])

def downgrade():
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    for table, index in [("trust_relationships", "ix_trust_relationships_org_created"), ("security_events", "ix_security_events_org_created"), ("api_key_policies", "ix_api_key_policies_expiry"), ("api_key_policies", "ix_api_key_policies_org")]:
        if table in tables and index in {i["name"] for i in inspect(bind).get_indexes(table)}:
            op.drop_index(index, table_name=table)
