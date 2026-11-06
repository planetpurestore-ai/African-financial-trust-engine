"""Persistent API rate-limit counters."""
from alembic import op
import sqlalchemy as sa

revision = "0006_api_rate_limits"
down_revision = "0005_trust_record_shares"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "api_rate_limits",
        sa.Column("bucket_key", sa.String(128), primary_key=True),
        sa.Column("window_key", sa.String(20), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_table("api_rate_limits")
