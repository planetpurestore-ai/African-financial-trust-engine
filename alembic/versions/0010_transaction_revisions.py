"""Link corrected transaction resubmissions to prior records."""
from alembic import op
import sqlalchemy as sa

revision = "0010_transaction_revisions"
down_revision = "0009_transaction_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("transactions", sa.Column("revision_of", sa.String(length=64), nullable=True))
    op.add_column("transactions", sa.Column("superseded_by_transaction_id", sa.String(length=64), nullable=True))
    op.create_index("ix_transactions_revision_of", "transactions", ["revision_of"])
    op.create_index("ix_transactions_superseded_by_transaction_id", "transactions", ["superseded_by_transaction_id"])


def downgrade():
    op.drop_index("ix_transactions_superseded_by_transaction_id", table_name="transactions")
    op.drop_index("ix_transactions_revision_of", table_name="transactions")
    op.drop_column("transactions", "superseded_by_transaction_id")
    op.drop_column("transactions", "revision_of")
