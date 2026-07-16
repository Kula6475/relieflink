"""ReliefLink reallocation agent (Phase 2).

Owners: everyone, built together.

Pulls real gaps/routes/capacity from the ledger, solves a minimum-cost
transportation problem per category with OR-Tools, posts the resulting
transfers to /recommendations, and (optionally) asks Claude for a plain-
language explanation an ops director would trust.

    python -m reallocation_agent.agent            # toy hardcoded demo (no ledger needed)
    python -m reallocation_agent.agent --live      # real run against the ledger
    python -m reallocation_agent.agent --live --dry-run     # compute only, don't POST
    python -m reallocation_agent.agent --live --no-explain  # skip the Claude call
"""

import argparse

import requests
from ortools.linear_solver import pywraplp

from shared.config import CATEGORIES, CLAUDE_MODEL, LEDGER_URL

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "2-3 sentence plain-language summary of the overall plan.",
        },
        "transfers": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "explanation": {"type": "string"},
                },
                "required": ["index", "explanation"],
                "additionalProperties": False,
            },
        },
        "faq": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                },
                "required": ["question", "answer"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "transfers", "faq"],
    "additionalProperties": False,
}


def solve_transfers(
    surplus: dict[int, int],
    shortage: dict[int, int],
    cost: dict[tuple[int, int], float],
    capacity: dict[int, int] | None = None,
) -> list[tuple[int, int, int]]:
    """Minimum-cost transportation solve for ONE category.

    surplus:  {site_id: units available to give}
    shortage: {site_id: units needed}
    cost:     {(from_site, to_site): miles}
    capacity: optional {site_id: max units that site can ship out, e.g.
              trucks * max_load_units}. Caps outbound volume on top of surplus.

    Returns [(from_site, to_site, quantity), ...]
    """
    solver = pywraplp.Solver.CreateSolver("GLOP")

    # Decision variable: how many units to move along each (from, to) lane.
    move = {
        (src, dst): solver.NumVar(0, surplus[src], f"move_{src}_{dst}")
        for src in surplus
        for dst in shortage
    }

    # Each surplus site can give at most what it has spare (and, if provided,
    # at most what its trucks can physically carry).
    for src in surplus:
        cap = surplus[src] if capacity is None else min(surplus[src], capacity.get(src, surplus[src]))
        solver.Add(sum(move[src, dst] for dst in shortage) <= cap)

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


# --------------------------------------------------------------- Ledger I/O


def fetch(path: str) -> list[dict]:
    resp = requests.get(f"{LEDGER_URL}{path}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def post_recommendation(from_site_id: int, to_site_id: int, category: str, quantity: int, reason: str) -> dict:
    payload = {
        "from_site_id": from_site_id,
        "to_site_id": to_site_id,
        "category": category,
        "quantity": quantity,
        "reason": reason,
    }
    resp = requests.post(f"{LEDGER_URL}/recommendations", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


# --------------------------------------------------------------- Plan building


def build_plan_for_category(
    category: str,
    gaps: list[dict],
    cost: dict[tuple[int, int], float],
    capacity: dict[int, int],
) -> list[tuple[int, int, int]]:
    """surplus/shortage per site for one category, then solve."""
    cat_gaps = [g for g in gaps if g["category"] == category]
    surplus = {g["site_id"]: -g["gap"] for g in cat_gaps if g["gap"] < 0}
    shortage = {g["site_id"]: g["gap"] for g in cat_gaps if g["gap"] > 0}

    if not surplus or not shortage:
        return []

    return solve_transfers(surplus, shortage, cost, capacity)


def build_full_plan(gaps: list[dict], routes: list[dict], capacity_rows: list[dict]) -> list[dict]:
    """Run the solver once per category, return a flat list of transfer dicts."""
    # Routes are stored once per pair and treated as symmetric -- add both directions.
    # Fall back to a large cost for any (src, dst) pair with no stored route so the
    # solver never crashes on a missing lane, it just avoids using it unless forced.
    cost: dict[tuple[int, int], float] = {}
    for route in routes:
        cost[(route["from_site_id"], route["to_site_id"])] = route["miles"]
        cost[(route["to_site_id"], route["from_site_id"])] = route["miles"]

    site_ids = {g["site_id"] for g in gaps}
    for a in site_ids:
        for b in site_ids:
            if a != b:
                cost.setdefault((a, b), 999_999.0)

    capacity = {row["site_id"]: row["trucks"] * row["max_load_units"] for row in capacity_rows}

    plan = []
    for category in CATEGORIES:
        for src, dst, quantity in build_plan_for_category(category, gaps, cost, capacity):
            if quantity <= 0:
                continue
            plan.append({"category": category, "from_site_id": src, "to_site_id": dst, "quantity": quantity})
    return plan


# --------------------------------------------------------------- Explanation


def explain_with_claude(plan: list[dict], gaps: list[dict], site_names: dict[int, str]) -> dict:
    """One Claude call: plain-language summary, per-transfer explanation, and
    a short FAQ an ops director might ask. Falls back to a template if the
    API isn't configured (no API key, offline, etc.) so the demo never breaks.
    """
    if not plan:
        return {"summary": "No transfers proposed -- no shortages currently need covering.", "transfers": [], "faq": []}

    try:
        import anthropic

        readable_plan = [
            f"{p['quantity']} units of {p['category']} from "
            f"{site_names.get(p['from_site_id'], p['from_site_id'])} to "
            f"{site_names.get(p['to_site_id'], p['to_site_id'])}"
            for p in plan
        ]
        readable_gaps = [
            f"{site_names.get(g['site_id'], g['site_id'])}: {g['category']} gap {g['gap']:+d}"
            for g in gaps
            if g["gap"] != 0
        ]

        prompt = (
            "You are briefing a food bank operations director on a proposed supply "
            "reallocation plan. Be concrete and confident, plain language, no jargon.\n\n"
            f"Detected gaps:\n" + "\n".join(readable_gaps) + "\n\n"
            f"Proposed transfers:\n" + "\n".join(readable_plan) + "\n\n"
            "Write a 2-3 sentence summary of the plan, a one-sentence explanation "
            "for each individual transfer (indexed to match the order given), and "
            "2-3 FAQ entries anticipating questions the director might ask."
        )

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            output_config={"format": {"type": "json_schema", "schema": PLAN_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        import json

        text = next(block.text for block in response.content if block.type == "text")
        return json.loads(text)

    except Exception as exc:  # no API key, network issue, etc. -- keep the demo working
        print(f"(Claude explanation skipped: {exc})")
        return {
            "summary": f"Proposing {len(plan)} transfer(s) to cover detected shortages.",
            "transfers": [
                {
                    "index": i,
                    "explanation": (
                        f"Move {p['quantity']} {p['category']} from "
                        f"{site_names.get(p['from_site_id'], p['from_site_id'])} to "
                        f"{site_names.get(p['to_site_id'], p['to_site_id'])}."
                    ),
                }
                for i, p in enumerate(plan)
            ],
            "faq": [],
        }


# --------------------------------------------------------------- Live run


def run_live(dry_run: bool = False, explain: bool = True) -> None:
    sites = fetch("/sites")
    site_names = {s["id"]: s["name"] for s in sites}
    gaps = fetch("/gaps")
    routes = fetch("/routes")
    capacity_rows = fetch("/capacity")

    plan = build_full_plan(gaps, routes, capacity_rows)

    if not plan:
        print("No shortages currently need covering -- nothing to propose.")
        return

    explanation = (
        explain_with_claude(plan, gaps, site_names)
        if explain
        else {"summary": "", "transfers": [{"index": i, "explanation": ""} for i in range(len(plan))], "faq": []}
    )
    reason_by_index = {t["index"]: t["explanation"] for t in explanation.get("transfers", [])}

    if explanation.get("summary"):
        print(f"Plan summary: {explanation['summary']}\n")

    for i, p in enumerate(plan):
        reason = reason_by_index.get(i) or (
            f"Reallocation solver: move {p['quantity']} {p['category']} from "
            f"{site_names.get(p['from_site_id'])} to {site_names.get(p['to_site_id'])}."
        )
        from_name = site_names.get(p["from_site_id"], p["from_site_id"])
        to_name = site_names.get(p["to_site_id"], p["to_site_id"])
        print(f"  {p['quantity']} {p['category']}: {from_name} -> {to_name}  ({reason})")

        if not dry_run:
            post_recommendation(p["from_site_id"], p["to_site_id"], p["category"], p["quantity"], reason)

    if explanation.get("faq"):
        print("\nFAQ:")
        for item in explanation["faq"]:
            print(f"  Q: {item['question']}\n  A: {item['answer']}")

    if dry_run:
        print("\n(dry run -- nothing posted to /recommendations)")
    else:
        print(f"\nPosted {len(plan)} recommendation(s) to {LEDGER_URL}/recommendations")


# --------------------------------------------------------------- Toy demo


def demo() -> None:
    """Toy run on hardcoded data: sites 1 and 4 have spare canned goods, 3 is short."""
    surplus = {1: 150, 4: 200}
    shortage = {3: 180}
    cost = {(1, 3): 75.0, (4, 3): 105.0}

    print("Toy transportation solve (canned_goods):")
    for src, dst, quantity in solve_transfers(surplus, shortage, cost):
        print(f"  move {quantity} units from site {src} to site {dst}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ReliefLink reallocation agent")
    parser.add_argument("--live", action="store_true", help="Run against the real ledger instead of the toy demo")
    parser.add_argument("--dry-run", action="store_true", help="Compute the plan but don't POST it")
    parser.add_argument("--no-explain", action="store_true", help="Skip the Claude explanation call")
    args = parser.parse_args()

    if args.live:
        run_live(dry_run=args.dry_run, explain=not args.no_explain)
    else:
        demo()