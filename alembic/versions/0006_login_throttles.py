"""Add shared database-backed login throttling."""
from alembic import op
import sqlalchemy as sa

revision = "0006_login_throttles"
down_revision = "0005_user_auth"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_throttles",
        sa.Column("bucket_key", sa.String(64), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_table("login_throttles")
