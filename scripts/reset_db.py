from __future__ import annotations

from app.db import engine
from app.models import Base


def reset() -> None:
    print(f"Using database: {engine.url}")
    # Drop and recreate all tables for a clean slate
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("Schema reset complete.")


if __name__ == "__main__":
    reset()
