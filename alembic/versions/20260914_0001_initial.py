"""Initial Trust Engine schema.

Revision ID: 20260914_0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "20260914_0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("organizations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(200), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("api_keys", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("key_hash", sa.String(128), nullable=False), sa.Column("label", sa.String(100), nullable=False), sa.Column("active", sa.Integer(), nullable=False, server_default="1"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("key_hash"))
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])
    op.create_table("transactions", sa.Column("id", sa.String(64), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("invoice_number", sa.String(120), nullable=False), sa.Column("payload", sa.Text(), nullable=False), sa.Column("status", sa.String(40), nullable=False, server_default="received"), sa.Column("idempotency_key", sa.String(255)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_transaction_idempotency"))
    op.create_index("ix_transactions_organization_id", "transactions", ["organization_id"])
    op.create_index("ix_transactions_invoice_number", "transactions", ["invoice_number"])
    op.create_table("audit_events", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("transaction_id", sa.String(64), sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False), sa.Column("decision", sa.String(40), nullable=False), sa.Column("score", sa.Numeric(6, 2), nullable=False), sa.Column("result_json", sa.Text(), nullable=False), sa.Column("previous_hash", sa.String(64), nullable=False), sa.Column("event_hash", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("event_hash"))
    op.create_index("ix_audit_events_organization_id", "audit_events", ["organization_id"])
    op.create_index("ix_audit_events_transaction_id", "audit_events", ["transaction_id"])
    op.create_table("documents", sa.Column("id", sa.String(64), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("filename", sa.String(255), nullable=False), sa.Column("content_type", sa.String(120), nullable=False), sa.Column("sha256", sa.String(64), nullable=False), sa.Column("text", sa.Text(), nullable=False), sa.Column("extraction_json", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_documents_organization_id", "documents", ["organization_id"])
    op.create_index("ix_documents_sha256", "documents", ["sha256"])
    op.create_table("integration_credentials", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("provider", sa.String(100), nullable=False), sa.Column("secret_hash", sa.String(128), nullable=False), sa.Column("active", sa.Integer(), nullable=False, server_default="1"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("organization_id", "provider", name="uq_integration_credential"))
    op.create_index("ix_integration_credentials_organization_id", "integration_credentials", ["organization_id"])
    op.create_table("integration_events", sa.Column("id", sa.String(64), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False), sa.Column("provider", sa.String(100), nullable=False), sa.Column("event_key", sa.String(255), nullable=False), sa.Column("event_type", sa.String(100), nullable=False), sa.Column("normalized_json", sa.Text(), nullable=False), sa.Column("received_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("organization_id", "provider", "event_key", name="uq_integration_event"))
    op.create_index("ix_integration_events_organization_id", "integration_events", ["organization_id"])
    op.create_index("ix_integration_events_provider", "integration_events", ["provider"])

def downgrade():
    op.drop_table("integration_events")
    op.drop_table("integration_credentials")
    op.drop_table("documents")
    op.drop_table("audit_events")
    op.drop_table("transactions")
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("organizations")
