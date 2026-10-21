"""Loopback-only UI. Credentials never enter HTTP requests or responses."""
from __future__ import annotations
from collections import deque
from pathlib import Path
from queue import Queue
from threading import Lock
from time import strftime
import secrets
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

STATIC = Path(__file__).resolve().parent / "static"
app = FastAPI(title="KeyForMe Local Control",docs_url=None,redoc_url=None,openapi_url=None)
app.add_middleware(TrustedHostMiddleware,allowed_hosts=["127.0.0.1", "localhost"])
app.mount("/static", StaticFiles(directory=STATIC), name="static")
commands: Queue[str] = Queue(maxsize=1)
token = secrets.token_urlsafe(32)
_lock = Lock()
_state = {"status":"Ready", "busy":False, "key_configured":False, "report_type":"—", "units":None, "warnings":0}
_logs = deque(maxlen=250)


@app.middleware("http")
async def local_security(request: Request, call_next):
    # Block cross-origin browser calls, including requests from eCrash tabs.
    origin = request.headers.get("origin")
    if origin and origin != f"{request.url.scheme}://{request.headers.get('host', '')}":
        return JSONResponse({"detail":"Cross-origin requests blocked"},status_code=403)
    if request.headers.get("sec-fetch-site") == "cross-site":
        return JSONResponse({"detail":"Cross-site requests blocked"},status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


def log(message: str, level: str = "info") -> None:
    with _lock:
        _logs.append({"time":strftime("%H:%M:%S"),"level":level,"message":message})


def update(**kwargs):
    with _lock:
        _state.update(kwargs)


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def state():
    with _lock:
        return {**_state,"logs":list(_logs),"token":token}


def _queue(command, supplied):
    if not secrets.compare_digest(supplied, token):
        raise HTTPException(403,"Invalid request token")
    with _lock:
        if _state["busy"] or commands.full():
            raise HTTPException(409,"An operation is already running or queued")
        if command == "extract" and not _state["key_configured"]:
            raise HTTPException(409,"Open API Settings and configure your key first")
        commands.put_nowait(command)
        _state.update(busy=True,status="Queued" if command == "extract" else "Opening native settings")
    log("Extract requested" if command == "extract" else "Opening native API settings")
    return {"queued":True}


@app.post("/api/extract")
def extract(x_keyforme_token: str = Header(default="")):
    return _queue("extract",x_keyforme_token)


@app.post("/api/settings")
def settings(x_keyforme_token: str = Header(default="")):
    # No key field: the main thread opens a native Windows dialog.
    return _queue("settings",x_keyforme_token)
