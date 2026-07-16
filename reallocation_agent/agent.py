"""ReliefLink reallocation agent: gaps -> minimum-cost transfer plan -> recommendations.

Pulls surplus/shortage per (site, category) from the ledger's /gaps endpoint, the
distance matrix from /routes, and per-site truck capacity from /capacity, then solves
one linear program across all categories:

    minimize    total miles driven  -  (big reward per unit delivered)
    subject to  a site never gives more than its spare units per category
                a site never receives more than its shortfall per category
                a site's TOTAL outbound units stay within trucks x max load

Each chosen transfer is POSTed to /recommendations (status "proposed"); the ops
director approves them on the dashboard's Transfers tab. If ANTHROPIC_API_KEY is set,
Claude writes a short plain-language justification of the overall plan.

Run (after inventory + forecasts exist):
    python -m reallocation_agent.agent            # solve and post recommendations
    python -m reallocation_agent.agent --dry-run  # solve and print only
"""

import argparse
import os

import requests
from ortools.linear_solver import pywraplp

from shared.config import CLAUDE_MODEL, LEDGER_URL

DELIVERY_REWARD = 1000  # per-unit reward so filling shortages beats saving fuel
UNKNOWN_ROUTE_MILES = 999.0


def solve_transfers(
    surplus: dict[tuple[int, str], int],
    shortage: dict[tuple[int, str], int],
    miles: dict[tuple[int, int], float],
    capacity_units: dict[int, int],
) -> list[dict]:
    """One LP across all categories with per-site outbound capacity.

    surplus/shortage are keyed by (site_id, category); miles by (from, to) symmetric.
    Returns [{"from_site_id", "to_site_id", "category", "quantity", "miles"}, ...]
    """
    solver = pywraplp.Solver.CreateSolver("GLOP")

    lanes = [
        (src, dst, category)
        for (src, category) in surplus
        for (dst, dst_category) in shortage
        if dst_category == category and src != dst
    ]
    if not lanes:
        return []

    move = {lane: solver.NumVar(0, solver.infinity(), f"move_{lane}") for lane in lanes}

    def lane_miles(src: int, dst: int) -> float:
        return miles.get((src, dst), miles.get((dst, src), UNKNOWN_ROUTE_MILES))

    for (src, category), spare in surplus.items():
        solver.Add(
            sum(move[lane] for lane in lanes if lane[0] == src and lane[2] == category) <= spare
        )
    for (dst, category), need in shortage.items():
        solver.Add(
            sum(move[lane] for lane in lanes if lane[1] == dst and lane[2] == category) <= need
        )
    for src in {lane[0] for lane in lanes}:
        solver.Add(
            sum(move[lane] for lane in lanes if lane[0] == src) <= capacity_units.get(src, 0)
        )

    solver.Minimize(
        sum(
            (lane_miles(src, dst) - DELIVERY_REWARD) * move[(src, dst, category)]
            for (src, dst, category) in lanes
        )
    )

    if solver.Solve() != pywraplp.Solver.OPTIMAL:
        return []

    return [
        {
            "from_site_id": src,
            "to_site_id": dst,
            "category": category,
            "quantity": round(var.solution_value()),
            "miles": lane_miles(src, dst),
        }
        for (src, dst, category), var in move.items()
        if var.solution_value() > 0.5
    ]


def explain_with_claude(transfers: list[dict], site_names: dict[int, str]) -> str | None:
    """Plain-language justification for the ops director. Skipped without an API key."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    import anthropic

    plan = "\n".join(
        f"- move {t['quantity']} {t['category']} from {site_names[t['from_site_id']]} "
        f"to {site_names[t['to_site_id']]} ({t['miles']:.0f} mi)"
        for t in transfers
    )
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": (
                    "You advise a food bank ops director. In 3 short sentences of plain "
                    "language, justify this transfer plan (why these moves, why now):\n"
                    f"{plan}"
                ),
            }
        ],
    )
    return next((block.text for block in response.content if block.type == "text"), None)


def run(dry_run: bool = False) -> None:
    gaps = requests.get(f"{LEDGER_URL}/gaps", timeout=10).json()
    routes = requests.get(f"{LEDGER_URL}/routes", timeout=10).json()
    capacity = requests.get(f"{LEDGER_URL}/capacity", timeout=10).json()
    sites = requests.get(f"{LEDGER_URL}/sites", timeout=10).json()
    site_names = {site["id"]: site["name"] for site in sites}

    if not gaps:
        raise SystemExit(
            "No gaps to solve: the ledger needs both inventory and forecasts first.\n"
            "  python -m vision_agent.agent --site-id 1 --fake   (or use /camera)\n"
            "  python -m disruption_agent.agent --synthetic"
        )

    surplus = {(g["site_id"], g["category"]): -g["gap"] for g in gaps if g["gap"] < 0}
    shortage = {(g["site_id"], g["category"]): g["gap"] for g in gaps if g["gap"] > 0}
    miles = {(r["from_site_id"], r["to_site_id"]): r["miles"] for r in routes}
    capacity_units = {c["site_id"]: c["trucks"] * c["max_load_units"] for c in capacity}

    transfers = solve_transfers(surplus, shortage, miles, capacity_units)
    if not transfers:
        print("Nothing to move: no site has spare units where another is short.")
        return

    shortfall = {key: value for key, value in shortage.items()}
    for transfer in transfers:
        need = shortfall.get((transfer["to_site_id"], transfer["category"]), 0)
        reason = (
            f"{site_names[transfer['to_site_id']]} is {need} short on "
            f"{transfer['category']} under the current forecast; "
            f"{site_names[transfer['from_site_id']]} has spare "
            f"({transfer['miles']:.0f} mi run)"
        )
        print(
            f"move {transfer['quantity']:>4} {transfer['category']:<13} "
            f"{site_names[transfer['from_site_id']]} -> {site_names[transfer['to_site_id']]}"
        )
        if not dry_run:
            requests.post(
                f"{LEDGER_URL}/recommendations",
                json={
                    "from_site_id": transfer["from_site_id"],
                    "to_site_id": transfer["to_site_id"],
                    "category": transfer["category"],
                    "quantity": transfer["quantity"],
                    "reason": reason,
                },
                timeout=10,
            ).raise_for_status()

    if not dry_run:
        print(f"\n{len(transfers)} recommendation(s) posted, approve them on the dashboard.")

    explanation = explain_with_claude(transfers, site_names)
    if explanation:
        print(f"\nClaude's summary for the ops director:\n{explanation}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ReliefLink reallocation agent")
    parser.add_argument(
        "--dry-run", action="store_true", help="solve and print, do not post recommendations"
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
