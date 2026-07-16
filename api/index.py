"""Vercel entrypoint: the same FastAPI app, adapted to serverless.

Vercel's filesystem is read-only except /tmp, so the demo database lives there
and is re-seeded on cold start. Data resets whenever the instance recycles;
that is fine for the hosted demo (run locally for a persistent ledger).
"""

import os

if os.environ.get("VERCEL"):
    os.environ.setdefault("LEDGER_DB", "/tmp/relief.db")

from ledger.main import app  # noqa: E402,F401

if os.environ.get("VERCEL"):
    from sqlmodel import Session, select

    from ledger import seed as _seed
    from ledger.database import engine
    from ledger.models import Site

    with Session(engine) as _session:
        if _session.exec(select(Site)).first() is None:
            _seed.seed()
