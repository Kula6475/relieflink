# Reallocation Agent

**Owners: everyone** | Status: **working end to end**

A LangGraph pipeline fetches ledger inputs, solves one cross-category OR-Tools program,
posts recommendations, and explains the plan in plain language with Claude. The solver
limits each site's total outbound units across categories to its truck capacity.

## Run it

```bash
python -m reallocation_agent.agent --dry-run
python -m reallocation_agent.agent
python -m reallocation_agent.agent --why "Why move canned goods from site 1?"
```

The graph is `fetch -> solve -> post -> claude`. `--dry-run` never posts or calls Claude;
without an API key, normal runs post recommendations and use a deterministic explanation.

## Remaining ideas

- [ ] Multi-hop routing (via a depot) instead of direct lanes only
- [ ] Respect `drive_minutes` with a delivery deadline per shortage
- [ ] Post Claude's plan summary somewhere visible on the dashboard
