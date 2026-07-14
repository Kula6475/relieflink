# ReliefLink API Contract

The interface between all four sections. Build against this and you never block each
other. Change it only after telling the team (it breaks everyone downstream).

Base URL: `http://localhost:8000` (override with `LEDGER_URL` in `.env`).
Interactive docs with try-it-out: `http://localhost:8000/docs`.

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

## To build (Vivaan + Akul, specs)

### GET /gaps
For each (site, category) that has both an inventory count and a forecast:
```json
[{"site_id": 3, "category": "canned_goods", "current": 60,
  "predicted_demand": 480, "gap": 420}]
```
`gap = predicted_demand - current`. Positive = shortage, negative = surplus.
Include rows for all sites/categories that have data; skip pairs with no forecast.

### POST /recommendations  (reallocation agent -> ledger)
```json
{"from_site_id": 1, "to_site_id": 3, "category": "canned_goods",
 "quantity": 150, "reason": "Site 3 shortfall of 420 under storm forecast"}
```
Validate both sites and the category. Stored with `status: "proposed"`.

### POST /recommendations/{id}/approve
No body. Sets `status` to `"approved"`. 404 if the id does not exist.
Returns the updated recommendation.
