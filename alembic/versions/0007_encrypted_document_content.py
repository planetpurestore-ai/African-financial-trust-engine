"""Store encrypted original document bytes."""
from alembic import op
import sqlalchemy as sa

revision = "0007_encrypted_document_content"
down_revision = "0006_login_throttles"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("encrypted_content", sa.LargeBinary(), nullable=True))


def downgrade():
    op.drop_column("documents", "encrypted_content")
