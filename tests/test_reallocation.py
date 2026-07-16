"""Unit tests for the ledger-connected reallocation planner."""

from reallocation_agent.agent import (
    REALLOCATION_GRAPH,
    build_plan,
    claude_node,
    route_costs,
    solve_transfers,
)


def test_route_costs_are_symmetric():
    routes = [{"from_site_id": 1, "to_site_id": 2, "miles": 12.5}]
    assert route_costs(routes) == {(1, 2): 12.5, (2, 1): 12.5}


def test_solver_respects_truck_capacity():
    transfers = solve_transfers(
        surplus={1: 200},
        shortage={2: 180},
        cost={(1, 2): 10.0},
        source_capacity={1: 75},
    )
    assert transfers == [(1, 2, 75)]


def test_build_plan_connects_gaps_routes_and_capacity():
    gaps = [
        {"site_id": 1, "category": "canned_goods", "gap": -150},
        {"site_id": 2, "category": "canned_goods", "gap": 120},
    ]
    routes = [{"from_site_id": 1, "to_site_id": 2, "miles": 20.0}]
    capacities = [{"site_id": 1, "trucks": 1, "max_load_units": 100}]

    assert build_plan(gaps, routes, capacities) == [
        {
            "from_site_id": 1,
            "to_site_id": 2,
            "category": "canned_goods",
            "quantity": 100,
            "reason": "Move 100 units to reduce site 2's canned_goods shortfall of 120",
        }
    ]


def test_build_plan_skips_missing_routes():
    gaps = [
        {"site_id": 1, "category": "dairy", "gap": -25},
        {"site_id": 2, "category": "dairy", "gap": 25},
    ]
    assert build_plan(gaps, routes=[], capacities=[]) == []


def test_reallocation_graph_has_expected_nodes():
    nodes = REALLOCATION_GRAPH.get_graph().nodes
    assert {"fetch", "solve", "post", "claude"}.issubset(nodes)


def test_dry_run_why_answer_never_needs_a_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-be-used")
    result = claude_node(
        {
            "dry_run": True,
            "why_question": "Why this route?",
            "plan": [
                {
                    "from_site_id": 1,
                    "to_site_id": 2,
                    "category": "dairy",
                    "quantity": 10,
                }
            ],
        }
    )
    assert "1 transfer" in result["justification"]
    assert "Why this route?" in result["why_answer"]
