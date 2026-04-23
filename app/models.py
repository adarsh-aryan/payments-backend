from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Enum,
    DateTime,
    Numeric,
    Boolean,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


class PaymentStatus(str, enum.Enum):
    initiated = "initiated"
    processed = "processed"
    failed = "failed"
    unknown = "unknown"


class SettlementStatus(str, enum.Enum):
    pending = "pending"
    settled = "settled"


class OverallStatus(str, enum.Enum):
    initiated = "initiated"
    processed = "processed"
    failed = "failed"
    settled = "settled"
    pending_settlement = "pending_settlement"
    inconsistent = "inconsistent"


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    transactions = relationship("Transaction", back_populates="merchant")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True)
    merchant_id = Column(String, ForeignKey("merchants.id"), index=True, nullable=False)
    amount = Column(Numeric(18, 2), nullable=True)
    currency = Column(String(8), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    has_initiated = Column(Boolean, default=False, nullable=False)
    has_processed = Column(Boolean, default=False, nullable=False)
    has_failed = Column(Boolean, default=False, nullable=False)
    has_settled = Column(Boolean, default=False, nullable=False)

    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.unknown, index=True, nullable=False)
    settlement_status = Column(Enum(SettlementStatus), default=SettlementStatus.pending, index=True, nullable=False)
    status = Column(Enum(OverallStatus), default=OverallStatus.initiated, index=True, nullable=False)
    discrepancy = Column(Boolean, default=False, index=True, nullable=False)

    merchant = relationship("Merchant", back_populates="transactions")
    events = relationship("Event", back_populates="transaction", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_transactions_updated_at", "updated_at"),
        Index("ix_transactions_merchant_status", "merchant_id", "status"),
    )


class EventType(str, enum.Enum):
    payment_initiated = "payment_initiated"
    payment_processed = "payment_processed"
    payment_failed = "payment_failed"
    settled = "settled"


class Event(Base):
    __tablename__ = "events"

    id = Column(String, primary_key=True)  # event_id
    transaction_id = Column(String, ForeignKey("transactions.id"), index=True, nullable=False)
    merchant_id = Column(String, ForeignKey("merchants.id"), index=True, nullable=False)

    type = Column(Enum(EventType), nullable=False, index=True)
    amount = Column(Numeric(18, 2), nullable=False)
    currency = Column(String(8), nullable=False)
    occurred_at = Column(DateTime, nullable=False)
    raw = Column(String, nullable=True)  # optional raw json string

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    transaction = relationship("Transaction", back_populates="events")
    merchant = relationship("Merchant")

    __table_args__ = (
        UniqueConstraint("id", name="uq_events_id"),
        Index("ix_events_transaction_occurred", "transaction_id", "occurred_at"),
    )
