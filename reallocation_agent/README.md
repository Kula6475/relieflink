# Reallocation Agent

**Owners: everyone** | Status: **working end to end**

Given camera-fed inventory and disaster-driven forecasts, proposes the minimum-cost set
of transfers between sites and posts them as recommendations for one-click approval on
the dashboard's Transfers tab.

## Run it

```bash
# needs gaps to exist: inventory (camera/fake) + forecasts (disruption agent) first
python -m reallocation_agent.agent            # solve and post recommendations
python -m reallocation_agent.agent --dry-run  # solve and print only
```

## How it works

1. Pulls `/gaps` (surplus and shortage per site + category), `/routes` (miles), and
   `/capacity` (trucks x max load per site) from the ledger.
2. Solves one linear program across all categories (OR-Tools GLOP):
   minimize miles driven minus a large per-unit delivery reward, subject to per-category
   surplus/shortage limits and each site's **total** outbound truck capacity.
3. POSTs each chosen transfer to `/recommendations` with a plain-language reason.
4. If `ANTHROPIC_API_KEY` is set, Claude adds a 3-sentence justification of the overall
   plan for the ops director (skipped silently otherwise).

## Remaining ideas

- [ ] Multi-hop routing (via a depot) instead of direct lanes only
- [ ] Respect `drive_minutes` with a delivery deadline per shortage
- [ ] Post Claude's plan summary somewhere visible on the dashboard
