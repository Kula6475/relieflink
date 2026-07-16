"""Tests for the reallocation solver. Pure LP, no network. Run with: pytest"""

from reallocation_agent.agent import solve_transfers


def test_nearest_surplus_covers_the_shortage():
    surplus = {(1, "canned_goods"): 150, (4, "canned_goods"): 200}
    shortage = {(3, "canned_goods"): 180}
    miles = {(1, 3): 75.0, (3, 4): 105.0}
    capacity = {1: 1000, 4: 1000}

    transfers = solve_transfers(surplus, shortage, miles, capacity)
    moved = {(t["from_site_id"], t["to_site_id"]): t["quantity"] for t in transfers}

    assert sum(moved.values()) == 180
    assert moved[(1, 3)] == 150  # cheaper lane maxes out first
    assert moved[(4, 3)] == 30


def test_capacity_limits_outbound_units():
    surplus = {(1, "canned_goods"): 500, (1, "dry_goods"): 500}
    shortage = {(2, "canned_goods"): 400, (2, "dry_goods"): 400}
    miles = {(1, 2): 40.0}
    capacity = {1: 300}  # one small truck: 300 units TOTAL across categories

    transfers = solve_transfers(surplus, shortage, miles, capacity)
    assert sum(t["quantity"] for t in transfers) == 300


def test_categories_never_cross():
    surplus = {(1, "dairy"): 100}
    shortage = {(2, "canned_goods"): 100}
    transfers = solve_transfers(surplus, shortage, {(1, 2): 10.0}, {1: 1000})
    assert transfers == []


def test_no_gaps_no_transfers():
    assert solve_transfers({}, {}, {}, {}) == []
