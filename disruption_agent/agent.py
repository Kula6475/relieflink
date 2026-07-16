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
import math
import time
from datetime import datetime, timedelta, timezone

import requests

from disruption_agent.demand_model import baseline_demand
from shared.config import CATEGORIES, LEDGER_URL

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


def run(synthetic: bool = False, verbose: bool = False) -> None:
    now = datetime.now(timezone.utc)
    sites = requests.get(f"{LEDGER_URL}/sites", timeout=10).json()
    if not sites:
        raise SystemExit("No sites in the ledger. Run: python -m ledger.seed")

    declarations = synthetic_declarations(now) if synthetic else fetch_fema_declarations()
    fema_counties = active_fema_counties(declarations, now)
    source = "synthetic" if synthetic else "weather.gov"

    for site in sites:
        alerts = (
            synthetic_alerts(site, now)
            if synthetic
            else fetch_weather_alerts(site["lat"], site["lon"])
        )
        if verbose:
            for alert in alerts:
                print(
                    f"  raw alert @ {site['name']}: event={alert.get('event')!r} "
                    f"severity={alert.get('severity')!r} onset={alert.get('onset')} "
                    f"ends={alert.get('ends') or alert.get('expires')}"
                )

        spike, coverage, reason = worst_alert(alerts, now)
        fema_active = site["county"].lower() in fema_counties
        if fema_active:
            reason += f"; FEMA declaration active for {site['county']} County (x{FEMA_MULTIPLIER})"

        multipliers = {}
        for category in CATEGORIES:
            multiplier = category_multiplier(spike, coverage, category, fema_active)
            baseline = baseline_demand(site["id"], category, HORIZON_HOURS)
            post_forecast(
                site["id"], category, math.ceil(baseline * multiplier), multiplier, reason, source
            )
            multipliers[category] = multiplier

        print(f"{site['name']}: {multipliers} ({reason})")


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
