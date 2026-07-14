# Shared Ledger (API + database)

**Owners: Vivaan + Akul** (you two also own [`dashboard/`](../dashboard/))

This is the single source of truth every other section reads from and writes to.
It is a FastAPI app backed by a SQLite file (`relief.db`). It already works, your
job is to finish the remaining endpoints and keep the contract stable.

## Run it

```bash
# from the repo root, with the virtualenv active
python -m ledger.seed              # create + fill relief.db (safe to re-run)
uvicorn ledger.main:app --reload   # start the API
```

Open **http://localhost:8000/docs**. Every endpoint has a "Try it out" button, use it
constantly while developing.

## Files you own

- `models.py` - the database tables
- `main.py` - the API endpoints
- `seed.py` - demo data
- `database.py` - engine/session plumbing (you rarely need to touch this)

## Your tasks

- [ ] Read [`docs/api-contract.md`](../docs/api-contract.md) top to bottom (10 min).
- [ ] Run the seed + server + `curl http://localhost:8000/inventory` and understand
      what "latest snapshot per (site, category)" means.
- [ ] **Build `GET /gaps`** (spec in the contract): for each (site, category), return
      `gap = predicted_demand - current count`. Positive = shortage, negative = surplus.
      This is the most important task, Phase 2 depends on it.
- [ ] **Build `POST /recommendations`**: validate that both sites exist and the category
      is valid, then store it with status `"proposed"`.
- [ ] **Build `POST /recommendations/{rec_id}/approve`**: set status to `"approved"`,
      404 if the id does not exist.
- [ ] Add tests for each new endpoint in `tests/test_ledger.py` (copy the existing
      test style, they run with plain `pytest`).
- [ ] Stretch: `GET /inventory/history?site_id=..&category=..` returning snapshots over
      time, so the dashboard can draw a trend line.

## Definition of done

`pytest` is green, `ruff check .` is clean, and Nehal + Pranav's agents plus the
dashboard all run against your API without changes on their side.

## Tips

- Copy an existing endpoint as your template, they all follow the same pattern.
- If the database gets into a weird state: `rm relief.db && python -m ledger.seed`.
- Ask Claude/Cursor: "read ledger/main.py and docs/api-contract.md, then help me
  implement GET /gaps" - the TODO block at the bottom of `main.py` is written for this.
