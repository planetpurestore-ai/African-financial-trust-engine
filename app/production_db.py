import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, DateTime, Integer, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required for the production engine")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=1800)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    api_keys = relationship("ApiKey", back_populates="organization", cascade="all, delete-orphan")

class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    organization = relationship("Organization", back_populates="api_keys")

class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="received", nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key", name="uq_transaction_idempotency"),)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class IntegrationCredential(Base):
    __tablename__ = "integration_credentials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    active: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    __table_args__ = (UniqueConstraint("organization_id", "provider", name="uq_integration_credential"),)

class IntegrationEvent(Base):
    __tablename__ = "integration_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_json: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    __table_args__ = (UniqueConstraint("organization_id", "provider", "event_key", name="uq_integration_event"),)


def init_production_db():
    Base.metadata.create_all(engine)
