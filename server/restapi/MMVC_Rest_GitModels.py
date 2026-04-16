import os
import uuid
import asyncio
from typing import List
from fastapi import APIRouter
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
import urllib.request
import urllib.error
import json
from const import getFrontendPath

CATALOG_URL = "https://raw.githubusercontent.com/arabdogwater/realtime-voicechanger-cloud-gpu/main/models/catalog.json"
ALLOWED_DOMAINS = ("huggingface.co", "raw.githubusercontent.com")

# job_id -> { status, progress, current_file, error }
_jobs: dict[str, dict] = {}


class InstallRequest(BaseModel):
    model_ids: List[str]


def _get_model_dir() -> str:
    return os.environ.get("MODEL_DIR", os.path.join(os.getcwd(), "model_dir"))


def _fetch_catalog() -> list:
    with urllib.request.urlopen(CATALOG_URL, timeout=10) as r:
        return json.loads(r.read().decode())


def _installed_ids(model_dir: str) -> set[str]:
    installed = set()
    try:
        for entry in os.scandir(model_dir):
            if entry.is_dir():
                installed.add(entry.name)
    except FileNotFoundError:
        pass
    return installed


def _validate_url(url: str):
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.hostname not in ALLOWED_DOMAINS:
        raise ValueError(f"URL domain not allowed: {parsed.hostname}")


async def _download_model(job_id: str, model: dict, model_dir: str):
    _jobs[job_id] = {"status": "downloading", "progress": 0.0, "current_file": "", "error": None}
    dest_dir = os.path.join(model_dir, model["id"])
    os.makedirs(dest_dir, exist_ok=True)
    files = model.get("files", [])
    try:
        for i, f in enumerate(files):
            url = f["url"]
            filename = f["filename"]
            _validate_url(url)
            dest = os.path.join(dest_dir, filename)
            _jobs[job_id]["current_file"] = filename
            _jobs[job_id]["progress"] = i / max(len(files), 1)
            await asyncio.get_event_loop().run_in_executor(
                None, lambda u=url, d=dest: urllib.request.urlretrieve(u, d)
            )
        _jobs[job_id]["status"] = "done"
        _jobs[job_id]["progress"] = 1.0
        _jobs[job_id]["current_file"] = ""
    except Exception as e:
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(e)


router = APIRouter()


@router.get("/git-models")
async def git_models_page():
    html_path = os.path.join(getFrontendPath(), "git-models.html")
    return FileResponse(html_path, media_type="text/html")


@router.get("/api/git-models/available")
async def get_available():
    try:
        catalog = _fetch_catalog()
    except Exception as e:
        return JSONResponse({"error": f"Failed to fetch catalog: {e}"}, status_code=502)
    model_dir = _get_model_dir()
    installed = _installed_ids(model_dir)
    available = []
    for m in catalog:
        available.append({
            **m,
            "installed": m["id"] in installed,
        })
    return {"models": available, "installed": list(installed)}


@router.post("/api/git-models/install")
async def install_models(req: InstallRequest):
    try:
        catalog = _fetch_catalog()
    except Exception as e:
        return JSONResponse({"error": f"Failed to fetch catalog: {e}"}, status_code=502)
    catalog_by_id = {m["id"]: m for m in catalog}
    model_dir = _get_model_dir()
    job_ids = []
    for model_id in req.model_ids:
        if model_id not in catalog_by_id:
            return JSONResponse({"error": f"Unknown model id: {model_id}"}, status_code=400)
        job_id = str(uuid.uuid4())
        job_ids.append({"model_id": model_id, "job_id": job_id})
        asyncio.create_task(_download_model(job_id, catalog_by_id[model_id], model_dir))
    return {"jobs": job_ids}


@router.get("/api/git-models/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in _jobs:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    return {"job_id": job_id, **_jobs[job_id]}
