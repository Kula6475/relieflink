"""Tests for the reallocation solver and LangGraph nodes."""

from reallocation_agent.agent import REALLOCATION_GRAPH, claude_node, solve_transfers


def test_nearest_surplus_covers_the_shortage():
    surplus = {(1, "canned_goods"): 150, (4, "canned_goods"): 200}
    shortage = {(3, "canned_goods"): 180}
    transfers = solve_transfers(
        surplus, shortage, {(1, 3): 75.0, (3, 4): 105.0}, {1: 1000, 4: 1000}
    )
    moved = {(row["from_site_id"], row["to_site_id"]): row["quantity"] for row in transfers}
    assert sum(moved.values()) == 180
    assert moved[(1, 3)] == 150
    assert moved[(4, 3)] == 30


def test_capacity_limits_total_outbound_units():
    surplus = {(1, "canned_goods"): 500, (1, "dry_goods"): 500}
    shortage = {(2, "canned_goods"): 400, (2, "dry_goods"): 400}
    transfers = solve_transfers(surplus, shortage, {(1, 2): 40.0}, {1: 300})
    assert sum(row["quantity"] for row in transfers) == 300


def test_categories_never_cross():
    transfers = solve_transfers(
        {(1, "dairy"): 100}, {(2, "canned_goods"): 100}, {(1, 2): 10.0}, {1: 1000}
    )
    assert transfers == []


def test_no_gaps_no_transfers():
    assert solve_transfers({}, {}, {}, {}) == []


def test_reallocation_graph_has_expected_nodes():
    assert {"fetch", "solve", "post", "claude"}.issubset(
        REALLOCATION_GRAPH.get_graph().nodes
    )


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
