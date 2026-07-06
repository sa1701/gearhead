"""GEARHEAD web app (Step 5): FastAPI backend + car-dashboard UI.

Run from the project root:  python run_app.py
Then open http://127.0.0.1:8000
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..brain.interview import DiagnosisSession
from ..config import settings
from ..library.images import illustrate

app = FastAPI(title="GEARHEAD")

STATIC = Path(__file__).parent / "static"
SESSIONS: dict[str, DiagnosisSession] = {}

# Ensure the rendered-image folder exists before we mount it as static.
settings.images_dir.mkdir(parents=True, exist_ok=True)

CARS = [{"id": "nissan-patrol-y61", "name": "Nissan Patrol Y61 (GU) 1997–2010"}]


class StartReq(BaseModel):
    problem: str
    car: str = "nissan-patrol-y61"


class AnswerReq(BaseModel):
    session_id: str
    answer: str


class SessionReq(BaseModel):
    session_id: str


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/cars")
def cars():
    return CARS


@app.get("/api/status")
def status():
    """Which brain is loaded — the UI shows this as the 'engine' badge."""
    provider = settings.resolved_provider()
    model = settings.ollama_model if provider == "ollama" else settings.model
    return {"provider": provider, "model": model, "local": provider == "ollama"}


@app.post("/api/start")
def start(req: StartReq):
    if not req.problem.strip():
        raise HTTPException(400, "Describe the problem first.")
    session = DiagnosisSession(req.problem.strip(), car=req.car)
    sid = uuid.uuid4().hex
    SESSIONS[sid] = session
    step = session.start()
    step["session_id"] = sid
    step["sections"] = len(session.sources())  # for the SOURCES mini-readout
    return step


@app.post("/api/answer")
def answer(req: AnswerReq):
    session = SESSIONS.get(req.session_id)
    if session is None:
        raise HTTPException(404, "Session not found — start a new diagnosis.")
    return session.answer(req.answer.strip())


@app.post("/api/illustrate")
def illustrate_endpoint(req: SessionReq):
    session = SESSIONS.get(req.session_id)
    if session is None:
        raise HTTPException(404, "Session not found.")
    res = illustrate(session.problem, session.hits, subdir=session.car, max_images=2)
    return {
        "images": [f"/page_images/{Path(p).name}" for p in res["images"]],
        "captions": res["captions"],
    }


app.mount("/page_images", StaticFiles(directory=str(settings.images_dir)), name="page_images")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
