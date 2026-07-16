from atlas_optimizer.service import AtlasOptimizationRequest, solve_allocation


def test_atlas_optimizer_fills_lowest_cost_feasible_sources():
    request = AtlasOptimizationRequest(
        requested_quantity=150,
        sources=[
            {
                "source_id": "oakland",
                "source_type": "site",
                "organization_id": "oakland_org",
                "available_quantity": 100,
                "capacity_quantity": 100,
                "distance_miles": 28,
                "earliest_pickup": "2026-07-17T15:00:00Z",
            },
            {
                "source_id": "vendor",
                "source_type": "vendor",
                "organization_id": "vendor_org",
                "available_quantity": 80,
                "capacity_quantity": 80,
                "distance_miles": 35,
                "earliest_pickup": "2026-07-17T16:00:00Z",
            },
        ],
    )
    result = solve_allocation(request)
    assert result["unfilled_quantity"] == 0
    assert [(row["source_id"], row["quantity"]) for row in result["allocations"]] == [
        ("oakland", 100),
        ("vendor", 50),
    ]
