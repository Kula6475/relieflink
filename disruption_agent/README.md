# Disruption Agent (weather + FEMA -> demand forecasts)

**Owner: Pranav**

Pulls live weather alerts from api.weather.gov and disaster declarations from OpenFEMA,
turns them into a demand-spike multiplier per site, and posts predicted demand per
(site, category) to the ledger for the next 48 hours.

## Run it

```bash
# from the repo root, with the ledger running and seeded

# Demo mode: fabricates a severe storm over every site (works on a sunny day)
python -m disruption_agent.agent --synthetic

# Live mode: real NWS alerts at each site's lat/lon, no API key needed
python -m disruption_agent.agent
```

Then `curl http://localhost:8000/forecasts` or check the dashboard's forecast tab.

## Files you own

- `agent.py` - fetchers, the multiplier logic, and forecast posting.

## Your tasks

- [ ] Run `--synthetic` end to end and confirm forecasts land in the ledger.
- [ ] Run live mode and inspect what api.weather.gov actually returns for each site
      (severity, event, onset/expires). Log or print the raw alerts once.
- [ ] **Fold FEMA into the multiplier**: `fetch_fema_declarations()` already works but
      is unused. Match declarations to sites by county (`designatedArea` field) and
      bump the multiplier for sites in a declared-disaster county.
- [ ] **Per-category multipliers**: a storm spikes canned/dry goods harder than dairy
      (people stock shelf-stable food). Replace the single multiplier with a
      per-category one.
- [ ] **Time-aware demand**: use alert `onset`/`expires` to scale the horizon instead
      of the flat 48h.
- [ ] Stretch: replace `BASELINE_DAILY_DEMAND` with a per-site synthetic historical
      curve (e.g. a CSV of 90 days of daily demand) and fit a simple regression or
      Prophet model so "predicted demand" is a real forecast, not baseline x multiplier.
- [ ] Stretch: schedule it (cron or a `--loop` flag) so forecasts refresh hourly.

## Definition of done

Running the agent against live APIs produces sensible, explainable forecasts for all
4 sites (each forecast row carries a human-readable `reason`), and a synthetic run
visibly raises predicted demand at affected sites on the dashboard.

## API notes

- api.weather.gov needs a descriptive `User-Agent` header (already set in `HEADERS`).
- OpenFEMA needs no key: https://www.fema.gov/about/openfema/data-sets
- Alert severities: Extreme > Severe > Moderate > Minor > Unknown.
