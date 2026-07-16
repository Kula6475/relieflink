# Reallocation Agent (Phase 2)

**Owners: everyone, built together after Phase 1 lands.**

The payoff of the whole system: a LangGraph pipeline fetches ledger inputs, runs the
OR-Tools optimizer, posts transfers, and explains the plan in plain language via Claude.
Without an API key (and always under `--dry-run`) it uses a deterministic explanation.

## Prerequisites (from Phase 1)

- Ledger `GET /gaps` endpoint (Vivaan + Akul)
- Real or fake inventory flowing from the vision agent (Nehal)
- Forecasts flowing from the disruption agent (Pranav)

## Run the connected agent

With the seeded ledger running, first populate inventory and forecasts, then build and
post transfer recommendations:

```bash
python -m vision_agent.agent --site-id 1 --fake
python -m disruption_agent.agent --synthetic
python -m reallocation_agent.agent --dry-run  # inspect without posting
python -m reallocation_agent.agent            # post to /recommendations
python -m reallocation_agent.agent --why "Why move canned goods from site 1?"
```

The standalone toy example is still available with `--demo`.

## Phase 2 status

1. [x] Pull `/gaps`, `/routes`, `/capacity` from the ledger.
2. [x] Run `solve_transfers()` per category with truck-capacity constraints.
3. [x] POST results to `/recommendations`.
4. [x] Claude explanation and follow-up `--why` Q&A, with a no-key fallback.
5. [ ] Dashboard approve button dispatches it (Vivaan + Akul).

The numbered TODO list in `agent.py` mirrors this.
