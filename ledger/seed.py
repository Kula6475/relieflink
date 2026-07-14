"""Seed the ledger with 4 demo sites, starting inventory, capacity, and routes.

Run from the repo root:
    python -m ledger.seed

Safe to re-run: it wipes and recreates all tables first.
"""

from sqlmodel import Session, SQLModel

from ledger.database import engine
from ledger.models import AgencyCapacity, InventorySnapshot, Route, Site
from shared.config import CATEGORIES

SITES = [
    Site(name="Oakland Community Food Bank", county="Alameda", lat=37.8044, lon=-122.2712),
    Site(name="San Jose Family Pantry", county="Santa Clara", lat=37.3382, lon=-121.8863),
    Site(name="Santa Cruz Coastal Pantry", county="Santa Cruz", lat=36.9741, lon=-122.0308),
    Site(name="Stockton Valley Depot", county="San Joaquin", lat=37.9577, lon=-121.2908),
]

# Starting counts per site (same order as SITES) and category (same order as CATEGORIES).
STARTING_COUNTS = [
    [340, 120, 80, 260],  # Oakland: well stocked
    [180, 90, 55, 140],  # San Jose: medium
    [60, 25, 10, 45],  # Santa Cruz: running low
    [420, 60, 30, 380],  # Stockton: big dry-goods depot
]

CAPACITY = [(1, 3, 400), (2, 2, 300), (3, 1, 200), (4, 3, 500)]  # (site_id, trucks, max load)

# (from_site_id, to_site_id, miles, drive_minutes). Symmetric, stored once per pair.
ROUTES = [
    (1, 2, 40, 50),
    (1, 3, 75, 90),
    (1, 4, 83, 95),
    (2, 3, 32, 45),
    (2, 4, 78, 90),
    (3, 4, 105, 120),
]


def seed() -> None:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        for site in SITES:
            session.add(site)
        session.commit()

        for site_index, counts in enumerate(STARTING_COUNTS):
            for category, count in zip(CATEGORIES, counts):
                session.add(
                    InventorySnapshot(
                        site_id=site_index + 1,
                        category=category,
                        count=count,
                        confidence=1.0,
                        source="manual",
                    )
                )

        for site_id, trucks, max_load in CAPACITY:
            session.add(AgencyCapacity(site_id=site_id, trucks=trucks, max_load_units=max_load))

        for from_id, to_id, miles, minutes in ROUTES:
            session.add(
                Route(from_site_id=from_id, to_site_id=to_id, miles=miles, drive_minutes=minutes)
            )

        session.commit()

    print(
        f"Seeded {len(SITES)} sites, {len(SITES) * len(CATEGORIES)} snapshots, "
        f"{len(CAPACITY)} capacity rows, {len(ROUTES)} routes into relief.db"
    )


if __name__ == "__main__":
    seed()
