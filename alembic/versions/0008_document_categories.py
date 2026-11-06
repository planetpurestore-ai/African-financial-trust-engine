"""Add document category classification."""
from alembic import op
import sqlalchemy as sa

revision = "0008_document_categories"
down_revision = "0007_organization_risk_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "documents",
        sa.Column("category", sa.String(length=32), nullable=False, server_default="other"),
    )


def downgrade():
    op.drop_column("documents", "category")
