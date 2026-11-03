"""Add African transaction country attribution."""
from alembic import op
import sqlalchemy as sa

revision = "0008_transaction_country"
down_revision = "0007_encrypted_document_content"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("transactions", sa.Column("country_code", sa.String(length=2), nullable=True))
    op.add_column("transactions", sa.Column("country_name", sa.String(length=100), nullable=True))
    op.create_index("ix_transactions_country_code", "transactions", ["country_code"])
    # Existing records remain NULL; historic country is never inferred.
    

def downgrade():
    op.drop_index("ix_transactions_country_code", table_name="transactions")
    op.drop_column("transactions", "country_name")
    op.drop_column("transactions", "country_code")
