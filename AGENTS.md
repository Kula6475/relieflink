# ReliefLink - agent/assistant instructions

Read [CLAUDE.md](CLAUDE.md) for full context (layout, ownership, commands, hard rules).
Quick version:

- One server runs everything: `uvicorn ledger.main:app --reload` serves the dashboard
  (`/`), the edge camera (`/camera`), and the API (`/docs`).
- Frontend is CDN React + Babel, **no build step**, Salesforce-style, **no rounded
  corners** (enforced in `web/styles.css`).
- Vision is edge YOLO (browser ONNX or Python ultralytics); camera frames never leave
  the device.
- The API contract is [docs/api-contract.md](docs/api-contract.md).
- Keep `ruff check .` and `pytest -q` green (CI enforces both).
