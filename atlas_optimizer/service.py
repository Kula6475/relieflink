"""Deterministic minimum-cost allocation over validated offers."""

from typing import Literal

from ortools.linear_solver import pywraplp
from pydantic import BaseModel, Field


class AllocationSource(BaseModel):
    source_id: str
    source_type: Literal["site", "vendor"]
    organization_id: str
    available_quantity: int = Field(ge=0)
    capacity_quantity: int = Field(ge=0)
    distance_miles: float = Field(ge=0)
    earliest_pickup: str
    refrigerated: bool = False


class AtlasOptimizationRequest(BaseModel):
    requested_quantity: int = Field(ge=0)
    sources: list[AllocationSource]


def solve_allocation(request: AtlasOptimizationRequest) -> dict:
    """Fill as much demand as possible, then minimize distance-weighted units."""
    solver = pywraplp.Solver.CreateSolver("GLOP")
    if solver is None:
        raise RuntimeError("OR-Tools GLOP solver is unavailable")
    moves = {
        source.source_id: solver.NumVar(
            0,
            min(source.available_quantity, source.capacity_quantity),
            f"move_{source.source_id}",
        )
        for source in request.sources
    }
    solver.Add(sum(moves.values()) <= request.requested_quantity)
    # A large fulfillment reward makes unmet demand more expensive than any route.
    solver.Minimize(
        sum(
            (source.distance_miles - 10_000) * moves[source.source_id]
            for source in request.sources
        )
    )
    if solver.Solve() != pywraplp.Solver.OPTIMAL:
        return {"allocations": [], "unfilled_quantity": request.requested_quantity}
    allocations = []
    filled = 0
    for source in request.sources:
        quantity = round(moves[source.source_id].solution_value())
        if quantity <= 0:
            continue
        filled += quantity
        allocations.append(
            {
                **source.model_dump(),
                "quantity": quantity,
                "estimated_cost": quantity * source.distance_miles,
            }
        )
    return {
        "allocations": allocations,
        "unfilled_quantity": max(0, request.requested_quantity - filled),
    }
