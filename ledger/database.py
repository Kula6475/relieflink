"""SQLite engine and session helpers for the ledger.

The database is a single file (relief.db in the repo root). Delete it and re-run
`python -m ledger.seed` any time you want a fresh start.
"""

import os

from sqlmodel import Session, SQLModel, create_engine

DB_PATH = os.getenv("LEDGER_DB", "relief.db")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
