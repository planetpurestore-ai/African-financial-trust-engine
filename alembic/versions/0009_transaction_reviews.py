"""Persist human review decisions for transactions."""
from alembic import op
import sqlalchemy as sa

revision = "0009_transaction_reviews"
down_revision = "0008_document_categories"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "review_decisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.String(64), nullable=False),
        sa.Column("reviewer_api_key_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_api_key_id"], ["api_keys.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_review_decisions_organization_id", "review_decisions", ["organization_id"])
    op.create_index("ix_review_decisions_transaction_id", "review_decisions", ["transaction_id"])


def downgrade():
    op.drop_index("ix_review_decisions_transaction_id", table_name="review_decisions")
    op.drop_index("ix_review_decisions_organization_id", table_name="review_decisions")
    op.drop_table("review_decisions")
