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
