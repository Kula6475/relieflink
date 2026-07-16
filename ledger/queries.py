"""Shared read queries used by the API endpoints and the spreadsheet export."""

from sqlmodel import Session, select

from ledger.models import DemandForecast, InventorySnapshot


def latest_snapshots(session: Session, site_id: int | None = None) -> list[InventorySnapshot]:
    """Newest snapshot per (site, category) = current inventory."""
    query = select(InventorySnapshot).order_by(InventorySnapshot.created_at.desc())  # type: ignore[attr-defined]
    if site_id is not None:
        query = query.where(InventorySnapshot.site_id == site_id)
    latest: dict[tuple[int, str], InventorySnapshot] = {}
    for snap in session.exec(query):
        latest.setdefault((snap.site_id, snap.category), snap)
    return list(latest.values())


def latest_forecasts(session: Session, site_id: int | None = None) -> list[DemandForecast]:
    """Newest forecast per (site, category)."""
    query = select(DemandForecast).order_by(DemandForecast.created_at.desc())  # type: ignore[attr-defined]
    if site_id is not None:
        query = query.where(DemandForecast.site_id == site_id)
    latest: dict[tuple[int, str], DemandForecast] = {}
    for forecast in session.exec(query):
        latest.setdefault((forecast.site_id, forecast.category), forecast)
    return list(latest.values())


def compute_gaps(session: Session) -> list[dict]:
    """gap = predicted_demand - current count, for pairs that have both numbers.

    Positive gap = shortage, negative gap = surplus.
    """
    current = {(s.site_id, s.category): s.count for s in latest_snapshots(session)}
    gaps = []
    for forecast in latest_forecasts(session):
        key = (forecast.site_id, forecast.category)
        if key in current:
            gaps.append(
                {
                    "site_id": forecast.site_id,
                    "category": forecast.category,
                    "current": current[key],
                    "predicted_demand": forecast.predicted_demand,
                    "gap": forecast.predicted_demand - current[key],
                }
            )
    return gaps
