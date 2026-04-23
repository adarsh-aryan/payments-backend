from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from dotenv import load_dotenv

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

# Load variables from a local .env file if present
load_dotenv()

# Prefer a full DATABASE_URL if provided; otherwise try to build from individual PG vars; fall back to SQLite
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    pg_user = os.getenv("POSTGRES_USER")
    pg_pass = os.getenv("POSTGRES_PASSWORD")
    pg_host = os.getenv("POSTGRES_HOST", "localhost")
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    pg_db = os.getenv("POSTGRES_DB")
    if pg_user and pg_pass and pg_db:
        DB_URL = f"postgresql+psycopg2://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
    else:
        DB_URL = "sqlite:///./data.db"

# If using SQLite, ensure the target directory exists to avoid 'unable to open database file'
try:
    url = make_url(DB_URL)
    if url.drivername == "sqlite" and url.database and url.database != ":memory:":
        dirpath = os.path.dirname(url.database) or "."
        os.makedirs(dirpath, exist_ok=True)
except Exception:
    # Non-fatal; engine creation may still work if path is valid
    pass

# For SQLite, need check_same_thread=False for FastAPI multi-thread workers
connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}

engine = create_engine(DB_URL, echo=False, future=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def session_scope() -> Iterator:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
