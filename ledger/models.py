"""Database tables for the shared ledger.

Owners: Vivaan + Akul. Every other section reads/writes these through the API,
never by touching the database directly.
"""

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Site(SQLModel, table=True):
    """A food bank / pantry location."""

    id: int | None = Field(default=None, primary_key=True)
    name: str
    county: str
    state: str = "CA"
    lat: float
    lon: float


class InventorySnapshot(SQLModel, table=True):
    """One camera (or manual) count of one category at one site.

    The vision agent posts these. 'Latest snapshot per (site, category)' is the
    current inventory, served by GET /inventory.
    """

    id: int | None = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id", index=True)
    category: str = Field(index=True)
    count: int
    confidence: float = 1.0
    source: str = "manual"  # "vision" | "fake" | "manual" | "test"
    created_at: datetime = Field(default_factory=utcnow)


class DemandForecast(SQLModel, table=True):
    """Predicted demand for one category at one site over the next horizon_hours.

    The disruption agent posts these based on weather alerts and FEMA declarations.
    """

    id: int | None = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id", index=True)
    category: str = Field(index=True)
    predicted_demand: int
    multiplier: float = 1.0  # demand spike factor vs the normal baseline
    horizon_hours: int = 48
    reason: str = ""  # e.g. "Severe Winter Storm Warning covering Alameda County"
    source: str = "weather.gov"  # "weather.gov" | "openfema" | "synthetic"
    created_at: datetime = Field(default_factory=utcnow)


class AgencyCapacity(SQLModel, table=True):
    """Transport capacity available at a site (for the Phase 2 optimizer)."""

    id: int | None = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id", index=True)
    trucks: int = 1
    max_load_units: int = 300  # items one truck can move in one trip


class Route(SQLModel, table=True):
    """Distance between two sites. Stored once per pair, treat as symmetric."""

    id: int | None = Field(default=None, primary_key=True)
    from_site_id: int = Field(foreign_key="site.id")
    to_site_id: int = Field(foreign_key="site.id")
    miles: float
    drive_minutes: int


class Recommendation(SQLModel, table=True):
    """A proposed transfer from the Phase 2 reallocation agent."""

    id: int | None = Field(default=None, primary_key=True)
    from_site_id: int = Field(foreign_key="site.id")
    to_site_id: int = Field(foreign_key="site.id")
    category: str
    quantity: int
    reason: str = ""
    status: str = "proposed"  # "proposed" | "approved" | "dispatched"
    created_at: datetime = Field(default_factory=utcnow)
