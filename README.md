# ReliefLink

Camera-fed inventory network for food banks, with disaster-aware demand forecasting and
smart reallocation between sites.

A webcam at each site counts shelf inventory with a Claude vision call and posts it to a
shared ledger. A forecasting agent watches live weather and FEMA disaster feeds and predicts
demand spikes per site. When a site is about to run short, an optimizer recommends what to
move from which surplus site, and the ops dashboard shows it all live.

## Team and sections

| Section | Owner | Folder | Status |
|---|---|---|---|
| Vision agent (camera to counts) | **Nehal** | [`vision_agent/`](vision_agent/) | Phase 1 |
| Disruption agent (weather + FEMA to forecasts) | **Pranav** | [`disruption_agent/`](disruption_agent/) | Phase 1 |
| Shared ledger (API + database) | **Vivaan + Akul** | [`ledger/`](ledger/) | Phase 1 |
| Dashboard (live ops view) | **Vivaan + Akul** | [`dashboard/`](dashboard/) | Phase 1 |
| Reallocation agent (optimizer + explainer) | **Everyone** | [`reallocation_agent/`](reallocation_agent/) | Phase 2, starts after Phase 1 lands |

Each folder has its own `README.md` with your task checklist, how to run your part on its
own, and a definition of done. **Start there.**

## Architecture

```
 vision_agent (Nehal)          disruption_agent (Pranav)
 camera/image -> Claude        api.weather.gov + OpenFEMA
 counts per category           demand forecast per site
        |                              |
        |  POST /snapshots             |  POST /forecasts
        v                              v
 +--------------------------------------------------+
 |        ledger/  (Vivaan + Akul)                   |
 |  FastAPI + SQLite: sites, snapshots, forecasts,   |
 |  capacity, routes  ->  /gaps (surplus/shortage)   |
 +--------------------------------------------------+
        |  GET /inventory /forecasts /gaps   ^
        v                                    |  POST /recommendations
 dashboard/ (Vivaan + Akul)          reallocation_agent (Phase 2)
 Streamlit: map, levels,             OR-Tools transport solve +
 alerts, approve button              Claude plain-English explainer
```

The **API contract** between all four sections lives in
[`docs/api-contract.md`](docs/api-contract.md). If you follow the contract, you can build
your section completely independently. Change the contract only after telling the team.

## Tech stack (chosen to be beginner friendly + AI friendly)

- **Python everywhere.** One language, one virtualenv, one `requirements.txt`.
- **SQLite** for the database. Zero setup, it is just a file (`relief.db`).
- **FastAPI** for the ledger. Auto-generated interactive docs at `http://localhost:8000/docs`
  where you can click "Try it out" on every endpoint.
- **Streamlit** for the dashboard. Pure Python, hot reloads on save.
- **Claude vision** (`claude-opus-4-8`) for counting, no model training needed.
- **OR-Tools** for the Phase 2 transportation solve.
- The repo ships `CLAUDE.md` / `AGENTS.md` so Claude Code, Cursor, etc. understand the
  project instantly. Ask your AI assistant to read your section's README before you start.

## Quickstart (everyone does this once)

```bash
git clone https://github.com/PranavAchar01/relieflink.git
cd relieflink

# 1. Create a virtualenv and install everything (Python 3.11+)
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Copy the env template (only Nehal needs a real ANTHROPIC_API_KEY)
cp .env.example .env

# 3. Seed the database with 4 demo sites + starting inventory
python -m ledger.seed

# 4. Start the ledger API (leave this running in one terminal)
uvicorn ledger.main:app --reload

# 5. In a second terminal: see it live
streamlit run dashboard/app.py
```

Smoke-test the agents against the running ledger (no API key needed):

```bash
python -m vision_agent.agent --site-id 1 --fake      # posts fake camera counts
python -m disruption_agent.agent --synthetic          # posts a fake storm forecast
```

Refresh the dashboard and you will see the numbers move.

## How we work

1. **Branch per person**: `nehal/vision`, `pranav/disruption`, `vivaan/ledger`, `akul/dashboard`.
2. Commit early and often, push your branch, open a PR to `main`.
3. CI (lint + tests) must be green before merging. One teammate reviews.
4. Run everything with `python -m <package>.<module>` **from the repo root** so imports work.
5. Never commit `.env` or `relief.db` (gitignored already).

## Phases

- **Phase 1 (now)**: each person makes their section real. The fake/demo modes already wired
  in mean the dashboard has data on day one, then real camera counts and real weather
  forecasts replace them as they land.
- **Phase 2 (together)**: once `/inventory` and `/forecasts` are flowing, we build
  `reallocation_agent/` as a team. The skeleton and a working OR-Tools toy example are
  already in the folder.
