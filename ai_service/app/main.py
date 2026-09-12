from __future__ import annotations

import asyncio
import contextlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .repository import IntelligenceRepository


ROOT = Path(os.getenv("DEIMOS_ROOT", Path(__file__).resolve().parents[2])).resolve()
repository = IntelligenceRepository(ROOT)


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
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
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
async def profiles() -> dict[str, Any]:
    rows = await asyncio.to_thread(repository.profiles)
    return {"profiles": rows, "count": len(rows)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin", "")
    if origin and not origin.startswith(("http://localhost:", "http://127.0.0.1:")):
        await websocket.close(code=1008)
        return
    await stream.connect(websocket)
    await stream.publish("connection", "Frontend connected to Python intelligence service", "success")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await stream.disconnect(websocket)
