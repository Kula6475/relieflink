# ReliefLink - context for AI assistants

Camera-fed food bank inventory network with disaster-aware forecasting and reallocation.
**One FastAPI server runs everything**: the JSON API, the React CRM dashboard, the edge
camera page, and the YOLO model file.

## Layout and ownership

| Path | What | Owner |
|---|---|---|
| `ledger/` | FastAPI + SQLite: API, queries, spreadsheet bridge, static serving | Vivaan + Akul |
| `web/` | React CRM dashboard (CDN React + Babel, NO build step) + edge camera page | Vivaan + Akul (dashboard), Nehal (camera) |
| `vision_agent/` | Python edge YOLO (`edge.py`), ONNX export helper, Claude/photo fallback | Nehal |
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
