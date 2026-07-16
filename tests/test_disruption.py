"""Unit tests for the disruption agent's scoring logic. No network calls.

Run with: pytest
"""

from datetime import date, datetime, timedelta, timezone

from disruption_agent.agent import (
    DISRUPTION_GRAPH,
    MAX_MULTIPLIER,
    active_fema_counties,
    alert_coverage,
    category_multiplier,
    claude_reason_node,
    forecast_node,
    worst_alert,
)
from disruption_agent.demand_model import baseline_demand, generate_history

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


def make_alert(severity: str = "Severe", start_h: float = -2, end_h: float = 48) -> dict:
    return {
        "event": "Test Storm",
        "severity": severity,
        "onset": (NOW + timedelta(hours=start_h)).isoformat(),
        "ends": (NOW + timedelta(hours=end_h)).isoformat(),
    }


# ---------------------------------------------------------------- coverage


def test_alert_covering_whole_window_has_full_coverage():
    assert alert_coverage(make_alert(start_h=-5, end_h=60), NOW) == 1.0


def test_alert_ending_halfway_has_half_coverage():
    assert alert_coverage(make_alert(start_h=-2, end_h=24), NOW) == 0.5


def test_expired_alert_has_zero_coverage():
    assert alert_coverage(make_alert(start_h=-10, end_h=-1), NOW) == 0.0


def test_alert_with_no_timestamps_assumes_full_window():
    assert alert_coverage({"event": "Storm", "severity": "Severe"}, NOW) == 1.0


# ---------------------------------------------------------------- worst alert


def test_worst_alert_picks_strongest_effective_impact():
    alerts = [make_alert(severity="Minor"), make_alert(severity="Severe")]
    spike, coverage, reason = worst_alert(alerts, NOW)
    assert spike == 2.0
    assert coverage == 1.0
    assert "Test Storm" in reason


def test_no_alerts_means_no_spike():
    assert worst_alert([], NOW) == (1.0, 0.0, "no active alerts")


# ---------------------------------------------------------------- multipliers


def test_shelf_stable_food_spikes_hardest():
    canned = category_multiplier(2.0, 1.0, "canned_goods", fema_active=False)
    dairy = category_multiplier(2.0, 1.0, "dairy", fema_active=False)
    assert canned == 2.0
    assert dairy < canned


def test_partial_coverage_scales_the_spike_down():
    full = category_multiplier(2.0, 1.0, "canned_goods", fema_active=False)
    half = category_multiplier(2.0, 0.5, "canned_goods", fema_active=False)
    assert half == 1.5
    assert half < full


def test_fema_bump_applies_and_multiplier_is_capped():
    multiplier = category_multiplier(3.0, 1.0, "canned_goods", fema_active=True)
    assert multiplier == MAX_MULTIPLIER  # 3.0 spike * 1.5 FEMA would be 4.5, capped


# ---------------------------------------------------------------- FEMA matching


def test_recent_declaration_matches_county():
    declarations = [{"designatedArea": "Santa Cruz (County)", "declarationDate": NOW.isoformat()}]
    assert active_fema_counties(declarations, NOW) == {"santa cruz"}


def test_old_declaration_is_ignored():
    old = (NOW - timedelta(days=120)).isoformat()
    declarations = [{"designatedArea": "Santa Cruz (County)", "declarationDate": old}]
    assert active_fema_counties(declarations, NOW) == set()


# ---------------------------------------------------------------- demand model


def test_history_is_deterministic_and_non_negative():
    end = date(2026, 7, 1)
    first = generate_history(1, "produce", end=end)
    second = generate_history(1, "produce", end=end)
    assert first == second
    assert all(units >= 0 for _, units in first)
    assert len(first) == 90


def test_baseline_demand_is_positive_and_scales_with_horizon():
    start = date(2026, 7, 1)
    two_days = baseline_demand(2, "canned_goods", 48, start=start)
    one_day = baseline_demand(2, "canned_goods", 24, start=start)
    assert one_day > 0
    assert two_days > one_day


# ---------------------------------------------------------------- LangGraph nodes


def test_disruption_graph_has_expected_nodes():
    nodes = DISRUPTION_GRAPH.get_graph().nodes
    assert {"fetch", "score", "claude_reason", "forecast", "post"}.issubset(nodes)


def test_synthetic_reason_node_never_needs_a_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-be-used")
    result = claude_reason_node(
        {
            "synthetic": True,
            "scored_sites": [
                {
                    "site": {"id": 7, "name": "Test", "county": "Alameda"},
                    "alerts": [],
                    "coverage": 0.0,
                    "fema_active": False,
                    "fallback_reason": "no active alerts",
                }
            ],
        }
    )
    assert result == {"reasons": {7: "no active alerts"}}


def test_forecast_node_uses_reason_and_contract_shape():
    result = forecast_node(
        {
            "synthetic": True,
            "reasons": {7: "Synthetic storm summary"},
            "scored_sites": [
                {
                    "site": {"id": 7},
                    "spike": 2.0,
                    "coverage": 0.5,
                    "fema_active": False,
                }
            ],
        }
    )
    forecasts = result["forecasts"]
    assert len(forecasts) == 4
    assert {row["category"] for row in forecasts} == {
        "canned_goods",
        "produce",
        "dairy",
        "dry_goods",
    }
    assert all(row["reason"] == "Synthetic storm summary" for row in forecasts)
    assert all(row["source"] == "synthetic" for row in forecasts)
