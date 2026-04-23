from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from .models import Event, EventType, Merchant, OverallStatus, Transaction
from .utils import derive_status


def upsert_merchant(session: Session, merchant_id: str, merchant_name: str) -> Merchant:
    merchant = session.get(Merchant, merchant_id)
    if merchant is None:
        merchant = Merchant(id=merchant_id, name=merchant_name)
        session.add(merchant)
        session.flush()
    else:
        # keep latest name if changed
        if merchant.name != merchant_name:
            merchant.name = merchant_name
    return merchant


def ensure_transaction(
    session: Session,
    tx_id: str,
    merchant_id: str,
    amount: float | None,
    currency: str | None,
    ts: datetime,
) -> Transaction:
    tx = session.get(Transaction, tx_id)
    if tx is None:
        tx = Transaction(
            id=tx_id,
            merchant_id=merchant_id,
            amount=amount,
            currency=currency,
            created_at=ts,
            updated_at=ts,
        )
        session.add(tx)
        session.flush()
    else:
        # Preserve earliest created_at, update updated_at
        if ts < tx.created_at:
            tx.created_at = ts
        if ts > tx.updated_at:
            tx.updated_at = ts
        # Set amount/currency if missing
        if tx.amount is None and amount is not None:
            tx.amount = amount
        if tx.currency is None and currency is not None:
            tx.currency = currency
    return tx


def insert_event_if_new(
    session: Session,
    *,
    event_id: str,
    tx_id: str,
    merchant_id: str,
    etype: EventType,
    amount: float,
    currency: str,
    occurred_at: datetime,
    raw: str | None = None,
) -> bool:
    ev = Event(
        id=event_id,
        transaction_id=tx_id,
        merchant_id=merchant_id,
        type=etype,
        amount=amount,
        currency=currency,
        occurred_at=occurred_at,
        raw=raw,
    )
    session.add(ev)
    try:
        session.flush()  # Will raise on duplicate due to PK/unique
        return True
    except IntegrityError:
        session.rollback()  # rollback the failed INSERT only
        return False


def recompute_tx_status(session: Session, tx: Transaction) -> None:
    # Query booleans from events for this transaction
    q = (
        select(
            func.count(func.nullif(Event.type != EventType.payment_initiated, True)),
            func.count(func.nullif(Event.type != EventType.payment_processed, True)),
            func.count(func.nullif(Event.type != EventType.payment_failed, True)),
            func.count(func.nullif(Event.type != EventType.settled, True)),
            func.min(Event.occurred_at),
            func.max(Event.occurred_at),
        )
        .where(Event.transaction_id == tx.id)
    )
    initiated_c, processed_c, failed_c, settled_c, min_ts, max_ts = session.execute(q).one()

    has_initiated = (initiated_c or 0) > 0
    has_processed = (processed_c or 0) > 0
    has_failed = (failed_c or 0) > 0
    has_settled = (settled_c or 0) > 0

    payment_status, settlement_status, overall_status, discrep = derive_status(
        has_initiated, has_processed, has_failed, has_settled
    )

    tx.has_initiated = has_initiated
    tx.has_processed = has_processed
    tx.has_failed = has_failed
    tx.has_settled = has_settled
    tx.payment_status = payment_status
    tx.settlement_status = settlement_status
    tx.status = overall_status
    tx.discrepancy = discrep

    # Update created/updated based on event times if available
    if min_ts is not None and min_ts < tx.created_at:
        tx.created_at = min_ts
    if max_ts is not None and max_ts > tx.updated_at:
        tx.updated_at = max_ts


def ingest_event(session: Session, payload: dict) -> Tuple[bool, Optional[str]]:
    # Minimal validation and coercion are handled before calling this in API layer
    event_id = payload["event_id"]
    event_type = payload["event_type"]
    tx_id = payload["transaction_id"]
    merchant_id = payload["merchant_id"]
    merchant_name = payload["merchant_name"]
    amount = float(payload["amount"])  # normalize
    currency = payload["currency"]
    ts = payload["timestamp"]

    # Coerce types if they came in as strings
    if isinstance(event_type, str):
        event_type = EventType(event_type)
    if isinstance(ts, str):
        # Python 3.11+ handles RFC3339 with tz using fromisoformat
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))

    upsert_merchant(session, merchant_id, merchant_name)
    tx = ensure_transaction(session, tx_id, merchant_id, amount, currency, ts)

    created = insert_event_if_new(
        session,
        event_id=event_id,
        tx_id=tx_id,
        merchant_id=merchant_id,
        etype=event_type,
        amount=amount,
        currency=currency,
        occurred_at=ts,
    )

    if created:
        recompute_tx_status(session, tx)
        return True, None
    else:
        # Duplicate event (by event_id) => idempotent no-op
        return False, event_id


def list_transactions(
    session: Session,
    *,
    merchant_id: Optional[str] = None,
    status: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    sort_by: str = "updated_at",
    order: str = "desc",
    page: int = 1,
    page_size: int = 50,
):
    q = select(Transaction).options(joinedload(Transaction.merchant))

    if merchant_id:
        q = q.where(Transaction.merchant_id == merchant_id)
    if status:
        q = q.where(Transaction.status == status)
    if start:
        q = q.where(Transaction.updated_at >= start)
    if end:
        q = q.where(Transaction.updated_at <= end)

    total = session.execute(q.with_only_columns(func.count())).scalar_one()

    sort_col = {
        "updated_at": Transaction.updated_at,
        "created_at": Transaction.created_at,
        "amount": Transaction.amount,
    }.get(sort_by, Transaction.updated_at)

    if order == "asc":
        q = q.order_by(sort_col.asc().nullslast())
    else:
        q = q.order_by(sort_col.desc().nullslast())

    q = q.limit(page_size).offset((page - 1) * page_size)
    items = [row[0] for row in session.execute(q).all()]
    return total, items


def get_transaction_detail(session: Session, tx_id: str) -> Optional[Transaction]:
    q = (
        select(Transaction)
        .options(joinedload(Transaction.merchant), joinedload(Transaction.events))
        .where(Transaction.id == tx_id)
    )
    return session.execute(q).scalars().first()


def summary(
    session: Session,
    *,
    group_fields: List[str],
):
    cols = []
    if "merchant" in group_fields:
        cols.append(Transaction.merchant_id.label("merchant_id"))
    else:
        cols.append(func.null().label("merchant_id"))
    if "date" in group_fields:
        cols.append(func.strftime("%Y-%m-%d", Transaction.updated_at).label("date"))
    else:
        cols.append(func.null().label("date"))
    if "status" in group_fields:
        cols.append(Transaction.status.label("status"))
    else:
        cols.append(func.null().label("status"))

    q = select(*cols, func.count().label("tx_count"), func.coalesce(func.sum(Transaction.amount), 0).label("amount_sum")).group_by(*cols)
    rows = session.execute(q).all()
    return rows


def discrepancies(session: Session):
    q = select(Transaction).where(
        (
            # settled while payment failed
            and_(Transaction.has_settled.is_(True), Transaction.has_failed.is_(True))
        )
        |
        (
            # processed but never settled
            and_(Transaction.has_processed.is_(True), Transaction.has_settled.is_(False))
        )
        |
        (
            # flagged inconsistent explicitly
            Transaction.discrepancy.is_(True)
        )
    ).order_by(Transaction.updated_at.desc())
    return [row[0] for row in session.execute(q).all()]
