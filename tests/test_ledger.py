"""Smoke tests for the ledger API. Run with: pytest

Vivaan + Akul: add a test here for every endpoint you build (see ledger/README.md).
"""

import os
import tempfile

# Point the ledger at a throwaway database BEFORE importing the app.
os.environ["LEDGER_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402

from ledger.main import app  # noqa: E402

client = TestClient(app)


def make_site() -> dict:
    response = client.post(
        "/sites",
        json={
            "name": "Test Pantry",
            "county": "Alameda",
            "state": "CA",
            "lat": 37.8,
            "lon": -122.27,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "canned_goods" in response.json()["categories"]


def test_snapshot_then_inventory():
    site = make_site()
    response = client.post(
        "/snapshots",
        json={
            "site_id": site["id"],
            "category": "canned_goods",
            "count": 42,
            "confidence": 0.9,
            "source": "test",
        },
    )
    assert response.status_code == 201

    inventory = client.get("/inventory", params={"site_id": site["id"]}).json()
    assert len(inventory) == 1
    assert inventory[0]["count"] == 42


def test_inventory_returns_latest_snapshot():
    site = make_site()
    for count in (10, 99):
        client.post(
            "/snapshots",
            json={
                "site_id": site["id"],
                "category": "produce",
                "count": count,
                "confidence": 1.0,
                "source": "test",
            },
        )
    inventory = client.get("/inventory", params={"site_id": site["id"]}).json()
    assert inventory[0]["count"] == 99


def test_snapshot_rejects_bad_category():
    site = make_site()
    response = client.post(
        "/snapshots",
        json={"site_id": site["id"], "category": "weapons", "count": 1},
    )
    assert response.status_code == 422


def test_snapshot_rejects_unknown_site():
    response = client.post(
        "/snapshots",
        json={"site_id": 99999, "category": "dairy", "count": 5},
    )
    assert response.status_code == 404


def test_forecast_flow():
    site = make_site()
    response = client.post(
        "/forecasts",
        json={
            "site_id": site["id"],
            "category": "dry_goods",
            "predicted_demand": 200,
            "multiplier": 2.0,
            "horizon_hours": 48,
            "reason": "test storm",
            "source": "synthetic",
        },
    )
    assert response.status_code == 201

    forecasts = client.get("/forecasts", params={"site_id": site["id"]}).json()
    assert forecasts[0]["predicted_demand"] == 200
    assert forecasts[0]["multiplier"] == 2.0

def test_gaps_computes_shortage():
    site = make_site()
    client.post(
        "/snapshots",
        json={
            "site_id": site["id"],
            "category": "canned_goods",
            "count": 60,
            "confidence": 0.9,
            "source": "test",
        },
    )
    client.post(
        "/forecasts",
        json={
            "site_id": site["id"],
            "category": "canned_goods",
            "predicted_demand": 480,
            "multiplier": 2.0,
            "horizon_hours": 48,
            "reason": "test storm",
            "source": "synthetic",
        },
    )

    gaps = client.get("/gaps").json()
    site_gap = next(g for g in gaps if g["site_id"] == site["id"] and g["category"] == "canned_goods")
    assert site_gap["current"] == 60
    assert site_gap["predicted_demand"] == 480
    assert site_gap["gap"] == 420


def test_gaps_skips_pairs_with_no_inventory():
    site = make_site()
    client.post(
        "/forecasts",
        json={
            "site_id": site["id"],
            "category": "dairy",
            "predicted_demand": 100,
            "multiplier": 1.5,
            "horizon_hours": 24,
            "reason": "test",
            "source": "synthetic",
        },
    )
    gaps = client.get("/gaps").json()
    matching = [g for g in gaps if g["site_id"] == site["id"] and g["category"] == "dairy"]
    assert matching == []


def test_recommendation_flow():
    from_site = make_site()
    to_site = make_site()
    response = client.post(
        "/recommendations",
        json={
            "from_site_id": from_site["id"],
            "to_site_id": to_site["id"],
            "category": "canned_goods",
            "quantity": 150,
            "reason": "test transfer",
        },
    )
    assert response.status_code == 201
    rec = response.json()
    assert rec["status"] == "proposed"

    approved = client.post(f"/recommendations/{rec['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


def test_recommendation_rejects_unknown_site():
    site = make_site()
    response = client.post(
        "/recommendations",
        json={
            "from_site_id": 99999,
            "to_site_id": site["id"],
            "category": "canned_goods",
            "quantity": 10,
            "reason": "test",
        },
    )
    assert response.status_code == 404


def test_recommendation_rejects_bad_category():
    from_site = make_site()
    to_site = make_site()
    response = client.post(
        "/recommendations",
        json={
            "from_site_id": from_site["id"],
            "to_site_id": to_site["id"],
            "category": "weapons",
            "quantity": 10,
            "reason": "test",
        },
    )
    assert response.status_code == 422


def test_approve_rejects_unknown_recommendation():
    response = client.post("/recommendations/99999/approve")
    assert response.status_code == 404
