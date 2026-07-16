"""ReliefLink reallocation agent: ledger gaps -> transfer recommendations.

Run with the ledger seeded and running:
    python -m reallocation_agent.agent

Use ``--dry-run`` to print the plan without posting recommendations, or ``--demo``
to run the original hard-coded solver example without a ledger.
"""

import argparse
import json
import os
from typing import TypedDict

import requests
from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, START, StateGraph
from ortools.linear_solver import pywraplp

from shared.config import CATEGORIES, CLAUDE_MODEL, LEDGER_URL


class ReallocationState(TypedDict, total=False):
    """Data passed between nodes in the reallocation graph."""

    dry_run: bool
    why_question: str | None
    gaps: list[dict]
    routes: list[dict]
    capacities: list[dict]
    plan: list[dict]
    posted: list[dict]
    justification: str
    why_answer: str


def solve_transfers(
    surplus: dict[int, int],
    shortage: dict[int, int],
    cost: dict[tuple[int, int], float],
    source_capacity: dict[int, int] | None = None,
) -> list[tuple[int, int, int]]:
    """Solve a minimum-distance transportation plan for one category.

    Missing routes are excluded. ``source_capacity`` limits all outbound units from
    a site to its available truck capacity.
    """
    solver = pywraplp.Solver.CreateSolver("GLOP")
    if solver is None:
        raise RuntimeError("OR-Tools GLOP solver is unavailable")

    lanes = [(src, dst) for src in surplus for dst in shortage if (src, dst) in cost]
    move = {
        (src, dst): solver.NumVar(0, surplus[src], f"move_{src}_{dst}")
        for src, dst in lanes
    }

    for src, available in surplus.items():
        outbound = [move[src, dst] for lane_src, dst in lanes if lane_src == src]
        if outbound:
            limit = min(available, (source_capacity or {}).get(src, available))
            solver.Add(sum(outbound) <= limit)

    for dst, needed in shortage.items():
        inbound = [move[src, dst] for src, lane_dst in lanes if lane_dst == dst]
        if inbound:
            solver.Add(sum(inbound) <= needed)

    # Filling shortages is the primary goal; distance breaks ties between plans.
    delivery_reward = max(cost.values(), default=0) + 1
    solver.Minimize(
        sum(
            (cost[src, dst] - delivery_reward) * variable
            for (src, dst), variable in move.items()
        )
    )

    if solver.Solve() != pywraplp.Solver.OPTIMAL:
        return []
    return [
        (src, dst, round(variable.solution_value()))
        for (src, dst), variable in move.items()
        if variable.solution_value() > 0.5
    ]


def route_costs(routes: list[dict]) -> dict[tuple[int, int], float]:
    """Expand ledger routes, which are stored once per symmetric site pair."""
    costs: dict[tuple[int, int], float] = {}
    for route in routes:
        src, dst, miles = route["from_site_id"], route["to_site_id"], route["miles"]
        costs[src, dst] = miles
        costs[dst, src] = miles
    return costs


def truck_capacities(capacities: list[dict]) -> dict[int, int]:
    return {
        row["site_id"]: row["trucks"] * row["max_load_units"]
        for row in capacities
    }


def build_plan(
    gaps: list[dict], routes: list[dict], capacities: list[dict]
) -> list[dict]:
    """Turn ledger responses into recommendation request bodies."""
    costs = route_costs(routes)
    capacity_by_site = truck_capacities(capacities)
    plan = []

    for category in CATEGORIES:
        category_gaps = [row for row in gaps if row["category"] == category]
        surplus = {row["site_id"]: -row["gap"] for row in category_gaps if row["gap"] < 0}
        shortage = {row["site_id"]: row["gap"] for row in category_gaps if row["gap"] > 0}
        if not surplus or not shortage:
            continue

        for src, dst, quantity in solve_transfers(
            surplus, shortage, costs, capacity_by_site
        ):
            plan.append(
                {
                    "from_site_id": src,
                    "to_site_id": dst,
                    "category": category,
                    "quantity": quantity,
                    "reason": (
                        f"Move {quantity} units to reduce site {dst}'s "
                        f"{category} shortfall of {shortage[dst]}"
                    ),
                }
            )
    return plan


def fetch(path: str) -> list[dict]:
    response = requests.get(f"{LEDGER_URL}{path}", timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_node(state: ReallocationState) -> dict:
    """Fetch every optimizer input through the ledger HTTP contract."""
    return {
        "gaps": fetch("/gaps"),
        "routes": fetch("/routes"),
        "capacities": fetch("/capacity"),
    }


def solve_node(state: ReallocationState) -> dict:
    return {
        "plan": build_plan(state["gaps"], state["routes"], state["capacities"])
    }


def post_node(state: ReallocationState) -> dict:
    """Post proposed transfers, unless this graph invocation is a dry run."""
    if state.get("dry_run"):
        return {"posted": []}

    posted = []
    for recommendation in state["plan"]:
        response = requests.post(
            f"{LEDGER_URL}/recommendations", json=recommendation, timeout=10
        )
        response.raise_for_status()
        posted.append(response.json())
    return {"posted": posted}


def fallback_justification(plan: list[dict]) -> str:
    if not plan:
        return "No feasible transfers were found from the current ledger data."
    total = sum(item["quantity"] for item in plan)
    return (
        f"The optimizer proposes {len(plan)} transfer(s), moving {total} total units "
        "from surplus sites toward forecast shortages while minimizing route distance "
        "and respecting available truck capacity."
    )


def message_text(message) -> str:
    """Normalize LangChain text or content-block responses to plain text."""
    if isinstance(message.content, str):
        return message.content
    return "\n".join(
        block.get("text", "")
        for block in message.content
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()


def claude_node(state: ReallocationState) -> dict:
    """Explain the optimized plan and optionally answer an ops director's question."""
    plan = state.get("plan", [])
    fallback = fallback_justification(plan)
    question = state.get("why_question")

    # --dry-run is deliberately key-free, even when a key happens to be configured.
    if state.get("dry_run") or not os.getenv("ANTHROPIC_API_KEY"):
        result = {"justification": fallback}
        if question:
            result["why_answer"] = f"{fallback} Question received: {question}"
        return result

    model = ChatAnthropic(model=CLAUDE_MODEL)
    evidence = {
        "plan": plan,
        "gaps": state.get("gaps", []),
        "routes": state.get("routes", []),
        "capacities": state.get("capacities", []),
    }
    prompt = (
        "You are explaining a food-bank inventory transfer plan to an operations "
        "director. In no more than three sentences, explain why the transfers are "
        "needed, cite quantities and site IDs, and mention route/truck constraints. "
        "Routes are symmetric even though each pair is stored once. Do not invent "
        "facts.\n\nOptimizer evidence:\n" + json.dumps(evidence, indent=2)
    )
    justification = message_text(model.invoke(prompt)) or fallback
    result = {"justification": justification}
    if question:
        why_prompt = (
            "Answer the operations director's follow-up using only the transfer plan. "
            "Use the supplied gaps, symmetric routes, and truck capacities to explain "
            "why the optimizer chose a source or route. Be concise and say when the "
            "evidence lacks enough information.\n\n"
            f"Evidence: {json.dumps(evidence)}\nJustification: {justification}\n"
            f"Question: {question}"
        )
        result["why_answer"] = message_text(model.invoke(why_prompt))
    return result


def build_graph():
    graph = StateGraph(ReallocationState)
    graph.add_node("fetch", fetch_node)
    graph.add_node("solve", solve_node)
    graph.add_node("post", post_node)
    graph.add_node("claude", claude_node)
    graph.add_edge(START, "fetch")
    graph.add_edge("fetch", "solve")
    graph.add_edge("solve", "post")
    graph.add_edge("post", "claude")
    graph.add_edge("claude", END)
    return graph.compile()


REALLOCATION_GRAPH = build_graph()


def run(dry_run: bool = False, why_question: str | None = None) -> list[dict]:
    """Invoke the ledger-connected reallocation LangGraph."""
    state = REALLOCATION_GRAPH.invoke(
        {"dry_run": dry_run, "why_question": why_question}
    )
    plan = state["plan"]
    if not plan:
        print(state["justification"])
        if why_question:
            print(f"\nWhy: {state['why_answer']}")
        return []

    for recommendation in plan:
        print(
            f"move {recommendation['quantity']} {recommendation['category']} units "
            f"from site {recommendation['from_site_id']} "
            f"to site {recommendation['to_site_id']}"
        )
    print(f"\nJustification: {state['justification']}")
    if why_question:
        print(f"\nWhy: {state['why_answer']}")
    return plan


def demo() -> None:
    surplus = {1: 150, 4: 200}
    shortage = {3: 180}
    cost = {(1, 3): 75.0, (4, 3): 105.0}
    print("Toy transportation solve (canned_goods):")
    for src, dst, quantity in solve_transfers(surplus, shortage, cost):
        print(f"  move {quantity} units from site {src} to site {dst}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ReliefLink reallocation agent")
    parser.add_argument("--dry-run", action="store_true", help="print but do not post the plan")
    parser.add_argument("--demo", action="store_true", help="run without a ledger")
    parser.add_argument("--why", help="ask a follow-up question about the resulting plan")
    args = parser.parse_args()
    demo() if args.demo else run(dry_run=args.dry_run, why_question=args.why)


if __name__ == "__main__":
    main()
