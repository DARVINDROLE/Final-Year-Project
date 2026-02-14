from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .models import AiReplyRequest, RingEvent
from .orchestrator import Orchestrator

load_dotenv()  # load .env before anything reads os.getenv

app = FastAPI(title="Smart Doorbell API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_orchestrator() -> Orchestrator:
    db_path = os.getenv("DOORBELL_DB_PATH", "data/db.sqlite")
    orchestrator = Orchestrator(db_path=db_path)
    orchestrator.initialize()
    return orchestrator


@app.on_event("startup")
async def startup_event() -> None:
    app.state.orchestrator = _build_orchestrator()


@app.get("/api/health")
async def health_check() -> dict:
    return {"status": "ok", "service": "smart-doorbell-backend"}


@app.post("/api/ring")
async def ring(payload: RingEvent) -> dict:
    return await app.state.orchestrator.handle_ring(payload)


@app.get("/api/session/{session_id}/status")
async def session_status(session_id: str) -> dict:
    return app.state.orchestrator.get_session_status(session_id)


@app.post("/api/ai-reply")
async def ai_reply(payload: AiReplyRequest) -> dict:
    return await app.state.orchestrator.handle_ai_reply(payload)


@app.get("/api/logs")
async def logs(limit: int = 50) -> dict:
    return app.state.orchestrator.get_logs(limit=limit)
