"""ReliefLink disruption agent: weather alerts + FEMA declarations -> demand forecasts.

Owner: Pranav. Task checklist: disruption_agent/README.md.

Modes:
    python -m disruption_agent.agent --synthetic      # fake storm + FEMA declaration
    python -m disruption_agent.agent                  # live NWS + OpenFEMA data
    python -m disruption_agent.agent --verbose        # also dump raw alert fields
    python -m disruption_agent.agent --loop 3600      # refresh every hour

How each (site, category) forecast is computed:

    baseline    = fitted demand model over 90 days of history
                  (linear trend + weekday profile, see demand_model.py)
    spike       = NWS severity factor (Extreme 3.0, Severe 2.0, Moderate 1.5, Minor 1.2)
    coverage    = fraction of the next 48h the alert is actually active
                  (from the alert's onset/ends timestamps)
    sensitivity = per-category storm sensitivity (shelf-stable food spikes hardest)

    multiplier  = 1 + (spike - 1) * coverage * sensitivity
                  x1.5 if the site's county has a FEMA declaration in the last 60 days,
                  capped at 4.0

    predicted_demand = ceil(baseline * multiplier)
"""

import argparse
import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from typing import TypedDict

import requests
from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, START, StateGraph

from disruption_agent.demand_model import baseline_demand
from shared.config import CATEGORIES, CLAUDE_MODEL, LEDGER_URL

WEATHER_API = "https://api.weather.gov/alerts/active"
FEMA_API = "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"

# api.weather.gov requires a descriptive User-Agent or it may block requests.
HEADERS = {"User-Agent": "ReliefLink hackathon project (github.com/PranavAchar01/relieflink)"}

SEVERITY_SPIKE = {"Extreme": 3.0, "Severe": 2.0, "Moderate": 1.5, "Minor": 1.2}

# How hard a disruption hits each category: people stock shelf-stable food ahead of
# a storm; perishables spike less because fridges may lose power anyway.
CATEGORY_SENSITIVITY = {"canned_goods": 1.0, "dry_goods": 0.9, "produce": 0.5, "dairy": 0.4}

FEMA_MULTIPLIER = 1.5
FEMA_LOOKBACK_DAYS = 60
MAX_MULTIPLIER = 4.0
HORIZON_HOURS = 48


class DisruptionState(TypedDict, total=False):
    """Data passed between nodes in the disruption graph."""

    synthetic: bool
    verbose: bool
    now: datetime
    sites: list[dict]
    declarations: list[dict]
    alerts_by_site: dict[int, list[dict]]
    scored_sites: list[dict]
    reasons: dict[int, str]
    forecasts: list[dict]
    posted_count: int


# ---------------------------------------------------------------- fetchers


def fetch_weather_alerts(lat: float, lon: float) -> list[dict]:
    """Active NWS alerts covering a point. Returns a list of alert properties."""
    response = requests.get(
        WEATHER_API, params={"point": f"{lat},{lon}"}, headers=HEADERS, timeout=15
    )
    response.raise_for_status()
    return [feature["properties"] for feature in response.json().get("features", [])]


def fetch_fema_declarations(state: str = "CA", top: int = 25) -> list[dict]:
    """Most recent FEMA disaster declarations for a state (OpenFEMA, no key needed)."""
    response = requests.get(
        FEMA_API,
        params={
            "$filter": f"state eq '{state}'",
            "$orderby": "declarationDate desc",
            "$top": top,
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("DisasterDeclarationsSummaries", [])


# ---------------------------------------------------------------- scoring


def parse_when(value: str | None) -> datetime | None:
    """ISO timestamp -> aware datetime, or None if missing/unparseable."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def alert_coverage(alert: dict, now: datetime, horizon_hours: int = HORIZON_HOURS) -> float:
    """Fraction of [now, now + horizon] that this alert is active for (0..1).

    Missing onset means "already active"; missing end means "assume the whole window".
    """
    window_end = now + timedelta(hours=horizon_hours)
    onset = parse_when(alert.get("onset") or alert.get("effective")) or now
    ends = parse_when(alert.get("ends") or alert.get("expires")) or window_end
    overlap = (min(ends, window_end) - max(onset, now)).total_seconds()
    return max(0.0, min(1.0, overlap / (horizon_hours * 3600)))


def worst_alert(alerts: list[dict], now: datetime) -> tuple[float, float, str]:
    """Pick the alert with the biggest time-weighted impact.

    Returns (spike, coverage, human-readable reason).
    """
    spike, coverage, reason = 1.0, 0.0, "no active alerts"
    best_effective = 1.0
    for alert in alerts:
        alert_spike = SEVERITY_SPIKE.get(alert.get("severity", ""), 1.0)
        cover = alert_coverage(alert, now)
        effective = 1 + (alert_spike - 1) * cover
        if effective > best_effective:
            best_effective = effective
            spike, coverage = alert_spike, cover
            reason = (
                f"{alert.get('event', 'Alert')} ({alert.get('severity')}), "
                f"covers {cover:.0%} of the next {HORIZON_HOURS}h"
            )
    return spike, coverage, reason


def active_fema_counties(declarations: list[dict], now: datetime) -> set[str]:
    """Lowercased county names with a declaration in the last FEMA_LOOKBACK_DAYS."""
    cutoff = now - timedelta(days=FEMA_LOOKBACK_DAYS)
    counties = set()
    for declaration in declarations:
        declared = parse_when(declaration.get("declarationDate"))
        if declared and declared >= cutoff:
            area = declaration.get("designatedArea", "")
            counties.add(area.replace("(County)", "").strip().lower())
    return counties


def category_multiplier(spike: float, coverage: float, category: str, fema_active: bool) -> float:
    multiplier = 1 + (spike - 1) * coverage * CATEGORY_SENSITIVITY[category]
    if fema_active:
        multiplier *= FEMA_MULTIPLIER
    return round(min(multiplier, MAX_MULTIPLIER), 2)


# ---------------------------------------------------------------- synthetic demo data


# Real disasters are localized: the synthetic storm only hits this county, so other
# sites keep surplus and the reallocation agent has somewhere to pull from.
SYNTHETIC_STORM_COUNTIES = {"Santa Cruz"}


def synthetic_alerts(site: dict, now: datetime) -> list[dict]:
    """A fake severe storm (started 2h ago, ends in 36h) over SYNTHETIC_STORM_COUNTIES."""
    if site["county"] not in SYNTHETIC_STORM_COUNTIES:
        return []
    return [
        {
            "event": "Winter Storm Warning",
            "severity": "Severe",
            "headline": f"Synthetic severe storm covering {site['county']} County",
            "onset": (now - timedelta(hours=2)).isoformat(),
            "ends": (now + timedelta(hours=36)).isoformat(),
        }
    ]


def synthetic_declarations(now: datetime) -> list[dict]:
    """A fake FEMA declaration for Santa Cruz so the county bump is demoable too."""
    return [
        {
            "designatedArea": "Santa Cruz (County)",
            "declarationDate": now.isoformat(),
            "declarationTitle": "Synthetic Severe Storm (DR-0000)",
        }
    ]


# ---------------------------------------------------------------- main loop


def post_forecast(
    site_id: int, category: str, predicted: int, multiplier: float, reason: str, source: str
) -> None:
    response = requests.post(
        f"{LEDGER_URL}/forecasts",
        json={
            "site_id": site_id,
            "category": category,
            "predicted_demand": predicted,
            "multiplier": multiplier,
            "horizon_hours": HORIZON_HOURS,
            "reason": reason,
            "source": source,
        },
        timeout=10,
    )
    response.raise_for_status()


def fetch_node(state: DisruptionState) -> dict:
    """Fetch sites, weather alerts, and FEMA declarations."""
    now = datetime.now(timezone.utc)
    response = requests.get(f"{LEDGER_URL}/sites", timeout=10)
    response.raise_for_status()
    sites = response.json()
    if not sites:
        raise SystemExit("No sites in the ledger. Run: python -m ledger.seed")

    synthetic = state.get("synthetic", False)
    declarations = synthetic_declarations(now) if synthetic else fetch_fema_declarations()
    alerts_by_site = {
        site["id"]: (
            synthetic_alerts(site, now)
            if synthetic
            else fetch_weather_alerts(site["lat"], site["lon"])
        )
        for site in sites
    }

    if state.get("verbose"):
        for site in sites:
            for alert in alerts_by_site[site["id"]]:
                print(
                    f"  raw alert @ {site['name']}: event={alert.get('event')!r} "
                    f"severity={alert.get('severity')!r} onset={alert.get('onset')} "
                    f"ends={alert.get('ends') or alert.get('expires')}"
                )
    return {
        "now": now,
        "sites": sites,
        "declarations": declarations,
        "alerts_by_site": alerts_by_site,
    }


def score_node(state: DisruptionState) -> dict:
    """Score time-weighted alert impact and FEMA coverage for each site."""
    now = state["now"]
    declarations = state["declarations"]
    fema_counties = active_fema_counties(declarations, now)
    scored_sites = []
    for site in state["sites"]:
        alerts = state["alerts_by_site"][site["id"]]
        spike, coverage, reason = worst_alert(alerts, now)
        fema_active = site["county"].lower() in fema_counties
        if fema_active:
            reason += f"; FEMA declaration active for {site['county']} County (x{FEMA_MULTIPLIER})"
        scored_sites.append(
            {
                "site": site,
                "alerts": alerts,
                "spike": spike,
                "coverage": coverage,
                "fema_active": fema_active,
                "fallback_reason": reason,
            }
        )
    return {"scored_sites": scored_sites}


def _message_text(message) -> str:
    if isinstance(message.content, str):
        return message.content
    return "\n".join(
        block.get("text", "")
        for block in message.content
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()


def claude_reason_node(state: DisruptionState) -> dict:
    """Summarize active alert evidence into a short forecast reason per site."""
    # Synthetic mode is guaranteed to remain a key-free demo path.
    use_claude = bool(os.getenv("ANTHROPIC_API_KEY")) and not state.get("synthetic")
    model = ChatAnthropic(model=CLAUDE_MODEL) if use_claude else None
    reasons = {}
    for scored in state["scored_sites"]:
        site = scored["site"]
        fallback = scored["fallback_reason"]
        if model is None:
            reasons[site["id"]] = fallback
            continue
        evidence = {
            "site": {"name": site["name"], "county": site["county"]},
            "alerts": [
                {
                    key: alert.get(key)
                    for key in ("event", "severity", "headline", "onset", "ends", "expires")
                }
                for alert in scored["alerts"]
            ],
            "coverage": scored["coverage"],
            "fema_active": scored["fema_active"],
        }
        prompt = (
            "Summarize this disaster evidence as one concise reason for a 48-hour "
            "food-bank demand forecast. State the alert and severity, timing/coverage, "
            "and FEMA status when relevant. Do not invent facts or give instructions. "
            "Return only the reason text.\n\n" + json.dumps(evidence, default=str)
        )
        reasons[site["id"]] = _message_text(model.invoke(prompt)) or fallback
    return {"reasons": reasons}


def forecast_node(state: DisruptionState) -> dict:
    """Build one ledger forecast payload per site and inventory category."""
    source = "synthetic" if state.get("synthetic") else "weather.gov"
    forecasts = []
    for scored in state["scored_sites"]:
        site = scored["site"]
        for category in CATEGORIES:
            multiplier = category_multiplier(
                scored["spike"], scored["coverage"], category, scored["fema_active"]
            )
            baseline = baseline_demand(site["id"], category, HORIZON_HOURS)
            forecasts.append(
                {
                    "site_id": site["id"],
                    "category": category,
                    "predicted_demand": math.ceil(baseline * multiplier),
                    "multiplier": multiplier,
                    "horizon_hours": HORIZON_HOURS,
                    "reason": state["reasons"][site["id"]],
                    "source": source,
                }
            )
    return {"forecasts": forecasts}


def post_node(state: DisruptionState) -> dict:
    """Post all graph-produced forecasts through the ledger API."""
    for forecast in state["forecasts"]:
        post_forecast(
            forecast["site_id"],
            forecast["category"],
            forecast["predicted_demand"],
            forecast["multiplier"],
            forecast["reason"],
            forecast["source"],
        )
    return {"posted_count": len(state["forecasts"])}


def build_graph():
    graph = StateGraph(DisruptionState)
    graph.add_node("fetch", fetch_node)
    graph.add_node("score", score_node)
    graph.add_node("claude_reason", claude_reason_node)
    graph.add_node("forecast", forecast_node)
    graph.add_node("post", post_node)
    graph.add_edge(START, "fetch")
    graph.add_edge("fetch", "score")
    graph.add_edge("score", "claude_reason")
    graph.add_edge("claude_reason", "forecast")
    graph.add_edge("forecast", "post")
    graph.add_edge("post", END)
    return graph.compile()


DISRUPTION_GRAPH = build_graph()


def run(synthetic: bool = False, verbose: bool = False) -> None:
    """Invoke the fetch -> score -> reason -> forecast -> post LangGraph."""
    result = DISRUPTION_GRAPH.invoke({"synthetic": synthetic, "verbose": verbose})
    by_site = {site["id"]: site for site in result["sites"]}
    forecasts_by_site: dict[int, list[dict]] = {}
    for forecast in result["forecasts"]:
        forecasts_by_site.setdefault(forecast["site_id"], []).append(forecast)

    for site_id, forecasts in forecasts_by_site.items():
        multipliers = {row["category"]: row["multiplier"] for row in forecasts}
        print(
            f"{by_site[site_id]['name']}: {multipliers} "
            f"({result['reasons'][site_id]})"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="ReliefLink disruption agent")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="fabricate a severe storm + FEMA declaration instead of calling live APIs",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="print raw alert fields for inspection"
    )
    parser.add_argument("--loop", type=int, help="refresh every N seconds (e.g. 3600)")
    args = parser.parse_args()

    if args.loop:
        print(f"Refreshing forecasts every {args.loop}s, Ctrl-C to stop")
        while True:
            run(synthetic=args.synthetic, verbose=args.verbose)
            time.sleep(args.loop)
    else:
        run(synthetic=args.synthetic, verbose=args.verbose)


if __name__ == "__main__":
    main()
