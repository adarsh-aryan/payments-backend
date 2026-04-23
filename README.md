# Payments Reconciliation Service

FastAPI + SQLite backend to ingest payment lifecycle events, maintain transaction state, and expose reconciliation views.

## Quick Start

1. Create venv and install deps:

```
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Configure database via .env (optional, Postgres example):

```
cp .env.example .env  # or copy manually on Windows
# Edit .env to set DATABASE_URL or POSTGRES_* variables
```

3. Run API locally:

```
uvicorn app.main:app --reload
```

Service runs at http://127.0.0.1:8000. Interactive docs at `/docs`.

4. Seed with sample events (optional, uses the ~10k events from `sample_events.json`):

```
python scripts/load_events.py
```

## API Overview

- POST `/events` – Ingest one or many events. Idempotent on `event_id`.
- GET `/transactions` – List transactions with filters for `merchant_id`, `status`, date range (`start`, `end`), pagination, and sorting.
- GET `/transactions/{transaction_id}` – Details + event history.
- GET `/reconciliation/summary?group_by=merchant,status` – Aggregate by `merchant`, `date`, `status` (comma-separated).
- GET `/reconciliation/discrepancies` – Transactions with inconsistent payment vs settlement states.

### Status Semantics

- Payment status: `initiated`, `processed`, `failed`
- Settlement status: `pending`, `settled`
- Overall `status` used in filters and summaries:
  - `settled`: any settled event
  - `failed`: failed and not settled
  - `pending_settlement`: processed and not settled
  - `initiated`: initiated only
  - `inconsistent`: settled + failed, or both processed and failed without settled

## Data Model

- `merchants` – merchant id and name
- `transactions` – derived state for each `transaction_id` including flags, statuses, timestamps, and indexes for query performance
- `events` – immutable history, unique on `event_id` (idempotency)

Indexes: transactions by `merchant_id`, `status`, `updated_at`; events by `transaction_id, occurred_at`.

## Idempotency

`events.id` is unique. Re-ingesting the same event returns `duplicates += 1` and does not mutate state. State is recomputed only when a new (unique) event is added.

## Postman Collection

`postman_collection.json` includes examples for all endpoints: ingestion (single and batch), listing with filters, details, summaries, and discrepancies.

## Docker

Build and run:

```
docker build -t payments-svc .
docker run -p 8080:8080 payments-svc
```

## Deployment

Any container platform works (Render, Railway, Fly.io, Cloud Run, ECS/Fargate). Provide `DATABASE_URL` if using a managed DB; otherwise the default SQLite file is created in the container (ephemeral).

Example (Render) quick hints:
- Create a new Web Service from this repo
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Add persistent DB if required; otherwise ephemeral SQLite is fine for the demo

## Assumptions & Tradeoffs

- SQLite chosen for simplicity; schema and SQLAlchemy ORM compatible with Postgres/MySQL if swapped via `DATABASE_URL`.
- Overall `status` is derived for filtering and summaries; also store detailed payment/settlement flags for richer queries without scanning events.
- Discrepancies flagged for: processed but not settled; settled with a failed payment; both processed and failed without a settle.
- Duplicate event handling uses unique `event_id`; near-duplicate events with different ids are recorded, which is acceptable for this scope.

## Development Notes

- SQL-first mindset: filters, sorting, pagination, and aggregates happen in SQL.
- Pydantic v2 for fast validation and clear typing.
- Minimal surfaces, small helpers, and straightforward endpoints for reviewer clarity.
