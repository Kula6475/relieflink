"""ReliefLink disruption agent: weather alerts + FEMA declarations -> demand forecasts.

Owner: Pranav. Your task checklist is in disruption_agent/README.md.

Quick start (no live disaster required):
    python -m disruption_agent.agent --synthetic

Real data (live NWS alerts for each site's location):
    python -m disruption_agent.agent
"""

import argparse
import math

import requests

from shared.config import CATEGORIES, LEDGER_URL

WEATHER_API = "https://api.weather.gov/alerts/active"
FEMA_API = "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"

# api.weather.gov requires a descriptive User-Agent or it may block requests.
HEADERS = {"User-Agent": "ReliefLink hackathon project (github.com/PranavAchar01/relieflink)"}

# How much demand spikes above baseline for each NWS alert severity.
SEVERITY_MULTIPLIER = {"Extreme": 3.0, "Severe": 2.0, "Moderate": 1.5, "Minor": 1.2}

# Normal daily demand per category at a typical site. Synthetic for the demo;
# replacing this with per-site historical curves is on the task list.
BASELINE_DAILY_DEMAND = {"canned_goods": 120, "produce": 80, "dairy": 60, "dry_goods": 100}

HORIZON_HOURS = 48


def fetch_weather_alerts(lat: float, lon: float) -> list[dict]:
    """Active NWS alerts covering a point. Returns a list of alert properties."""
    response = requests.get(
        WEATHER_API, params={"point": f"{lat},{lon}"}, headers=HEADERS, timeout=15
    )
    response.raise_for_status()
    return [feature["properties"] for feature in response.json().get("features", [])]


def fetch_fema_declarations(state: str = "CA", top: int = 10) -> list[dict]:
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


def demand_multiplier(alerts: list[dict]) -> tuple[float, str]:
    """Worst active alert wins. Returns (multiplier, human-readable reason)."""
    multiplier, reason = 1.0, "no active alerts"
    for alert in alerts:
        severity = alert.get("severity", "Unknown")
        candidate = SEVERITY_MULTIPLIER.get(severity, 1.0)
        if candidate > multiplier:
            multiplier = candidate
            reason = f"{alert.get('event', 'Alert')} ({severity}): {alert.get('headline', '')}"
    return multiplier, reason


def synthetic_alerts(site: dict) -> list[dict]:
    """A fake severe storm so the pipeline can be demoed on a sunny day."""
    return [
        {
            "event": "Winter Storm Warning",
            "severity": "Severe",
            "headline": f"Synthetic severe storm covering {site['county']} County",
        }
    ]


def post_forecast(site_id: int, category: str, multiplier: float, reason: str, source: str) -> None:
    predicted = math.ceil(BASELINE_DAILY_DEMAND[category] * multiplier * HORIZON_HOURS / 24)
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


def run(synthetic: bool = False) -> None:
    sites = requests.get(f"{LEDGER_URL}/sites", timeout=10).json()
    if not sites:
        raise SystemExit("No sites in the ledger. Run: python -m ledger.seed")

    for site in sites:
        if synthetic:
            alerts = synthetic_alerts(site)
            source = "synthetic"
        else:
            alerts = fetch_weather_alerts(site["lat"], site["lon"])
            source = "weather.gov"

        multiplier, reason = demand_multiplier(alerts)
        for category in CATEGORIES:
            post_forecast(site["id"], category, multiplier, reason, source)

        print(f"{site['name']}: x{multiplier} ({reason})")

    # FEMA context is fetched but not yet folded into the multiplier, see the
    # task list in disruption_agent/README.md.
    if not synthetic:
        declarations = fetch_fema_declarations()
        if declarations:
            latest = declarations[0]
            print(
                f"Latest CA FEMA declaration: {latest.get('declarationTitle')} "
                f"({latest.get('declarationDate', '')[:10]})"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="ReliefLink disruption agent")
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="fabricate a severe storm instead of calling live APIs",
    )
    args = parser.parse_args()
    run(synthetic=args.synthetic)


if __name__ == "__main__":
    main()
