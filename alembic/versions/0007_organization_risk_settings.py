"""Per-organisation configurable risk settings."""
from alembic import op
import sqlalchemy as sa

revision = "0007_organization_risk_settings"
down_revision = "0006_api_rate_limits"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organization_risk_settings",
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organization_id"),
    )


def downgrade():
    op.drop_table("organization_risk_settings")
