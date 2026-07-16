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

DEMO_USERNAME = "admin"
DEMO_PASSWORD = "reliefLink2026"

# Small hardcoded product catalog for the Barcode demo tab. Not a real barcode
# database -- just enough to make the demo flow feel real.
DEMO_BARCODE_CATALOG = {
    "012345678905": ("Canned Beans (case)", "canned_goods"),
    "034567891236": ("Whole Milk (gallon)", "dairy"),
    "045678912367": ("Rice 20lb bag", "dry_goods"),
    "056789123478": ("Fresh Apples (case)", "produce"),
}


def require_login() -> bool:
    """Simple demo-only gate. Not real security -- credentials live in this file."""
    if st.session_state.get("authenticated"):
        return True

    st.caption("OPERATIONS DASHBOARD")
    st.title("📦 ReliefLink")
    st.write("Sign in to continue.")
    _, form_col, _ = st.columns([1, 1, 1])
    with form_col:
        with st.container(border=True):
            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Sign in", width="stretch")
            if submitted:
                if username == DEMO_USERNAME and password == DEMO_PASSWORD:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")
    return False


if not require_login():
    st.stop()

MAP_STYLE = "carto-darkmatter"
RISK_COLORS = ["#2ecc71", "#f1c40f", "#e74c3c"]
CATEGORY_COLORS = {
    "dry goods": "#4f8ff7",
    "dairy": "#9b6bf2",
    "produce": "#2ecc71",
    "canned goods": "#e74c3c",
}
CATEGORY_OPTIONS = ["dry_goods", "dairy", "produce", "canned_goods"]


def pretty(category: str) -> str:
    """Display-only label, e.g. 'dry_goods' -> 'dry goods'. Never used for API calls."""
    return category.replace("_", " ")


@st.cache_data(ttl=20)
def fetch(path: str) -> list[dict]:
    return requests.get(f"{LEDGER_URL}{path}", timeout=10).json()


def post_snapshot(site_id: int, category: str, count: int, confidence: float, source: str):
    payload = {
        "site_id": site_id,
        "category": category,
        "count": int(count),
        "confidence": confidence,
        "source": source,
    }
    return requests.post(f"{LEDGER_URL}/snapshots", json=payload, timeout=10)


with st.sidebar:
    st.header("Controls")
    if st.button("Refresh now", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    refresh_label = st.selectbox("Auto-refresh", ["Off", "10s", "20s", "60s"], index=2)
    REFRESH_SECONDS = {"Off": None, "10s": 10, "20s": 20, "60s": 60}[refresh_label]
    st.divider()
    if st.button("Log out", width="stretch"):
        st.session_state["authenticated"] = False
        st.rerun()


@st.fragment(run_every=REFRESH_SECONDS)
def render_dashboard():
    st.caption("OPERATIONS DASHBOARD")
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

    st.info(f"Live ledger data from {LEDGER_URL} · refreshing every {refresh_label.lower()}.")

    total_items = sum(row["count"] for row in inventory) if inventory else 0
    at_risk = len({row["site_id"] for row in forecasts if row["multiplier"] > 1.5}) if forecasts else 0

    with st.container(border=True):
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Sites", len(sites))
        m2.metric("Items tracked", f"{total_items:,}")
        m3.metric("Sites at risk", at_risk)
        m4.metric("Pending transfers", len(recommendations) if recommendations else 0)

    inventory_tab, add_tab, forecast_tab, realloc_tab = st.tabs(
        ["Inventory", "Add Inventory", "Alerts & Forecasts", "Reallocation (Phase 2)"]
    )

    with inventory_tab:
        with st.container(border=True):
            map_col, chart_col = st.columns([1, 2])

            with map_col:
                st.subheader("Sites")
                site_map_df = pd.DataFrame(sites)
                site_fig = px.scatter_map(
                    site_map_df, lat="lat", lon="lon", hover_name="name", zoom=6, height=350
                )
                site_fig.update_traces(marker=dict(size=14, color="#4f8ff7"))
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

    with add_tab:
        st.subheader("Add inventory")
        st.caption("Turn any existing workflow into a standardized ledger entry.")

        manual_tab, csv_tab, sheet_tab, photo_tab, barcode_tab = st.tabs(
            ["Manual entry", "Upload CSV", "Paper sheet photo", "Food photo", "Barcode"]
        )

        with manual_tab:
            with st.container(border=True):
                with st.form("manual_entry_form", clear_on_submit=True):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        site_choice = st.selectbox("Site", options=list(site_names.values()), key="manual_site")
                    with col2:
                        category_choice = st.selectbox(
                            "Category", CATEGORY_OPTIONS, format_func=pretty, key="manual_category"
                        )
                    with col3:
                        source = st.selectbox("Source", ["manual", "vision", "synthetic"], key="manual_source")
                    count = st.number_input("Quantity", min_value=0, step=1, key="manual_count")
                    confidence = st.slider("Confidence", 0.0, 1.0, 1.0, key="manual_confidence")
                    submitted = st.form_submit_button("Submit snapshot", width="stretch")

                if submitted:
                    site_id = next(sid for sid, name in site_names.items() if name == site_choice)
                    resp = post_snapshot(site_id, category_choice, count, confidence, source)
                    if resp.status_code in (200, 201):
                        st.success(f"Added {int(count)} {pretty(category_choice)} at {site_choice}.")
                        st.cache_data.clear()
                    else:
                        st.error(f"Failed to add snapshot: {resp.status_code} {resp.text}")

        with csv_tab:
            with st.container(border=True):
                st.write(
                    "CSV columns expected: **site, category, count** "
                    "(optional: confidence, source). "
                    "`site` must exactly match an existing site name."
                )
                uploaded = st.file_uploader("Upload CSV", type=["csv"], key="csv_upload")
                if uploaded is not None:
                    try:
                        csv_df = pd.read_csv(uploaded)
                    except Exception as exc:
                        st.error(f"Could not read that CSV: {exc}")
                        csv_df = None

                    if csv_df is not None:
                        missing = {"site", "category", "count"} - set(csv_df.columns)
                        if missing:
                            st.error(f"CSV is missing required column(s): {', '.join(missing)}")
                        else:
                            st.dataframe(csv_df, width="stretch", hide_index=True)
                            if st.button("Submit all rows", width="stretch"):
                                name_to_id = {name: sid for sid, name in site_names.items()}
                                ok, failed = 0, []
                                for _, row in csv_df.iterrows():
                                    site_id = name_to_id.get(str(row["site"]).strip())
                                    if site_id is None:
                                        failed.append(f"Unknown site: {row['site']}")
                                        continue
                                    resp = post_snapshot(
                                        site_id,
                                        str(row["category"]).strip(),
                                        int(row["count"]),
                                        float(row.get("confidence", 1.0)),
                                        str(row.get("source", "manual")),
                                    )
                                    if resp.status_code in (200, 201):
                                        ok += 1
                                    else:
                                        failed.append(f"{row['site']} / {row['category']}: {resp.status_code}")
                                st.cache_data.clear()
                                if ok:
                                    st.success(f"Added {ok} row(s) to the ledger.")
                                if failed:
                                    st.error("Some rows failed:\n" + "\n".join(failed))

        with sheet_tab:
            with st.container(border=True):
                st.warning(
                    "Not wired in this build. This tab is a placeholder for cloud "
                    "document extraction (photographing a paper count sheet and "
                    "parsing it automatically) -- it would post to the same "
                    "`/snapshots` endpoint as manual entry once built."
                )

        with photo_tab:
            with st.container(border=True):
                st.warning(
                    "Not wired in this build. This tab is a placeholder for AI shelf-photo "
                    "analysis -- uploading a photo of a shelf and having a vision model "
                    "estimate the count. The real version of this lives in `vision_agent/`; "
                    "run `python -m vision_agent.agent --site-id 1 --fake` from the terminal "
                    "to see a simulated version of that pipeline feed the ledger directly."
                )

        with barcode_tab:
            with st.container(border=True):
                st.caption(
                    "Demo catalog only -- not a real barcode lookup. Try: "
                    + ", ".join(DEMO_BARCODE_CATALOG.keys())
                )
                barcode = st.text_input("Scan or type a barcode", key="barcode_input")
                match = DEMO_BARCODE_CATALOG.get(barcode.strip())
                if barcode and not match:
                    st.info("Barcode not in the demo catalog -- fill in the category manually below.")

                with st.form("barcode_form", clear_on_submit=True):
                    if match:
                        st.write(f"**Matched product:** {match[0]}")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        bc_site_choice = st.selectbox("Site", options=list(site_names.values()), key="bc_site")
                    with col2:
                        default_index = CATEGORY_OPTIONS.index(match[1]) if match else 0
                        bc_category_choice = st.selectbox(
                            "Category", CATEGORY_OPTIONS, index=default_index, format_func=pretty, key="bc_category"
                        )
                    with col3:
                        bc_source = st.selectbox("Source", ["manual", "vision", "synthetic"], key="bc_source")
                    bc_count = st.number_input("Quantity", min_value=0, step=1, key="bc_count")
                    bc_submitted = st.form_submit_button("Submit snapshot", width="stretch")

                if bc_submitted:
                    bc_site_id = next(sid for sid, name in site_names.items() if name == bc_site_choice)
                    resp = post_snapshot(bc_site_id, bc_category_choice, bc_count, 1.0, bc_source)
                    if resp.status_code in (200, 201):
                        st.success(f"Added {int(bc_count)} {pretty(bc_category_choice)} at {bc_site_choice}.")
                        st.cache_data.clear()
                    else:
                        st.error(f"Failed to add snapshot: {resp.status_code} {resp.text}")

    with forecast_tab:
        with st.container(border=True):
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

        with st.container(border=True):
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
        with st.container(border=True):
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

        with st.container(border=True):
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