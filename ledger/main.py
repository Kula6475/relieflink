"""ReliefLink shared ledger API.

Owners: Vivaan + Akul. Your task checklist is in ledger/README.md.

Run from the repo root:
    uvicorn ledger.main:app --reload

Then open http://localhost:8000/docs for interactive docs where you can try
every endpoint in the browser.
"""

from fastapi import Depends, FastAPI, HTTPException
from sqlmodel import Session, select

from ledger.database import get_session, init_db
from ledger.models import (
    AgencyCapacity,
    DemandForecast,
    InventorySnapshot,
    Recommendation,
    Route,
    Site,
)
from shared.config import CATEGORIES

app = FastAPI(
    title="ReliefLink Ledger",
    description="Shared source of truth: sites, camera-fed inventory, demand forecasts.",
    version="0.1.0",
)

init_db()


@app.get("/")
def root():
    return {
        "service": "ReliefLink Ledger",
        "docs": "/docs",
        "categories": CATEGORIES,
    }


# ---------------------------------------------------------------- sites


@app.get("/sites")
def list_sites(session: Session = Depends(get_session)) -> list[Site]:
    return list(session.exec(select(Site)).all())


@app.post("/sites", status_code=201)
def create_site(site: Site, session: Session = Depends(get_session)) -> Site:
    site.id = None
    session.add(site)
    session.commit()
    session.refresh(site)
    return site


# ---------------------------------------------------------------- inventory


@app.post("/snapshots", status_code=201)
def create_snapshot(
    snap: InventorySnapshot, session: Session = Depends(get_session)
) -> InventorySnapshot:
    """Vision agent posts one count per (site, category) here."""
    if snap.category not in CATEGORIES:
        raise HTTPException(422, f"category must be one of {CATEGORIES}")
    if session.get(Site, snap.site_id) is None:
        raise HTTPException(404, f"site {snap.site_id} not found")
    snap.id = None
    session.add(snap)
    session.commit()
    session.refresh(snap)
    return snap


@app.get("/inventory")
def latest_inventory(
    site_id: int | None = None, session: Session = Depends(get_session)
) -> list[InventorySnapshot]:
    """Current inventory: the newest snapshot for each (site, category)."""
    query = select(InventorySnapshot).order_by(InventorySnapshot.created_at.desc())  # type: ignore[attr-defined]
    if site_id is not None:
        query = query.where(InventorySnapshot.site_id == site_id)
    latest: dict[tuple[int, str], InventorySnapshot] = {}
    for snap in session.exec(query):
        latest.setdefault((snap.site_id, snap.category), snap)
    return list(latest.values())


# ---------------------------------------------------------------- forecasts


@app.post("/forecasts", status_code=201)
def create_forecast(
    forecast: DemandForecast, session: Session = Depends(get_session)
) -> DemandForecast:
    """Disruption agent posts predicted demand per (site, category) here."""
    if forecast.category not in CATEGORIES:
        raise HTTPException(422, f"category must be one of {CATEGORIES}")
    if session.get(Site, forecast.site_id) is None:
        raise HTTPException(404, f"site {forecast.site_id} not found")
    forecast.id = None
    session.add(forecast)
    session.commit()
    session.refresh(forecast)
    return forecast


@app.get("/forecasts")
def latest_forecasts(
    site_id: int | None = None, session: Session = Depends(get_session)
) -> list[DemandForecast]:
    """The newest forecast for each (site, category)."""
    query = select(DemandForecast).order_by(DemandForecast.created_at.desc())  # type: ignore[attr-defined]
    if site_id is not None:
        query = query.where(DemandForecast.site_id == site_id)
    latest: dict[tuple[int, str], DemandForecast] = {}
    for forecast in session.exec(query):
        latest.setdefault((forecast.site_id, forecast.category), forecast)
    return list(latest.values())


# ---------------------------------------------------------------- logistics


@app.get("/capacity")
def list_capacity(session: Session = Depends(get_session)) -> list[AgencyCapacity]:
    return list(session.exec(select(AgencyCapacity)).all())


@app.get("/routes")
def list_routes(session: Session = Depends(get_session)) -> list[Route]:
    return list(session.exec(select(Route)).all())


@app.get("/recommendations")
def list_recommendations(session: Session = Depends(get_session)) -> list[Recommendation]:
    return list(session.exec(select(Recommendation)).all())


@app.get("/gaps")
def compute_gaps(session: Session = Depends(get_session)) -> list[dict]:
    """For each (site, category) with both a snapshot and a forecast,
    gap = predicted_demand - current count. Positive = shortage, negative = surplus.
    """
    inventory = latest_inventory(session=session)
    forecasts = latest_forecasts(session=session)

    current_by_key = {(s.site_id, s.category): s.count for s in inventory}
    forecast_by_key = {(f.site_id, f.category): f.predicted_demand for f in forecasts}

    gaps = []
    for key, predicted_demand in forecast_by_key.items():
        site_id, category = key
        if key not in current_by_key:
            continue
        current = current_by_key[key]
        gaps.append({
            "site_id": site_id,
            "category": category,
            "current": current,
            "predicted_demand": predicted_demand,
            "gap": predicted_demand - current,
        })
    return gaps


@app.post("/recommendations", status_code=201)
def create_recommendation(
    rec: Recommendation, session: Session = Depends(get_session)
) -> Recommendation:
    """Reallocation agent posts a proposed transfer here."""
    if rec.category not in CATEGORIES:
        raise HTTPException(422, f"category must be one of {CATEGORIES}")
    if session.get(Site, rec.from_site_id) is None:
        raise HTTPException(404, f"site {rec.from_site_id} not found")
    if session.get(Site, rec.to_site_id) is None:
        raise HTTPException(404, f"site {rec.to_site_id} not found")
    rec.id = None
    rec.status = "proposed"
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


@app.post("/recommendations/{rec_id}/approve")
def approve_recommendation(
    rec_id: int, session: Session = Depends(get_session)
) -> Recommendation:
    """Dashboard's approve button calls this. No body needed."""
    rec = session.get(Recommendation, rec_id)
    if rec is None:
        raise HTTPException(404, f"recommendation {rec_id} not found")
    rec.status = "approved"
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec
