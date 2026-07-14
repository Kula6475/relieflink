# ReliefLink - agent/assistant instructions

Read [CLAUDE.md](CLAUDE.md) for the full project context (layout, ownership, commands,
conventions). Quick version:

- Python only. Install: `pip install -r requirements.txt`. Run modules from the repo
  root with `python -m package.module`.
- Sections communicate only through the ledger HTTP API. The contract is
  [docs/api-contract.md](docs/api-contract.md), read it before touching endpoints.
- Keep `ruff check .` and `pytest -q` green (CI enforces both).
- Each folder's README.md contains that owner's task checklist. Start there.
