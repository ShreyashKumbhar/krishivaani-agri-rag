"""Evaluation dashboard API."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from .. import db
from ..config import settings
from ..services.container import AppContainer
from ..services.evaluation import load_dataset, run_evaluation
from .deps import get_services, require_admin

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("/cases")
def cases() -> dict[str, Any]:
    return load_dataset()


@router.get("/runs")
def runs(limit: int = Query(20, ge=1, le=100), services: AppContainer = Depends(get_services)) -> dict[str, Any]:
    return {"items": db.list_eval_runs(limit=limit)}


@router.get("/latest")
def latest(services: AppContainer = Depends(get_services)) -> dict[str, Any]:
    runs = db.list_eval_runs(limit=1)
    if not runs:
        return {"run": None}
    run = db.get_eval_run(runs[0]["id"])
    return {"run": run}


@router.get("/runs/{run_id}")
def run_detail(run_id: str, services: AppContainer = Depends(get_services)) -> dict[str, Any]:
    run = db.get_eval_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return run


@router.post("/run")
def run(
    admin_user: str = Depends(require_admin),
    services: AppContainer = Depends(get_services),
) -> dict[str, Any]:
    try:
        return run_evaluation(services.pipeline, save=True, write_report=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {type(exc).__name__}: {exc}") from exc


@router.get("/report")
def report(services: AppContainer = Depends(get_services)) -> FileResponse:
    path = Path(settings.docs_dir) / "EVALUATION_REPORT.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No evaluation report has been generated yet")
    return FileResponse(path, media_type="text/markdown", filename="EVALUATION_REPORT.md")


@router.get("/results.json")
def results_json(services: AppContainer = Depends(get_services)) -> FileResponse:
    path = Path(settings.docs_dir) / "evaluation_latest.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No evaluation results have been generated yet")
    return FileResponse(path, media_type="application/json", filename="evaluation_latest.json")
