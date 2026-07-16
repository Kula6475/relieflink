"""ReliefLink reallocation LangGraph: ledger gaps -> transfer recommendations.

The graph fetches gaps, routes, capacity, and sites; solves one OR-Tools program
across all categories; posts recommendations; then explains the result with Claude.
``--dry-run`` never posts or calls Claude and remains a no-key demo path.
"""

import argparse
import json
import os
from typing import TypedDict

import requests
from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, START, StateGraph
from ortools.linear_solver import pywraplp

from shared.config import CLAUDE_MODEL, LEDGER_URL

DELIVERY_REWARD = 1000
UNKNOWN_ROUTE_MILES = 999.0


class ReallocationState(TypedDict, total=False):
    dry_run: bool
    why_question: str | None
    gaps: list[dict]
    routes: list[dict]
    capacities: list[dict]
    sites: list[dict]
    site_names: dict[int, str]
    plan: list[dict]
    posted: list[dict]
    justification: str
    why_answer: str


def solve_transfers(
    surplus: dict[tuple[int, str], int],
    shortage: dict[tuple[int, str], int],
    miles: dict[tuple[int, int], float],
    capacity_units: dict[int, int],
) -> list[dict]:
    """Solve one LP across all categories with total outbound capacity per site."""
    solver = pywraplp.Solver.CreateSolver("GLOP")
    if solver is None:
        raise RuntimeError("OR-Tools GLOP solver is unavailable")

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
            sum(move[lane] for lane in lanes if lane[0] == src and lane[2] == category)
            <= spare
        )
    for (dst, category), need in shortage.items():
        solver.Add(
            sum(move[lane] for lane in lanes if lane[1] == dst and lane[2] == category)
            <= need
        )
    for src in {lane[0] for lane in lanes}:
        solver.Add(
            sum(move[lane] for lane in lanes if lane[0] == src)
            <= capacity_units.get(src, 0)
        )

    solver.Minimize(
        sum(
            (lane_miles(src, dst) - DELIVERY_REWARD) * move[src, dst, category]
            for src, dst, category in lanes
        )
    )
    if solver.Solve() != pywraplp.Solver.OPTIMAL:
        return []

    return [
        {
            "from_site_id": src,
            "to_site_id": dst,
            "category": category,
            "quantity": round(variable.solution_value()),
            "miles": lane_miles(src, dst),
        }
        for (src, dst, category), variable in move.items()
        if variable.solution_value() > 0.5
    ]


def fetch(path: str) -> list[dict]:
    response = requests.get(f"{LEDGER_URL}{path}", timeout=10)
    response.raise_for_status()
    return response.json()


def fetch_node(state: ReallocationState) -> dict:
    sites = fetch("/sites")
    return {
        "gaps": fetch("/gaps"),
        "routes": fetch("/routes"),
        "capacities": fetch("/capacity"),
        "sites": sites,
        "site_names": {site["id"]: site["name"] for site in sites},
    }


def solve_node(state: ReallocationState) -> dict:
    gaps = state["gaps"]
    surplus = {(g["site_id"], g["category"]): -g["gap"] for g in gaps if g["gap"] < 0}
    shortage = {(g["site_id"], g["category"]): g["gap"] for g in gaps if g["gap"] > 0}
    miles = {(r["from_site_id"], r["to_site_id"]): r["miles"] for r in state["routes"]}
    capacity_units = {
        row["site_id"]: row["trucks"] * row["max_load_units"]
        for row in state["capacities"]
    }
    return {"plan": solve_transfers(surplus, shortage, miles, capacity_units)}


def recommendation_payload(transfer: dict, state: ReallocationState) -> dict:
    names = state["site_names"]
    need = next(
        (
            gap["gap"]
            for gap in state["gaps"]
            if gap["site_id"] == transfer["to_site_id"]
            and gap["category"] == transfer["category"]
        ),
        0,
    )
    return {
        "from_site_id": transfer["from_site_id"],
        "to_site_id": transfer["to_site_id"],
        "category": transfer["category"],
        "quantity": transfer["quantity"],
        "reason": (
            f"{names[transfer['to_site_id']]} is {need} short on "
            f"{transfer['category']} under the current forecast; "
            f"{names[transfer['from_site_id']]} has spare "
            f"({transfer['miles']:.0f} mi run)"
        ),
    }


def post_node(state: ReallocationState) -> dict:
    if state.get("dry_run"):
        return {"posted": []}
    posted = []
    for transfer in state["plan"]:
        response = requests.post(
            f"{LEDGER_URL}/recommendations",
            json=recommendation_payload(transfer, state),
            timeout=10,
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
        "and respecting total outbound truck capacity."
    )


def message_text(message) -> str:
    if isinstance(message.content, str):
        return message.content
    return "\n".join(
        block.get("text", "")
        for block in message.content
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()


def claude_node(state: ReallocationState) -> dict:
    plan = state.get("plan", [])
    fallback = fallback_justification(plan)
    question = state.get("why_question")
    if state.get("dry_run") or not os.getenv("ANTHROPIC_API_KEY"):
        result = {"justification": fallback}
        if question:
            result["why_answer"] = f"{fallback} Question received: {question}"
        return result

    evidence = {
        "plan": plan,
        "gaps": state.get("gaps", []),
        "routes": state.get("routes", []),
        "capacities": state.get("capacities", []),
        "sites": state.get("sites", []),
    }
    model = ChatAnthropic(model=CLAUDE_MODEL)
    prompt = (
        "You advise a food-bank operations director. In no more than three sentences, "
        "explain why these transfers are needed, cite quantities and site names, and "
        "mention relevant route and total truck-capacity constraints. Routes are "
        "symmetric. Do not invent facts.\n\n" + json.dumps(evidence, indent=2)
    )
    justification = message_text(model.invoke(prompt)) or fallback
    result = {"justification": justification}
    if question:
        why_prompt = (
            "Answer the operations director's question using only this optimizer "
            "evidence. Explain source/route choices from gaps, symmetric distances, "
            "and total truck capacity. Be concise and admit missing information.\n\n"
            f"Evidence: {json.dumps(evidence)}\nQuestion: {question}"
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
    state = REALLOCATION_GRAPH.invoke({"dry_run": dry_run, "why_question": why_question})
    plan = state["plan"]
    if not plan:
        print(state["justification"])
    for transfer in plan:
        print(
            f"move {transfer['quantity']:>4} {transfer['category']:<13} "
            f"{state['site_names'][transfer['from_site_id']]} -> "
            f"{state['site_names'][transfer['to_site_id']]}"
        )
    if plan and not dry_run:
        print(f"\n{len(state['posted'])} recommendation(s) posted.")
    print(f"\nJustification: {state['justification']}")
    if why_question:
        print(f"\nWhy: {state['why_answer']}")
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description="ReliefLink reallocation agent")
    parser.add_argument("--dry-run", action="store_true", help="solve without posting or Claude")
    parser.add_argument("--why", help="ask a follow-up question about the resulting plan")
    args = parser.parse_args()
    run(dry_run=args.dry_run, why_question=args.why)


if __name__ == "__main__":
    main()
