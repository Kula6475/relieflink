"""Smoke tests for the ledger API. Run with: pytest"""

import os
import tempfile

# Point the ledger at a throwaway database BEFORE importing the app.
os.environ.setdefault("LEDGER_DB", os.path.join(tempfile.mkdtemp(), "test.db"))

from fastapi.testclient import TestClient  # noqa: E402

from ledger.main import app  # noqa: E402

client = TestClient(app)


def make_site(name: str = "Test Pantry") -> dict:
    response = client.post(
        "/sites",
        json={"name": name, "county": "Alameda", "state": "CA", "lat": 37.8, "lon": -122.27},
    )
    assert response.status_code == 201
    return response.json()


def test_api_info():
    response = client.get("/api")
    assert response.status_code == 200
    assert "canned_goods" in response.json()["categories"]


def test_dashboard_and_camera_pages_serve_html():
    for path in ("/", "/camera"):
        response = client.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


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
        "/snapshots", json={"site_id": site["id"], "category": "weapons", "count": 1}
    )
    assert response.status_code == 422


def test_snapshot_rejects_unknown_site():
    response = client.post("/snapshots", json={"site_id": 99999, "category": "dairy", "count": 5})
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


def test_gaps_positive_means_shortage():
    site = make_site("Gap Pantry")
    client.post(
        "/snapshots",
        json={"site_id": site["id"], "category": "canned_goods", "count": 60, "source": "test"},
    )
    client.post(
        "/forecasts",
        json={
            "site_id": site["id"],
            "category": "canned_goods",
            "predicted_demand": 480,
            "multiplier": 2.0,
            "reason": "test",
            "source": "synthetic",
        },
    )
    gaps = client.get("/gaps").json()
    row = next(g for g in gaps if g["site_id"] == site["id"] and g["category"] == "canned_goods")
    assert row["current"] == 60
    assert row["gap"] == 420


def test_gaps_skips_pairs_without_a_forecast():
    site = make_site("Snapshot Only Pantry")
    client.post(
        "/snapshots",
        json={"site_id": site["id"], "category": "dairy", "count": 10, "source": "test"},
    )
    gaps = client.get("/gaps").json()
    assert not any(g["site_id"] == site["id"] and g["category"] == "dairy" for g in gaps)


def test_gaps_skips_pairs_with_no_inventory():
    # Akul's case from PR #7: a forecast alone (no snapshot yet) must not produce a gap.
    site = make_site("Forecast Only Pantry")
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
    assert not any(g["site_id"] == site["id"] and g["category"] == "dairy" for g in gaps)


def test_recommendation_create_and_approve():
    giver, taker = make_site("Giver"), make_site("Taker")
    created = client.post(
        "/recommendations",
        json={
            "from_site_id": giver["id"],
            "to_site_id": taker["id"],
            "category": "canned_goods",
            "quantity": 50,
            "reason": "test",
        },
    )
    assert created.status_code == 201
    assert created.json()["status"] == "proposed"

    rec_id = created.json()["id"]
    approved = client.post(f"/recommendations/{rec_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


def test_recommendation_validates_sites_and_category():
    site = make_site("Lonely")
    assert (
        client.post(
            "/recommendations",
            json={
                "from_site_id": site["id"],
                "to_site_id": 99999,
                "category": "canned_goods",
                "quantity": 5,
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/recommendations",
            json={
                "from_site_id": site["id"],
                "to_site_id": site["id"],
                "category": "gold",
                "quantity": 5,
            },
        ).status_code
        == 422
    )
    assert client.post("/recommendations/99999/approve").status_code == 404
