"""ReliefLink unified server: shared ledger API + CRM dashboard + edge camera page.

One process serves everything:
    /            the React CRM dashboard (web/index.html)
    /camera      the in-browser edge YOLO detector (web/camera.html)
    /docs        interactive API docs (try every endpoint in the browser)
    /models/...  the YOLOv8n ONNX weights the camera page loads
    everything else: the JSON API (the contract in docs/api-contract.md)

Run from the repo root:
    uvicorn ledger.main:app --reload
"""

from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
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
from ledger.queries import compute_gaps, latest_forecasts, latest_snapshots
from ledger.spreadsheets import build_export, build_template, import_rows, rows_from_upload
from shared.config import CATEGORIES
from atlas_optimizer.service import AtlasOptimizationRequest, solve_allocation
from atlas_optimizer.advisor import AtlasAdvisorRequest, explain

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
MODELS_DIR = REPO_ROOT / "models"

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

app = FastAPI(
    title="ReliefLink",
    description="Shared ledger + CRM dashboard + edge camera, one server.",
    version="0.2.0",
)

# Edge cameras and dashboards may run on other devices on the LAN.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

init_db()


# ---------------------------------------------------------------- frontend


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/camera", include_in_schema=False)
def camera_page():
    return FileResponse(WEB_DIR / "camera.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
app.mount("/models", StaticFiles(directory=MODELS_DIR), name="models")


@app.get("/api")
def api_info():
    return {"service": "ReliefLink Ledger", "docs": "/docs", "categories": CATEGORIES}


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
    """Edge cameras (and spreadsheet imports) post counts here."""
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
def inventory(
    site_id: int | None = None, session: Session = Depends(get_session)
) -> list[InventorySnapshot]:
    """Current inventory: the newest snapshot for each (site, category)."""
    return latest_snapshots(session, site_id)


# ---------------------------------------------------------------- forecasts


@app.post("/forecasts", status_code=201)
def create_forecast(
    forecast: DemandForecast, session: Session = Depends(get_session)
) -> DemandForecast:
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
def forecasts(
    site_id: int | None = None, session: Session = Depends(get_session)
) -> list[DemandForecast]:
    return latest_forecasts(session, site_id)


# ---------------------------------------------------------------- gaps


@app.get("/gaps")
def gaps(session: Session = Depends(get_session)) -> list[dict]:
    """gap = predicted_demand - current, per (site, category) with both numbers.

    Positive = shortage, negative = surplus. The reallocation agent consumes this.
    """
    return compute_gaps(session)


# ---------------------------------------------------------------- logistics


@app.get("/capacity")
def list_capacity(session: Session = Depends(get_session)) -> list[AgencyCapacity]:
    return list(session.exec(select(AgencyCapacity)).all())


@app.get("/routes")
def list_routes(session: Session = Depends(get_session)) -> list[Route]:
    return list(session.exec(select(Route)).all())


@app.post("/optimizer/atlas")
def optimize_atlas(request: AtlasOptimizationRequest) -> dict:
    """Stateless OR-Tools solve for offers already validated by hosted ATLAS."""
    return solve_allocation(request)


@app.post("/atlas/advisor")
def atlas_advisor(request: AtlasAdvisorRequest) -> dict:
    """Claude explanation/follow-up node with a no-key deterministic fallback."""
    return {"answer": explain(request)}


# ---------------------------------------------------------------- recommendations


@app.get("/recommendations")
def list_recommendations(session: Session = Depends(get_session)) -> list[Recommendation]:
    return list(session.exec(select(Recommendation)).all())


@app.post("/recommendations", status_code=201)
def create_recommendation(
    rec: Recommendation, session: Session = Depends(get_session)
) -> Recommendation:
    if rec.category not in CATEGORIES:
        raise HTTPException(422, f"category must be one of {CATEGORIES}")
    for site_id in (rec.from_site_id, rec.to_site_id):
        if session.get(Site, site_id) is None:
            raise HTTPException(404, f"site {site_id} not found")
    rec.id = None
    rec.status = "proposed"
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


@app.post("/recommendations/{rec_id}/approve")
def approve_recommendation(rec_id: int, session: Session = Depends(get_session)) -> Recommendation:
    rec = session.get(Recommendation, rec_id)
    if rec is None:
        raise HTTPException(404, f"recommendation {rec_id} not found")
    rec.status = "approved"
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


# ---------------------------------------------------------------- spreadsheets


@app.post("/spreadsheets/import")
async def import_spreadsheet(
    file: UploadFile = File(...), session: Session = Depends(get_session)
) -> dict:
    """Upload a partner's .xlsx/.csv inventory sheet; rows land in the ledger.

    The response links the live export, the "new spreadsheet" that stays connected:
    every download regenerates from current ledger data.
    """
    data = await file.read()
    try:
        rows = rows_from_upload(file.filename or "upload.xlsx", data)
    except Exception as error:  # unreadable file, wrong format
        raise HTTPException(422, f"could not parse spreadsheet: {error}") from error
    if not rows:
        raise HTTPException(422, "no data rows found (need headers: site, category, count)")
    summary = import_rows(rows, session)
    summary["export_url"] = "/spreadsheets/export"
    return summary


@app.get("/spreadsheets/export")
def export_spreadsheet(session: Session = Depends(get_session)) -> Response:
    """The live-linked workbook: regenerated from the ledger on every download."""
    return Response(
        content=build_export(session),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="relieflink-live.xlsx"'},
    )


@app.get("/spreadsheets/template")
def spreadsheet_template() -> Response:
    return Response(
        content=build_template(),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="relieflink-template.xlsx"'},
    )
