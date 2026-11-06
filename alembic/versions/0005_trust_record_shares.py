"""Expiring, revocable Trust Record share links."""
from alembic import op
import sqlalchemy as sa

revision = "0005_trust_record_shares"
down_revision = "0004_external_financial_records"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "transaction_share_links",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.String(64), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name="uq_transaction_share_token_hash"),
    )
    op.create_index("ix_transaction_share_links_org_tx", "transaction_share_links", ["organization_id", "transaction_id"])
    op.create_index("ix_transaction_share_links_expiry", "transaction_share_links", ["expires_at"])


def downgrade():
    op.drop_index("ix_transaction_share_links_expiry", table_name="transaction_share_links")
    op.drop_index("ix_transaction_share_links_org_tx", table_name="transaction_share_links")
    op.drop_table("transaction_share_links")
