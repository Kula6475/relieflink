# ReliefLink - context for AI assistants

Hackathon project: camera-fed food bank inventory network with disaster-aware demand
forecasting and reallocation. All Python. Four sections, each owned by a teammate.

## Layout and ownership

| Folder | What | Owner |
|---|---|---|
| `ledger/` | FastAPI + SQLite source of truth (sites, snapshots, forecasts, routes) | Vivaan + Akul |
| `dashboard/` | Streamlit ops view | Vivaan + Akul |
| `vision_agent/` | Camera/photo -> Claude vision counts -> POST /snapshots | Nehal |
| `disruption_agent/` | weather.gov + OpenFEMA -> demand forecasts -> POST /forecasts | Pranav |
| `reallocation_agent/` | Phase 2: OR-Tools transfer optimizer + Claude explainer | everyone |
| `shared/config.py` | CATEGORIES, LEDGER_URL, CLAUDE_MODEL constants | shared |
| `docs/api-contract.md` | The interface between sections. Read before changing any endpoint. | shared |

When helping a teammate, stay inside their folder unless they ask otherwise. Cross-section
changes go through docs/api-contract.md first.

## Commands (always from the repo root, venv active)

```bash
pip install -r requirements.txt        # one install for everything
python -m ledger.seed                  # reset + fill relief.db
uvicorn ledger.main:app --reload       # API at :8000, docs at /docs
streamlit run dashboard/app.py         # dashboard
python -m vision_agent.agent --site-id 1 --fake       # fake camera counts
python -m disruption_agent.agent --synthetic           # fake storm forecasts
python -m reallocation_agent.agent     # toy OR-Tools solve
ruff check . && pytest -q              # what CI runs, keep green
```

## Conventions

- Run modules with `python -m package.module` from the repo root (imports depend on it).
- Categories are the fixed list in `shared/config.py`, never invent new ones inline.
- Sections talk ONLY through the ledger HTTP API, never import each other's code or
  touch relief.db directly.
- Claude calls use the `anthropic` SDK with model from `shared.config.CLAUDE_MODEL`
  (default `claude-opus-4-8`), key from `ANTHROPIC_API_KEY` in `.env` (gitignored).
- Every agent has a no-key demo mode (`--fake` / `--synthetic`); keep those working.
- No secrets in code or commits.
