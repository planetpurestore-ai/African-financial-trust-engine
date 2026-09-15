"""External financial evidence records and verification provenance."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0004_external_financial_records"
down_revision = "0003_production_assurance"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "external_financial_records" not in tables:
        op.create_table(
            "external_financial_records",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("organization_id", sa.Integer(), nullable=False),
            sa.Column("provider", sa.String(100), nullable=False),
            sa.Column("authority", sa.String(30), nullable=False, server_default="unverified"),
            sa.Column("record_type", sa.String(60), nullable=False),
            sa.Column("provider_record_id", sa.String(255), nullable=False),
            sa.Column("reference", sa.String(255)),
            sa.Column("amount", sa.Numeric(18, 2)),
            sa.Column("currency", sa.String(10)),
            sa.Column("sender", sa.String(255)),
            sa.Column("recipient", sa.String(255)),
            sa.Column("occurred_at", sa.DateTime(timezone=True)),
            sa.Column("raw_hash", sa.String(64), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False),
            sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("organization_id", "provider", "provider_record_id", name="uq_external_financial_record")
        )
        op.create_index("ix_external_financial_records_org_reference", "external_financial_records", ["organization_id", "reference"])
        op.create_index("ix_external_financial_records_org_created", "external_financial_records", ["organization_id", "created_at"])


def downgrade():
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "external_financial_records" in tables:
        op.drop_index("ix_external_financial_records_org_created", table_name="external_financial_records")
        op.drop_index("ix_external_financial_records_org_reference", table_name="external_financial_records")
        op.drop_table("external_financial_records")
