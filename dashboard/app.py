"""ReliefLink operations dashboard (Streamlit).

Owners: Vivaan + Akul. Your task checklist is in dashboard/README.md.

Run from the repo root (with the ledger API running):
    streamlit run dashboard/app.py
"""

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

from shared.config import LEDGER_URL

st.set_page_config(page_title="ReliefLink", page_icon="📦", layout="wide")
st.title("ReliefLink Operations")


@st.cache_data(ttl=20)
def fetch(path: str) -> list[dict]:
    return requests.get(f"{LEDGER_URL}{path}", timeout=10).json()


try:
    sites = fetch("/sites")
except requests.ConnectionError:
    st.error(
        f"Cannot reach the ledger at {LEDGER_URL}. "
        "Start it first: `uvicorn ledger.main:app --reload`"
    )
    st.stop()

if not sites:
    st.warning("No sites yet. Seed the database: `python -m ledger.seed`")
    st.stop()

site_names = {site["id"]: site["name"] for site in sites}

inventory_tab, forecast_tab, realloc_tab = st.tabs(
    ["Inventory", "Alerts & Forecasts", "Reallocation (Phase 2)"]
)

with inventory_tab:
    map_col, chart_col = st.columns([1, 2])

    with map_col:
        st.subheader("Sites")
        st.map(pd.DataFrame(sites)[["lat", "lon"]], size=800)

    with chart_col:
        st.subheader("Current inventory (latest camera count per category)")
        inventory = fetch("/inventory")
        if inventory:
            df = pd.DataFrame(inventory)
            df["site"] = df["site_id"].map(site_names)
            fig = px.bar(
                df,
                x="site",
                y="count",
                color="category",
                barmode="group",
                labels={"count": "items", "site": ""},
            )
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(
                df[["site", "category", "count", "confidence", "source", "created_at"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No inventory yet. Run: python -m vision_agent.agent --site-id 1 --fake")

with forecast_tab:
    st.subheader("Predicted demand (next 48h)")
    forecasts = fetch("/forecasts")
    if forecasts:
        fdf = pd.DataFrame(forecasts)
        fdf["site"] = fdf["site_id"].map(site_names)
        spiking = fdf[fdf["multiplier"] > 1.0]
        if not spiking.empty:
            for site in spiking["site"].unique():
                reason = spiking[spiking["site"] == site].iloc[0]["reason"]
                st.warning(f"**{site}** demand spike: {reason}")
        st.dataframe(
            fdf[["site", "category", "predicted_demand", "multiplier", "reason", "source"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No forecasts yet. Run: python -m disruption_agent.agent --synthetic")

    # TODO(Vivaan/Akul): draw the sites on a map colored by multiplier (green=1.0,
    # red=3.0) so an ops director sees at a glance which sites are at risk.

with realloc_tab:
    st.subheader("Recommended transfers")
    recommendations = fetch("/recommendations")
    if recommendations:
        rdf = pd.DataFrame(recommendations)
        rdf["from"] = rdf["from_site_id"].map(site_names)
        rdf["to"] = rdf["to_site_id"].map(site_names)
        st.dataframe(
            rdf[["from", "to", "category", "quantity", "reason", "status"]],
            use_container_width=True,
            hide_index=True,
        )
        # TODO(Vivaan/Akul): add an "Approve" button per row that calls
        # POST /recommendations/{id}/approve (build that endpoint in the ledger first).
    else:
        st.info("Phase 2: the reallocation agent will post transfer recommendations here.")

st.caption(f"Ledger: {LEDGER_URL} | data refreshes every 20s (st.cache_data ttl)")
