# Disruption Agent (weather + FEMA -> demand forecasts)

**Owner: Pranav** | Status: **core tasks complete**

Pulls live weather alerts from api.weather.gov and disaster declarations from OpenFEMA,
turns them into a per-category demand multiplier per site, and posts predicted demand
per (site, category) to the ledger for the next 48 hours.

The runtime is a LangGraph pipeline: `fetch -> score -> claude_reason -> forecast -> post`.
Claude condenses the alert evidence into each forecast's `reason`; when no Anthropic key
is configured, and always in `--synthetic`, the graph uses the deterministic reason.

## Run it

```bash
# from the repo root, with the ledger running and seeded

# Demo mode: fabricates a severe storm over every site + a FEMA declaration
# for Santa Cruz County (works on a sunny day)
python -m disruption_agent.agent --synthetic

# Live mode: real NWS alerts at each site's lat/lon + real OpenFEMA data, no key needed
python -m disruption_agent.agent

# Inspect the raw alert fields NWS returns
python -m disruption_agent.agent --verbose

# Keep forecasts fresh (refresh every hour)
python -m disruption_agent.agent --loop 3600
```

Then `curl http://localhost:8000/forecasts` or check the dashboard's forecast tab.

## How a forecast is computed

For each (site, category):

1. **Baseline** comes from a fitted demand model (`demand_model.py`): 90 days of
   deterministic synthetic history per site/category, fitted with a linear trend plus
   weekday profile, projected over the horizon. Swap `generate_history()` for real CSV
   logs and nothing else changes.
2. **Spike** from the worst active NWS alert: Extreme 3.0, Severe 2.0, Moderate 1.5,
   Minor 1.2.
3. **Coverage**: the fraction of the next 48h the alert is actually active, computed
   from its `onset`/`ends` timestamps. A storm that ends in 6 hours barely moves the
   forecast; one covering the whole window moves it fully.
4. **Category sensitivity**: shelf-stable food spikes hardest ahead of a disruption
   (canned 1.0, dry 0.9, produce 0.5, dairy 0.4).
5. **FEMA bump**: if the site's county has a declaration in the last 60 days
   (matched via OpenFEMA `designatedArea`), the multiplier gets a further x1.5.
6. Final multiplier is capped at 4.0. `predicted_demand = ceil(baseline * multiplier)`,
   and every forecast row carries a human-readable `reason`.

## Files

- `agent.py` - fetchers, scoring (coverage, severity, FEMA), posting, CLI.
- `demand_model.py` - synthetic history generation + trend/weekday regression.
- `tests/test_disruption.py` - unit tests for all the scoring logic (no network).

## Task list

- [x] Synthetic and live runs end to end
- [x] Inspect raw NWS alerts (`--verbose`)
- [x] Fold FEMA declarations into the multiplier (county match on `designatedArea`)
- [x] Per-category multipliers (shelf-stable spikes hardest)
- [x] Time-aware demand from alert `onset`/`ends` (coverage fraction)
- [x] Regression baseline over 90-day history instead of a flat constant
- [x] Refresh loop (`--loop N`)

Ideas if there is time left:
- [ ] Replace synthetic history with real distribution CSVs per site
- [ ] Prophet (or statsmodels) instead of the hand-rolled trend + weekday fit
- [ ] Match alerts by NWS zone/polygon instead of a point lookup
- [ ] Incident-type-specific sensitivities (fire vs flood vs storm)

## API notes

- api.weather.gov needs a descriptive `User-Agent` header (already set in `HEADERS`).
- OpenFEMA needs no key: https://www.fema.gov/about/openfema/data-sets
- Alert severities: Extreme > Severe > Moderate > Minor > Unknown.
