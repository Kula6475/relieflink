# ReliefLink API Contract

The interface between all four sections. Build against this and you never block each
other. Change it only after telling the team (it breaks everyone downstream).

Base URL: `http://localhost:8000` (override with `LEDGER_URL` in `.env`).
Interactive docs with try-it-out: `http://localhost:8000/docs`.

The hosted ATLAS application is a separate Next.js service under `vision_agent/web`.
Its base URL is `http://localhost:3000` in development and it uses Neon Postgres as
its source of truth. The legacy endpoints below remain unchanged for Python-prototype
compatibility.

**Categories** (exact strings, everywhere): `canned_goods`, `produce`, `dairy`, `dry_goods`.

## Implemented endpoints

### GET /sites
```json
[{"id": 1, "name": "Oakland Community Food Bank", "county": "Alameda",
  "state": "CA", "lat": 37.8044, "lon": -122.2712}]
```

### POST /snapshots  (vision agent -> ledger)
Request:
```json
{"site_id": 1, "category": "canned_goods", "count": 212,
 "confidence": 0.91, "source": "vision"}
```
201 on success. 422 for a bad category, 404 for an unknown site.
`source` is one of `vision | fake | manual | test`.

### GET /inventory[?site_id=N]
The **latest** snapshot per (site, category), i.e. current stock:
```json
[{"id": 17, "site_id": 1, "category": "canned_goods", "count": 212,
  "confidence": 0.91, "source": "vision", "created_at": "2026-07-14T18:02:11"}]
```

### POST /forecasts  (disruption agent -> ledger)
```json
{"site_id": 3, "category": "canned_goods", "predicted_demand": 480,
 "multiplier": 2.0, "horizon_hours": 48,
 "reason": "Winter Storm Warning (Severe): ...", "source": "weather.gov"}
```

### GET /forecasts[?site_id=N]
Latest forecast per (site, category), same shape as the POST plus `id`/`created_at`.

### GET /capacity
```json
[{"id": 1, "site_id": 1, "trucks": 3, "max_load_units": 400}]
```

### GET /routes
Symmetric distances, stored once per pair:
```json
[{"id": 1, "from_site_id": 1, "to_site_id": 2, "miles": 40.0, "drive_minutes": 50}]
```

### GET /recommendations
List of proposed/approved transfers (empty until Phase 2).

### GET /gaps
For each (site, category) that has both an inventory count and a forecast:
```json
[{"site_id": 3, "category": "canned_goods", "current": 60,
  "predicted_demand": 480, "gap": 420}]
```
`gap = predicted_demand - current`. Positive = shortage, negative = surplus.
Pairs with no forecast are skipped.

### POST /recommendations  (reallocation agent -> ledger)
```json
{"from_site_id": 1, "to_site_id": 3, "category": "canned_goods",
 "quantity": 150, "reason": "Site 3 shortfall of 420 under storm forecast"}
```
Both sites and the category are validated. Stored with `status: "proposed"`.

### POST /recommendations/{id}/approve
No body. Sets `status` to `"approved"`, returns the updated recommendation.
404 if the id does not exist.

### POST /optimizer/atlas  (hosted ATLAS -> stateless Python OR-Tools)

This endpoint performs no ledger reads or writes. ATLAS sends already-authorized,
validated supply and logistics data; the service returns a deterministic minimum-cost
allocation.

```json
{
  "requested_quantity": 150,
  "sources": [
    {"source_id": "site_oakland", "source_type": "site",
     "organization_id": "org_oakland", "available_quantity": 100,
     "capacity_quantity": 100, "distance_miles": 28,
     "earliest_pickup": "2026-07-17T15:00:00Z", "refrigerated": false}
  ]
}
```

Response:

```json
{"allocations": [{"source_id": "site_oakland", "quantity": 100,
  "estimated_cost": 2800}], "unfilled_quantity": 50}
```

### POST /atlas/advisor

Accepts validated proposal evidence and an optional operations-director question. The
Claude node uses `shared.config.CLAUDE_MODEL`; without `ANTHROPIC_API_KEY` it returns a
deterministic explanation. It may explain but never calculates quantities, determines
permissions, or changes state.

## Hosted Next.js / Neon endpoints

All writes use JWT sessions and organization-scoped authorization in persistent mode.
The synthetic demo routes are deliberately key-free and do not create real commitments.

| Method and path | Purpose |
|---|---|
| `POST /api/auth/login` | Create a signed, HTTP-only session from email/password |
| `POST /api/auth/logout` | Clear the session |
| `GET /api/auth/me` | Return the authenticated user |
| `GET /api/atlas/state` | Organization-scoped ATLAS situation, proposal, messages, approvals, and audit timeline |
| `POST /api/atlas/triggers` | Persist an authorized weather/FEMA/shortage/inventory/vendor/proposal trigger and start an orchestrator run |
| `POST /api/atlas/demo` | Reset the non-persistent synthetic scenario |
| `POST /api/atlas/approvals/{approvalId}` | Record `approved` or `rejected`; only the required organization's human role may decide |
| `POST /api/vision/analyze` | Run still-image package detection and product classification; never changes inventory |

`POST /api/vision/analyze` accepts multipart form fields `image` and optional
`synthetic=true`. It returns image dimensions, YOLO model/version, bounding boxes,
per-object confidence, visible-object count, classification source, and uncertainty.
Submitting the later operator-confirmation step creates a **pending** immutable inventory
transaction; only a separate site reviewer may approve it.

## Spreadsheet bridge

### POST /spreadsheets/import
Multipart upload, field name `file`, accepts `.xlsx` or `.csv`. Flexible headers
(case-insensitive): `site`/`location`/`pantry`, `category`/`type`,
`count`/`qty`/`quantity`, optional `county`, `lat`, `lon`. Unknown sites are created.
Response:
```json
{"imported_rows": 8, "created_sites": ["Fremont Family Pantry"],
 "skipped": [{"row": 4, "reason": "need site, a known category, and a count"}],
 "export_url": "/spreadsheets/export"}
```

### GET /spreadsheets/export
Downloads `relieflink-live.xlsx`, regenerated from the live ledger on every request
(sheets: README, Inventory, Forecasts, Gaps, Upload). Same URL, always current: this is
the "connected spreadsheet" partners keep.

### GET /spreadsheets/template
A blank starter sheet with the right headers and example rows.

## Frontend + static (same server)

| Path | Serves |
|---|---|
| `/` | React CRM dashboard (`web/index.html`) |
| `/camera` | in-browser edge YOLO page (`web/camera.html`) |
| `/static/...` | `web/` assets |
| `/models/yolov8n.onnx` | YOLO weights for the camera page |
| `/api` | machine-readable service info (name, docs URL, categories) |
