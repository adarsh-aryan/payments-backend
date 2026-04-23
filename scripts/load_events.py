from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.models import Base
from app import crud


def load_events(path: Path) -> None:
    Base.metadata.create_all(bind=engine)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array of events")
    ingested = 0
    duplicates = 0
    with SessionLocal() as session:  # type: Session
        for raw in data:
            # Normalize to expected types
            created, dup = crud.ingest_event(session, raw | {"timestamp": raw["timestamp"]})
            if created:
                ingested += 1
            else:
                duplicates += 1
        session.commit()
    print(f"Ingested: {ingested}, Duplicates: {duplicates}, Total: {len(data)}")


if __name__ == "__main__":
    default = Path(__file__).resolve().parents[1] / "sample_events.json"
    load_events(default)
