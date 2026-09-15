"""Persistent bank-grade control tables."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision="0002_bank_grade_controls"
down_revision="20260914_0001"
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind(); tables=set(inspect(bind).get_table_names())
    if "api_key_policies" not in tables:
        op.create_table("api_key_policies",sa.Column("key_hash",sa.String(128),primary_key=True),sa.Column("organization_id",sa.Integer(),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True)),sa.Column("scopes",sa.Text(),nullable=False),sa.Column("revoked",sa.Integer(),nullable=False,server_default="0"),sa.Column("last_used_at",sa.DateTime(timezone=True)),sa.ForeignKeyConstraint(["organization_id"],["organizations.id"],ondelete="CASCADE"))
    if "trust_entities" not in tables:
        op.create_table("trust_entities",sa.Column("id",sa.String(64),primary_key=True),sa.Column("organization_id",sa.Integer(),nullable=False),sa.Column("entity_type",sa.String(60),nullable=False),sa.Column("external_id",sa.String(255),nullable=False),sa.Column("name",sa.String(255)),sa.Column("attributes_json",sa.Text(),nullable=False,server_default="{}"),sa.Column("verified",sa.Integer(),nullable=False,server_default="0"),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),sa.ForeignKeyConstraint(["organization_id"],["organizations.id"],ondelete="CASCADE"),sa.UniqueConstraint("organization_id","entity_type","external_id"))
    if "trust_relationships" not in tables:
        op.create_table("trust_relationships",sa.Column("id",sa.String(64),primary_key=True),sa.Column("organization_id",sa.Integer(),nullable=False),sa.Column("source_entity_id",sa.String(64),nullable=False),sa.Column("relationship_type",sa.String(80),nullable=False),sa.Column("target_entity_id",sa.String(64),nullable=False),sa.Column("evidence_id",sa.String(64)),sa.Column("confidence",sa.Numeric(5,2),nullable=False,server_default="0"),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),sa.ForeignKeyConstraint(["organization_id"],["organizations.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["source_entity_id"],["trust_entities.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["target_entity_id"],["trust_entities.id"],ondelete="CASCADE"))
    if "security_events" not in tables:
        op.create_table("security_events",sa.Column("id",sa.String(64),primary_key=True),sa.Column("organization_id",sa.Integer(),nullable=True),sa.Column("event_type",sa.String(100),nullable=False),sa.Column("subject",sa.String(255)),sa.Column("metadata_json",sa.Text(),nullable=False,server_default="{}"),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),sa.ForeignKeyConstraint(["organization_id"],["organizations.id"],ondelete="CASCADE"))

def downgrade():
    pass
