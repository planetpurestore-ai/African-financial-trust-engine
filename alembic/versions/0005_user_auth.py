"Add user accounts and browser sessions."
from alembic import op
import sqlalchemy as sa

revision = "0005_user_auth"
down_revision = "0004_external_financial_records"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("user_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("full_name", sa.String(160), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("email_normalized", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(30), nullable=False, server_default="admin"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("email_normalized", name="uq_user_accounts_email_normalized"))
    op.create_index("ix_user_accounts_org", "user_accounts", ["organization_id"])
    op.create_table("user_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
    op.create_index("ix_user_sessions_user_expiry", "user_sessions", ["user_id", "expires_at"])

def downgrade():
    op.drop_index("ix_user_sessions_user_expiry", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_user_accounts_org", table_name="user_accounts")
    op.drop_table("user_accounts")
