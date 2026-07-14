# Reallocation Agent (Phase 2)

**Owners: everyone, built together after Phase 1 lands.**

The payoff of the whole system: given camera-fed inventory and disaster-driven demand
forecasts, recommend the minimum-cost set of transfers between sites, and explain the
plan in plain language via Claude.

## Prerequisites (from Phase 1)

- Ledger `GET /gaps` endpoint (Vivaan + Akul)
- Real or fake inventory flowing from the vision agent (Nehal)
- Forecasts flowing from the disruption agent (Pranav)

## Try the solver today

The OR-Tools pattern already works on hardcoded data:

```bash
python -m reallocation_agent.agent
```

## Phase 2 plan

1. Pull `/gaps`, `/routes`, `/capacity` from the ledger.
2. Run `solve_transfers()` per category, add a truck-capacity constraint.
3. POST results to `/recommendations`.
4. `explain_with_claude()`: 3-sentence plain-language justification + "why" Q&A.
5. Dashboard approve button dispatches it (Vivaan + Akul).

The numbered TODO list in `agent.py` mirrors this.
