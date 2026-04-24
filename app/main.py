from __future__ import annotations

from datetime import datetime
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.models import Base, EventType
from . import crud
from app.schemas import (
    EventIn,
    IngestResponse,
    PaginatedTransactions,
    SummaryGroupBy,
    SummaryRow,
    TransactionDetailOut,
    TransactionOut,
)


def create_app() -> FastAPI:
    # Use lifespan instead of deprecated on_event for startup/shutdown hooks
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: ensure tables exist before serving
        Base.metadata.create_all(bind=engine)
        yield
        # Shutdown: nothing to clean up here

    app = FastAPI(title="Payments Reconciliation Service", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Tables are created in lifespan startup above

    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    @app.post("/events", response_model=IngestResponse)
    async def ingest_events(request: Request, db: Session = Depends(get_db)):
        payload = await request.json()
        events: List[Dict[str, Any]]
        if isinstance(payload, list):
            events = payload
        elif isinstance(payload, dict):
            events = [payload]
        else:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        ingested = 0
        duplicates = 0
        for raw in events:
            try:
                item = EventIn.model_validate(raw)
            except Exception as e:  # validation error
                raise HTTPException(status_code=400, detail=f"Invalid event: {e}") from e

            created, dup_id = crud.ingest_event(
                db,
                {
                    "event_id": item.event_id,
                    "event_type": item.event_type,
                    "transaction_id": item.transaction_id,
                    "merchant_id": item.merchant_id,
                    "merchant_name": item.merchant_name,
                    "amount": item.amount,
                    "currency": item.currency,
                    "timestamp": item.timestamp,
                },
            )
            if created:
                ingested += 1
            else:
                duplicates += 1

        db.commit()

        return IngestResponse(ingested=ingested, duplicates=duplicates, total=len(events))

    @app.get("/transactions", response_model=PaginatedTransactions)
    def list_transactions(
        merchant_id: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        start: Optional[datetime] = Query(None),
        end: Optional[datetime] = Query(None),
        sort_by: Optional[str] = Query("updated_at"),
        order: Optional[str] = Query("desc"),
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=500),
        db: Session = Depends(get_db),
    ):
        total, items = crud.list_transactions(
            db,
            merchant_id=merchant_id,
            status=status,
            start=start,
            end=end,
            sort_by=sort_by,
            order=order,
            page=page,
            page_size=page_size,
        )
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                TransactionOut(
                    id=t.id,
                    merchant_id=t.merchant_id,
                    amount=float(t.amount) if t.amount is not None else None,
                    currency=t.currency,
                    created_at=t.created_at,
                    updated_at=t.updated_at,
                    payment_status=t.payment_status,
                    settlement_status=t.settlement_status,
                    status=t.status,
                    discrepancy=t.discrepancy,
                    merchant={"id": t.merchant.id, "name": t.merchant.name} if t.merchant else None,
                )
                for t in items
            ],
        }

    @app.get("/transactions/{transaction_id}", response_model=TransactionDetailOut)
    def transaction_detail(transaction_id: str, db: Session = Depends(get_db)):
        t = crud.get_transaction_detail(db, transaction_id)
        if not t:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return TransactionDetailOut(
            id=t.id,
            merchant_id=t.merchant_id,
            amount=float(t.amount) if t.amount is not None else None,
            currency=t.currency,
            created_at=t.created_at,
            updated_at=t.updated_at,
            payment_status=t.payment_status,
            settlement_status=t.settlement_status,
            status=t.status,
            discrepancy=t.discrepancy,
            merchant={"id": t.merchant.id, "name": t.merchant.name} if t.merchant else None,
            events=[
                {
                    "id": e.id,
                    "transaction_id": e.transaction_id,
                    "merchant_id": e.merchant_id,
                    "type": e.type,
                    "amount": float(e.amount),
                    "currency": e.currency,
                    "occurred_at": e.occurred_at,
                }
                for e in sorted(t.events, key=lambda x: x.occurred_at)
            ],
        )

    @app.get("/reconciliation/summary", response_model=List[SummaryRow])
    def reconciliation_summary(group_by: str = Query("merchant,status"), db: Session = Depends(get_db)):
        fields = [f.strip() for f in group_by.split(",") if f.strip() in {"merchant", "date", "status"}]
        if not fields:
            fields = ["merchant", "status"]
        rows = crud.summary(db, group_fields=fields)
        out: List[SummaryRow] = []
        for merchant_id, date, status, tx_count, amount_sum in rows:
            out.append(
                SummaryRow(
                    merchant_id=merchant_id,
                    date=date,
                    status=status,
                    tx_count=int(tx_count),
                    amount_sum=float(amount_sum or 0),
                )
            )
        return out

    @app.get("/reconciliation/discrepancies", response_model=List[TransactionOut])
    def reconciliation_discrepancies(db: Session = Depends(get_db)):
        items = crud.discrepancies(db)
        return [
            TransactionOut(
                id=t.id,
                merchant_id=t.merchant_id,
                amount=float(t.amount) if t.amount is not None else None,
                currency=t.currency,
                created_at=t.created_at,
                updated_at=t.updated_at,
                payment_status=t.payment_status,
                settlement_status=t.settlement_status,
                status=t.status,
                discrepancy=t.discrepancy,
                merchant={"id": t.merchant.id, "name": t.merchant.name} if t.merchant else None,
            )
            for t in items
        ]

    return app


app = create_app()
