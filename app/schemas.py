from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Literal

from pydantic import BaseModel, Field, validator

from .models import OverallStatus, PaymentStatus, SettlementStatus, EventType


class EventIn(BaseModel):
    event_id: str = Field(..., alias="event_id")
    event_type: EventType
    transaction_id: str
    merchant_id: str
    merchant_name: str
    amount: float
    currency: str
    timestamp: datetime

    class Config:
        populate_by_name = True


class EventOut(BaseModel):
    id: str
    transaction_id: str
    merchant_id: str
    type: EventType
    amount: float
    currency: str
    occurred_at: datetime


class MerchantOut(BaseModel):
    id: str
    name: str


class TransactionOut(BaseModel):
    id: str
    merchant_id: str
    amount: Optional[float] = None
    currency: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    payment_status: PaymentStatus
    settlement_status: SettlementStatus
    status: OverallStatus
    discrepancy: bool
    merchant: Optional[MerchantOut]


class TransactionDetailOut(TransactionOut):
    events: List[EventOut]


class IngestResponse(BaseModel):
    ingested: int
    duplicates: int
    total: int


class TransactionsQuery(BaseModel):
    merchant_id: Optional[str] = None
    status: Optional[Literal[
        "initiated",
        "processed",
        "failed",
        "settled",
        "pending_settlement",
        "inconsistent",
    ]] = None
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    sort_by: Optional[Literal["updated_at", "amount", "created_at"]] = "updated_at"
    order: Optional[Literal["asc", "desc"]] = "desc"
    page: int = 1
    page_size: int = 50

    @validator("page", "page_size")
    def positive(cls, v):  # noqa: D401
        if v <= 0:
            raise ValueError("must be positive")
        return v


class PaginatedTransactions(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[TransactionOut]


class SummaryGroupBy(BaseModel):
    group_by: Optional[str] = Field(
        default="merchant,status",
        description="Comma separated fields: merchant,date,status",
    )


class SummaryRow(BaseModel):
    merchant_id: Optional[str] = None
    date: Optional[str] = None
    status: Optional[OverallStatus] = None
    tx_count: int
    amount_sum: float

