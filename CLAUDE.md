# ReliefLink - context for AI assistants

Disaster-aware food-bank inventory network with human-governed multi-organization
coordination. The primary hosted application is now the Next.js/Neon project under
`vision_agent/web`. The original FastAPI/SQLite application remains a working prototype
and supplies stateless OR-Tools and Claude-advisor endpoints during migration.

## Layout and ownership

| Path | What | Owner |
|---|---|---|
| `ledger/` | FastAPI + SQLite: API, queries, spreadsheet bridge, static serving | Vivaan + Akul |
| `web/` | React CRM dashboard (CDN React + Babel, NO build step) + edge camera page | Vivaan + Akul (dashboard), Nehal (camera) |
| `vision_agent/` | Python edge YOLO (`edge.py`), ONNX export helper, Claude/photo fallback | Nehal |
| `vision_agent/web/` | Next.js + Neon hosted app, immutable ledger, auth, ATLAS dashboard | shared |
| `atlas_optimizer/` | Stateless OR-Tools solve and Claude evidence explanation | shared |
| `disruption_agent/` | weather.gov + OpenFEMA -> demand forecasts | Pranav |
| `reallocation_agent/` | OR-Tools transfer optimizer + optional Claude explainer | everyone |
| `models/yolov8n.onnx` | Committed YOLO weights the browser camera page loads | Nehal |
| `shared/config.py` | CATEGORIES, LEDGER_URL, CLAUDE_MODEL | shared |
| `docs/api-contract.md` | The interface between all pieces. Read before changing endpoints. | shared |

## Commands (repo root, venv active)

```bash
pip install -r requirements.txt
python -m ledger.seed                     # reset + fill relief.db
uvicorn ledger.main:app --reload          # EVERYTHING: dashboard at /, camera at /camera, API at /docs
python -m vision_agent.agent --site-id 1 --fake     # fake counts (no key/camera)
python -m disruption_agent.agent --synthetic         # fake storm + FEMA declaration
python -m reallocation_agent.agent                   # solve gaps -> recommendations
ruff check . && pytest -q                 # what CI runs, keep green
```

## Hard rules

- **Hosted source of truth**: production ATLAS state lives only in Neon Postgres. Do not
  make the hosted app depend on the prototype SQLite database.
- **Human commitments**: every affected organization approves its own commitment. No
  agent can approve, reserve, dispatch, or receive for a human.
- **Hosted vision**: use still-image YOLO for visible package counting and a vision LLM
  for label/category interpretation. Always require operator and site-reviewer checks.
- The legacy UI and edge-camera rules below apply only to root `web/` and the Python
  prototype; they do not prohibit the separately built Next.js application.

- **Dashboard style**: Salesforce-Lightning-inspired, and **no rounded corners** ever
  (`* { border-radius: 0 !important }` in `web/styles.css` is intentional).
- **No build step for the frontend**: React comes from CDN, JSX is compiled in-browser
  by Babel standalone. Do not introduce npm/webpack/vite.
- **Edge-first vision**: YOLO runs on-device (browser via onnxruntime-web, or
  `ultralytics` in Python). Do not send camera frames to any cloud service; only counts
  are posted. `ultralytics` stays OUT of requirements.txt (optional dep).
- Categories are the fixed list in `shared/config.py`.
- Components talk only through the ledger HTTP API; agents never touch relief.db.
- Claude calls (photo fallback, plan explainer) use `shared.config.CLAUDE_MODEL`
  (default `claude-opus-4-8`); every flow must keep working WITHOUT an API key.
- No secrets in code or commits.
