from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from celery.result import AsyncResult
from fastapi import FastAPI, HTTPException

from shared.votenow_common.settings import Settings

from .tasks import celery_app, export_root, generate_excel_report, generate_pdf_report

settings = Settings(service_name="export-service", service_port=8505)
app = FastAPI(title="VoteNow Export Service", version="1.0.0")


async def _get_json(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url)
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/exports/{survey_id}/excel")
async def export_excel(survey_id: str) -> dict[str, str]:
    tables = await _get_json(f"{settings.analytics_service_url}/analytics/{survey_id}/tables")
    task = generate_excel_report.delay(survey_id, tables)
    return {"task_id": task.id, "format": "excel"}


@app.post("/exports/{survey_id}/pdf")
async def export_pdf(survey_id: str) -> dict[str, str]:
    tables = await _get_json(f"{settings.analytics_service_url}/analytics/{survey_id}/tables")
    task = generate_pdf_report.delay(survey_id, tables)
    return {"task_id": task.id, "format": "pdf"}


@app.get("/exports/tasks/{task_id}")
async def task_status(task_id: str) -> dict[str, Any]:
    result = AsyncResult(task_id, app=celery_app)
    payload: dict[str, Any] = {"task_id": task_id, "status": result.status}
    if result.ready() and result.successful():
        payload["result"] = result.result
    if result.failed():
        payload["error"] = str(result.result)
    return payload


@app.get("/exports/files")
async def list_files() -> dict[str, Any]:
    items = []
    if Path(export_root).exists():
        items = sorted([entry.name for entry in Path(export_root).glob("*") if entry.is_file()])
    return {"items": items, "count": len(items)}
