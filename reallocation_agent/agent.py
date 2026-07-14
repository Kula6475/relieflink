"""ReliefLink reallocation agent (PHASE 2 - starts after the other sections land).

Owners: everyone, built together.

Takes real inventory (camera-fed) and predicted demand, computes the surplus/shortage
gap per site per category, and solves a minimum-cost transportation problem with
OR-Tools to recommend what to move where. A Claude call then explains the plan in
plain language for the ops director.

The toy example below already solves a hardcoded transportation problem, so you can
see the OR-Tools pattern working today:

    python -m reallocation_agent.agent
"""

from ortools.linear_solver import pywraplp


def solve_transfers(
    surplus: dict[int, int],
    shortage: dict[int, int],
    cost: dict[tuple[int, int], float],
) -> list[tuple[int, int, int]]:
    """Minimum-cost transportation solve for ONE category.

    surplus:  {site_id: units available to give}
    shortage: {site_id: units needed}
    cost:     {(from_site, to_site): miles}

    Returns [(from_site, to_site, quantity), ...]
    """
    solver = pywraplp.Solver.CreateSolver("GLOP")

    # Decision variable: how many units to move along each (from, to) lane.
    move = {
        (src, dst): solver.NumVar(0, surplus[src], f"move_{src}_{dst}")
        for src in surplus
        for dst in shortage
    }

    # Each surplus site can give at most what it has spare.
    for src in surplus:
        solver.Add(sum(move[src, dst] for dst in shortage) <= surplus[src])

    # Each shortage site should receive at most what it needs
    # (and as much as possible, rewarded via the objective below).
    for dst in shortage:
        solver.Add(sum(move[src, dst] for src in surplus) <= shortage[dst])

    # Minimize miles driven, minus a big reward per unit delivered so the solver
    # prefers filling shortages over saving fuel.
    solver.Minimize(
        sum(cost[src, dst] * move[src, dst] for src in surplus for dst in shortage)
        - 1000 * sum(move[src, dst] for src in surplus for dst in shortage)
    )

    if solver.Solve() != pywraplp.Solver.OPTIMAL:
        return []
    return [
        (src, dst, round(var.solution_value()))
        for (src, dst), var in move.items()
        if var.solution_value() > 0.5
    ]


# ---------------------------------------------------------------- Phase 2 tasks
#
# TODO(team) - wire this to real data once Phase 1 lands:
#   1. GET /gaps from the ledger (Vivaan/Akul build it in Phase 1) to get
#      surplus/shortage per (site, category).
#   2. GET /routes for the cost matrix and /capacity for per-site truck limits
#      (add a capacity constraint to the solve).
#   3. Run solve_transfers() once per category.
#   4. POST each transfer to /recommendations with a reason string.
#   5. explain_with_claude(): send the gaps + chosen plan to Claude
#      (model from shared.config.CLAUDE_MODEL) and ask for a 3-sentence
#      plain-language explanation an ops director would trust, plus answers
#      to follow-up "why" questions.


def demo() -> None:
    """Toy run on hardcoded data: sites 1 and 4 have spare canned goods, 3 is short."""
    surplus = {1: 150, 4: 200}
    shortage = {3: 180}
    cost = {(1, 3): 75.0, (4, 3): 105.0}

    print("Toy transportation solve (canned_goods):")
    for src, dst, quantity in solve_transfers(surplus, shortage, cost):
        print(f"  move {quantity} units from site {src} to site {dst}")


if __name__ == "__main__":
    demo()
