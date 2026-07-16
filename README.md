# ReliefLink

> **ATLAS hosted MVP:** A new Next.js + Neon application now lives in
> [`vision_agent/web`](vision_agent/web). It adds organization-scoped auth, immutable
> inventory transactions, structured food-bank/vendor/logistics negotiation, deterministic
> bullwhip controls, OR-Tools allocation, multi-party human approvals, reservations, and
> an auditable operations dashboard. The FastAPI/SQLite app described below remains the
> working prototype and compatibility service.

Start the key-free ATLAS demo:

```bash
cd vision_agent/web
npm install
cp .env.example .env.local
npm run dev
```

Camera-fed inventory network for food banks, with disaster-aware demand forecasting and
smart reallocation between sites. **One server runs everything.**

Point any camera at a shelf: an on-edge YOLO model (running locally in the browser, no
cloud calls) counts what it sees, and when someone takes a can off the shelf the shared
ledger updates itself seconds later. Weather and FEMA feeds predict demand spikes per
site, an optimizer proposes transfers, and an ops director approves them from a
Salesforce-style CRM dashboard. Partners who live in spreadsheets can upload theirs and
get back a live-linked workbook that is always in sync with the ledger.

**Live demo: https://relieflink-iota.vercel.app** (dashboard at `/`, edge camera at
`/camera`, API docs at `/docs`). Hosted demo data lives in a throwaway database and
resets periodically; run locally for a persistent ledger.

## Quickstart

```bash
git clone https://github.com/PranavAchar01/relieflink.git
cd relieflink
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m ledger.seed                                # 4 demo sites + starting data
uvicorn ledger.main:app --reload                     # the whole platform, one process
```

Then open:

| URL | What |
|---|---|
| http://localhost:8000/ | **CRM dashboard** (React, Salesforce-style, auto-refreshes) |
| http://localhost:8000/camera | **Edge camera**: YOLOv8n in your browser, counts -> ledger |
| http://localhost:8000/docs | Interactive API docs (try every endpoint) |

Feed it data without any camera or API key:

```bash
python -m vision_agent.agent --site-id 3 --fake       # fake shelf counts
python -m disruption_agent.agent --synthetic           # fake storm forecasts
python -m reallocation_agent.agent                     # propose transfers from the gaps
```

## The demo story (2 minutes)

1. Open `/camera`, pick a site, hit Start. YOLO runs on-device; put bottles/apples/books
   in view and watch counts appear. Remove one, the ledger updates automatically and the
   dashboard's Inventory tab reflects it within 5 seconds.
2. Run the disruption agent (`--synthetic` fakes a severe storm + a FEMA declaration for
   Santa Cruz). The Forecasts tab lights up, Home shows shortages.
3. Run the reallocation agent. The Transfers tab shows the minimum-cost plan; click
   Approve.
4. Spreadsheets tab: upload the template with a new pantry's counts, a new site appears
   instantly; download the live workbook, always current, same link.

## Architecture

```
 browser /camera page          disruption_agent (Python)
 YOLOv8n via onnxruntime-web   api.weather.gov + OpenFEMA
 (or vision_agent/edge.py      -> per-category demand forecasts
  with ultralytics on any
  Python device)                        |
        | POST /snapshots               | POST /forecasts
        v                               v
 +---------------------------------------------------------------+
 |  ledger/  -  ONE FastAPI server (SQLite file relief.db)       |
 |  sites, snapshots, forecasts, capacity, routes                |
 |  /gaps (surplus vs shortage)   /recommendations (+approve)    |
 |  /spreadsheets/import + /export (live-linked workbook)        |
 |  serves: / (CRM dashboard)  /camera  /models/yolov8n.onnx     |
 +---------------------------------------------------------------+
        ^ GET /gaps /routes /capacity        | polls every 5s
        | POST /recommendations              v
 reallocation_agent (OR-Tools LP     web/ React CRM dashboard
 + optional Claude explainer)        (square corners, Lightning-style)
```

The API contract between all pieces lives in [`docs/api-contract.md`](docs/api-contract.md).

## Tech stack

- **Backend**: FastAPI + SQLite (SQLModel). One process, one file database.
- **Dashboard**: React 18 via CDN with Babel standalone, so there is **no build step,
  no Node required**. Styled after Salesforce Lightning: dense list views, stat cards,
  global search, and zero rounded corners (`border-radius: 0` enforced globally).
- **Edge vision**: YOLOv8n exported to ONNX (committed at `models/yolov8n.onnx`) running
  in-browser via onnxruntime-web on any device with a camera. A Python flavor
  (`vision_agent/edge.py`, `pip install ultralytics`) covers headless devices like a
  Raspberry Pi. Detection is fully local; only category counts are sent.
- **Forecasting**: live NWS alerts + OpenFEMA declarations, per-category multipliers,
  time-aware coverage, regression baseline (see `disruption_agent/`).
- **Optimization**: OR-Tools linear program with per-site truck capacity.
- **Spreadsheets**: openpyxl. Upload any .xlsx/.csv (flexible headers); the export is
  regenerated from the live ledger on every download.

## Team

| Area | Owner |
|---|---|
| Edge vision (`web/camera.*`, `vision_agent/`) | Nehal |
| Disruption forecasts (`disruption_agent/`) | Pranav |
| Ledger + dashboard (`ledger/`, `web/`) | Vivaan + Akul |
| Reallocation (`reallocation_agent/`) | everyone |

Workflow: branch per person, PR to `main`, CI (ruff + pytest) must be green.

## Notes

- Phone cameras need a secure context: `localhost` works out of the box; for a phone on
  the LAN, tunnel with ngrok/localtunnel or run uvicorn with `--ssl-keyfile`.
- The YOLO class mapping uses COCO stand-ins (bottle=can, book=boxed dry goods). The
  upgrade path is fine-tuning YOLOv8n on real shelf photos and re-running
  `python -m vision_agent.export_model`.
- `python -m vision_agent.agent --image photo.jpg` still works as a Claude-vision
  fallback for one-off photo counts (needs `ANTHROPIC_API_KEY`).
