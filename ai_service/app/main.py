from __future__ import annotations

import asyncio
import contextlib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .repository import IntelligenceRepository


ROOT = Path(os.getenv("DEIMOS_ROOT", Path(__file__).resolve().parents[2])).resolve()
repository = IntelligenceRepository(ROOT)
ALLOWED_ORIGINS = {origin.strip() for origin in os.getenv("DEIMOS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://10.12.13.8:3000").split(",") if origin.strip()}


class WorkspaceAnalysisRequest(BaseModel):
    profile_ids: list[int] = Field(default_factory=list, max_length=12)
    page_url: str = Field(default="", max_length=2048)
    depth: int = Field(default=2, ge=1, le=4)
    max_activities: int = Field(default=12, ge=2, le=30)


class EventStream:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self.lock:
            self.connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self.lock:
            self.connections.discard(websocket)

    async def publish(self, event_type: str, message: str, level: str = "info", data: dict[str, Any] | None = None) -> None:
        payload = {
            "type": event_type,
            "source": "python",
            "message": message,
            "level": level,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data or {},
        }
        async with self.lock:
            targets = list(self.connections)
        failed: list[WebSocket] = []
        for websocket in targets:
            try:
                await websocket.send_json(payload)
            except Exception:
                failed.append(websocket)
        if failed:
            async with self.lock:
                for websocket in failed:
                    self.connections.discard(websocket)


stream = EventStream()


async def monitor_analysis() -> None:
    previous: dict[str, int] | None = None
    while True:
        try:
            current = await asyncio.to_thread(repository.stats)
            if previous is not None and current != previous:
                await stream.publish("analysis.updated", "Intelligence database updated", "success", current)
            previous = current
        except Exception as error:
            await stream.publish("analysis.error", f"Analysis database unavailable: {error}", "warning")
        await asyncio.sleep(8)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(monitor_analysis())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="DEIMOS Intelligence Service", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With"],
)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "deimos-python-intelligence",
        "legacy_root": str(ROOT / "phobos"),
    }


@app.get("/api/stats")
async def stats() -> dict[str, int]:
    return await asyncio.to_thread(repository.stats)


@app.get("/api/stats/{engine}")
async def engine_stats(engine: str) -> dict[str, int]:
    return await asyncio.to_thread(repository.stats, engine)


@app.get("/api/reports")
async def reports(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    rows = await asyncio.to_thread(repository.reports, limit)
    return {"reports": rows, "count": len(rows)}


@app.get("/api/entities")
async def entities(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    rows = await asyncio.to_thread(repository.entities, limit)
    return {"entities": rows, "count": len(rows)}


@app.get("/api/profiles")
async def profiles(limit: int = Query(default=100, ge=1, le=500), q: str = "") -> dict[str, Any]:
    rows, total = await asyncio.gather(
        asyncio.to_thread(repository.profiles, limit, q),
        asyncio.to_thread(repository.profile_count),
    )
    return {"profiles": rows, "count": total}


@app.get("/api/profiles/{profile_id}")
async def profile(profile_id: int) -> dict[str, Any]:
    row = await asyncio.to_thread(repository.profile, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return row


@app.delete("/api/profiles")
async def clear_profiles(confirmation: str = Query(default="")) -> dict[str, Any]:
    if confirmation != "CLEAR":
        raise HTTPException(status_code=400, detail="confirmation=CLEAR is required")
    count = await asyncio.to_thread(repository.clear_profiles)
    return {"message": f"Cleared {count} profile records", "count": count}


@app.post("/api/profiles/reanalyze/{engine}")
async def reanalyze_profiles(engine: str) -> dict[str, Any]:
    if engine not in {"crawler", "phobos-search"}:
        raise HTTPException(status_code=404, detail="Unknown database engine")
    try:
        await asyncio.to_thread(repository.request_profile_rescan, engine)
    except sqlite3.DatabaseError as error:
        raise HTTPException(status_code=409, detail=f"Profile database is not ready: {error}") from error
    return {"message": f"Profile reanalysis queued for {engine}", "engine": engine}


@app.post("/api/workspace/analyze")
async def analyze_workspace(request: WorkspaceAnalysisRequest) -> dict[str, Any]:
    if not request.profile_ids and not request.page_url.strip():
        raise HTTPException(status_code=400, detail="Select a profile or provide an indexed page URL")
    try:
        graph = await asyncio.to_thread(
            repository.workspace_graph,
            request.profile_ids,
            request.page_url.strip(),
            request.depth,
            request.max_activities,
        )
    except sqlite3.DatabaseError as error:
        raise HTTPException(status_code=409, detail=f"Workspace intelligence databases are busy: {error}") from error
    if not graph["roots"]:
        raise HTTPException(status_code=404, detail="No selected profile or indexed website was found")
    await stream.publish(
        "workspace.analyzed",
        f"Workspace generated {len(graph['nodes'])} nodes and {len(graph['edges'])} links",
        "success",
        {"nodes": len(graph["nodes"]), "edges": len(graph["edges"]), "depth": graph["depth"]},
    )
    return graph


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin", "")
    if origin and origin not in ALLOWED_ORIGINS:
        await websocket.close(code=1008)
        return
    await stream.connect(websocket)
    await stream.publish("connection", "Frontend connected to Python intelligence service", "success")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await stream.disconnect(websocket)
