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

MAP_STYLE = "carto-darkmatter"
RISK_COLORS = ["#2ecc71", "#f1c40f", "#e74c3c"]
CATEGORY_COLORS = {
    "dry goods": "#3498db",
    "dairy": "#9b59b6",
    "produce": "#2ecc71",
    "canned goods": "#e74c3c",
}


def pretty(category: str) -> str:
    """Display-only label, e.g. 'dry_goods' -> 'dry goods'. Never used for API calls."""
    return category.replace("_", " ")


@st.cache_data(ttl=20)
def fetch(path: str) -> list[dict]:
    return requests.get(f"{LEDGER_URL}{path}", timeout=10).json()


with st.sidebar:
    st.header("Controls")
    if st.button("Refresh now", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    refresh_label = st.selectbox("Auto-refresh", ["Off", "10s", "20s", "60s"], index=2)
    REFRESH_SECONDS = {"Off": None, "10s": 10, "20s": 20, "60s": 60}[refresh_label]


@st.fragment(run_every=REFRESH_SECONDS)
def render_dashboard():
    st.title("ReliefLink Operations")

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
    inventory = fetch("/inventory")
    forecasts = fetch("/forecasts")
    recommendations = fetch("/recommendations")

    total_items = sum(row["count"] for row in inventory) if inventory else 0
    at_risk = len({row["site_id"] for row in forecasts if row["multiplier"] > 1.5}) if forecasts else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Sites", len(sites))
    m2.metric("Items tracked", f"{total_items:,}")
    m3.metric("Sites at risk", at_risk)
    m4.metric("Pending transfers", len(recommendations) if recommendations else 0)

    inventory_tab, forecast_tab, realloc_tab = st.tabs(
        ["Inventory", "Alerts & Forecasts", "Reallocation (Phase 2)"]
    )

    with inventory_tab:
        map_col, chart_col = st.columns([1, 2])

        with map_col:
            st.subheader("Sites")
            site_map_df = pd.DataFrame(sites)
            site_fig = px.scatter_map(
                site_map_df, lat="lat", lon="lon", hover_name="name", zoom=6, height=350
            )
            site_fig.update_traces(marker=dict(size=14, color="#3498db"))
            site_fig.update_layout(map_style=MAP_STYLE, margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(site_fig, width="stretch")

        with chart_col:
            st.subheader("Current inventory (latest camera count per category)")
            if inventory:
                df = pd.DataFrame(inventory)
                df["site"] = df["site_id"].map(site_names)
                df["category"] = df["category"].map(pretty)
                fig = px.bar(
                    df,
                    x="site",
                    y="count",
                    color="category",
                    color_discrete_map=CATEGORY_COLORS,
                    barmode="group",
                    labels={"count": "items", "site": ""},
                )
                fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig, width="stretch")

                display_df = df[["site", "category", "count", "confidence", "source", "created_at"]].copy()
                display_df["confidence"] = (display_df["confidence"] * 100).round(0).astype(int).astype(str) + "%"
                display_df["created_at"] = pd.to_datetime(display_df["created_at"]).dt.strftime("%b %d, %I:%M %p")
                st.dataframe(display_df, width="stretch", hide_index=True)
            else:
                st.info("No inventory yet. Run: python -m vision_agent.agent --site-id 1 --fake")

    with forecast_tab:
        st.subheader("Site risk map")
        site_df = pd.DataFrame(sites)[["id", "name", "lat", "lon"]].rename(columns={"id": "site_id"})
        if forecasts:
            fdf_all = pd.DataFrame(forecasts)
            worst = fdf_all.groupby("site_id")["multiplier"].max().reset_index()
            site_risk = site_df.merge(worst, on="site_id", how="left")
        else:
            site_risk = site_df.copy()
            site_risk["multiplier"] = None
        site_risk["multiplier"] = site_risk["multiplier"].fillna(1.0)

        risk_fig = px.scatter_map(
            site_risk,
            lat="lat",
            lon="lon",
            color="multiplier",
            color_continuous_scale=RISK_COLORS,
            range_color=[1.0, 3.0],
            hover_name="name",
            zoom=6,
            height=350,
        )
        risk_fig.update_traces(marker=dict(size=16))
        risk_fig.update_layout(map_style=MAP_STYLE, margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(risk_fig, width="stretch")

        st.subheader("Predicted demand (next 48h)")
        if forecasts:
            fdf = pd.DataFrame(forecasts)
            fdf["site"] = fdf["site_id"].map(site_names)
            fdf["category"] = fdf["category"].map(pretty)
            spiking = fdf[fdf["multiplier"] > 1.0]
            if not spiking.empty:
                for site in spiking["site"].unique():
                    reason = spiking[spiking["site"] == site].iloc[0]["reason"]
                    st.warning(f"**{site}** demand spike: {reason}")
            st.dataframe(
                fdf[["site", "category", "predicted_demand", "multiplier", "reason", "source"]],
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("No forecasts yet. Run: python -m disruption_agent.agent --synthetic")

    with realloc_tab:
        st.subheader("Supply gaps")
        gaps = fetch("/gaps")
        if gaps:
            gdf = pd.DataFrame(gaps)
            gdf["site"] = gdf["site_id"].map(site_names)
            gdf["category"] = gdf["category"].map(pretty)
            shortages = gdf[gdf["gap"] > 0].sort_values("gap", ascending=False)
            surpluses = gdf[gdf["gap"] < 0].sort_values("gap")

            gap_col1, gap_col2 = st.columns(2)
            with gap_col1:
                st.caption("Shortages (need more)")
                if not shortages.empty:
                    st.dataframe(
                        shortages[["site", "category", "current", "predicted_demand", "gap"]],
                        width="stretch",
                        hide_index=True,
                    )
                else:
                    st.success("No shortages right now.")
            with gap_col2:
                st.caption("Surpluses (have extra)")
                if not surpluses.empty:
                    st.dataframe(
                        surpluses[["site", "category", "current", "predicted_demand", "gap"]],
                        width="stretch",
                        hide_index=True,
                    )
                else:
                    st.info("No surpluses right now.")
        else:
            st.info("No gap data yet.")

        st.divider()
        st.subheader("Recommended transfers")
        if recommendations:
            for rec in recommendations:
                from_name = site_names.get(rec["from_site_id"], rec["from_site_id"])
                to_name = site_names.get(rec["to_site_id"], rec["to_site_id"])
                label = (
                    f"**{rec['quantity']} {pretty(rec['category'])}**: "
                    f"{from_name} -> {to_name} — {rec['reason']} "
                    f"[{rec['status']}]"
                )
                row_col, btn_col = st.columns([4, 1])
                row_col.markdown(label)
                if rec["status"] not in ("approved", "rejected"):
                    if btn_col.button("Approve", key=f"approve-{rec['id']}"):
                        requests.post(f"{LEDGER_URL}/recommendations/{rec['id']}/approve", timeout=10)
                        st.cache_data.clear()
                        st.rerun()
                else:
                    btn_col.write(rec["status"])
        else:
            st.info("No recommendations yet. Phase 2's reallocation agent will post transfer suggestions here.")

    st.caption(f"Ledger: {LEDGER_URL} | auto-refresh: {refresh_label}")


render_dashboard()