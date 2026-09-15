"""Bank-grade schema baseline.

This migration is intentionally idempotent at the table level so it can
adopt the already-running production database without destroying data.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0001_bank_grade_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _create_if_missing(bind, name, columns, constraints=None, indexes=None):
    inspector = inspect(bind)
    if name in inspector.get_table_names():
        return
    op.create_table(name, *columns, *(constraints or []))
    for idx in indexes or []:
        op.create_index(*idx)


def upgrade():
    bind = op.get_bind()

    _create_if_missing(bind, "organizations", [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ])

    _create_if_missing(bind, "api_keys", [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_hash", sa.String(128), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ], constraints=[sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash")], indexes=[("ix_api_keys_key_hash", "api_keys", ["key_hash"])] )

    _create_if_missing(bind, "transactions", [
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_number", sa.String(120), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="received"),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ], constraints=[sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_transaction_idempotency")], indexes=[("ix_transactions_organization_id", "transactions", ["organization_id"]), ("ix_transactions_invoice_number", "transactions", ["invoice_number"])])

    _create_if_missing(bind, "audit_events", [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transaction_id", sa.String(64), sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision", sa.String(40), nullable=False),
        sa.Column("score", sa.Numeric(6, 2), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("event_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ], constraints=[sa.UniqueConstraint("event_hash", name="uq_audit_events_event_hash")], indexes=[("ix_audit_events_organization_id", "audit_events", ["organization_id"]), ("ix_audit_events_transaction_id", "audit_events", ["transaction_id"])])

    _create_if_missing(bind, "documents", [
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("extraction_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ], indexes=[("ix_documents_organization_id", "documents", ["organization_id"]), ("ix_documents_sha256", "documents", ["sha256"])])

    _create_if_missing(bind, "integration_credentials", [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("secret_hash", sa.String(128), nullable=False),
        sa.Column("active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ], constraints=[sa.UniqueConstraint("organization_id", "provider", name="uq_integration_credential")], indexes=[("ix_integration_credentials_organization_id", "integration_credentials", ["organization_id"])])

    _create_if_missing(bind, "integration_events", [
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("event_key", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("normalized_json", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    ], constraints=[sa.UniqueConstraint("organization_id", "provider", "event_key", name="uq_integration_event")], indexes=[("ix_integration_events_organization_id", "integration_events", ["organization_id"]), ("ix_integration_events_provider", "integration_events", ["provider"])])


def downgrade():
    # Deliberately non-destructive: this baseline adopts an existing production
    # schema. Future revisions should carry reversible, explicit changes.
    pass
