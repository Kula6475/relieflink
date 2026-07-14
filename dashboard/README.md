# Dashboard (live ops view)

**Owners: Vivaan + Akul** (you two also own [`ledger/`](../ledger/))

The Streamlit app an ops director watches: camera-fed inventory per site, active
alerts and demand forecasts on a map, and (Phase 2) recommended transfers with a
one-click approve.

## Run it

```bash
# from the repo root, with the ledger running and seeded
streamlit run dashboard/app.py
```

It opens in your browser and hot-reloads every time you save `app.py`.
To see data move: run the fake agents in another terminal
(`python -m vision_agent.agent --site-id 3 --fake`, then hit R to rerun).

## Files you own

- `app.py` - the whole dashboard.

## Your tasks

- [ ] Run it, click through all three tabs, and read `app.py` top to bottom.
- [ ] **Risk map**: on the forecast tab, plot sites colored by their demand multiplier
      (green 1.0 -> red 3.0). `px.scatter_map` with `color` works well.
- [ ] **Shortage highlighting**: once the ledger's `GET /gaps` endpoint exists (your
      other task list), add a "Gaps" view that shows shortage sites in red and surplus
      sites in green per category.
- [ ] **Approve button**: on the reallocation tab, one button per recommendation row
      that calls `POST /recommendations/{id}/approve` and reruns. (`st.button` inside
      a loop with `key=rec['id']`.)
- [ ] **Auto-refresh**: add `st.sidebar` controls for refresh interval, or use
      `st.rerun` on a timer so the demo updates hands-free.
- [ ] Stretch: inventory trend line per site/category (needs the history endpoint
      from the ledger stretch task).

## Definition of done

During a demo: fake counts posted from another terminal appear within one refresh,
a synthetic storm turns the affected sites red on the map, and (Phase 2) clicking
Approve flips a recommendation's status live.

## Tips

- Streamlit reruns the whole script on every interaction, that is normal.
- `st.cache_data(ttl=20)` is why data can lag up to 20s, lower it while developing.
- Ask Claude/Cursor: "read dashboard/app.py and add a scatter map colored by
  forecast multiplier on the forecast tab".
