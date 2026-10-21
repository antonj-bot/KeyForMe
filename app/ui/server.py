"""Local-only UI. HTTP thread never touches Playwright objects."""
from __future__ import annotations

from collections import deque
from pathlib import Path
from queue import Queue
from threading import Lock
from time import strftime
import secrets

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC = Path(__file__).resolve().parent / "static"
app = FastAPI(title="KeyForMe Local Control", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
commands: Queue[str] = Queue(maxsize=1)
token = secrets.token_urlsafe(32)
_lock = Lock()
_state = {"status": "Ready", "busy": False, "report_type": "—", "units": None, "warnings": 0}
_logs = deque(maxlen=250)


def log(message: str, level: str = "info") -> None:
    # Only pass operational messages. Never pass report content, credentials or full URLs.
    with _lock:
        _logs.append({"time": strftime("%H:%M:%S"), "level": level, "message": message})


def update(**kwargs) -> None:
    with _lock:
        _state.update(kwargs)


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/state")
def state():
    with _lock:
        return {**_state, "logs": list(_logs), "token": token}


@app.post("/api/extract")
def extract(x_keyforme_token: str = Header(default="")):
    if not secrets.compare_digest(x_keyforme_token, token):
        raise HTTPException(403, "Invalid request token")
    with _lock:
        if _state["busy"]:
            raise HTTPException(409, "An extraction is already running")
        if commands.full():
            raise HTTPException(409, "An extraction is already queued")
        commands.put_nowait("extract")
        _state["busy"] = True
        _state["status"] = "Queued"
        _logs.append({"time": strftime("%H:%M:%S"), "level": "info", "message": "Extract requested"})
    return {"queued": True}
