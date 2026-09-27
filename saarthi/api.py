"""SAARTHI prototype server: FastAPI over saarthi.service.

The endpoint logic lives in service.py (standard library only) so the exact same
code also runs in the browser for the static GitHub Pages demo.

Run:  py -m uvicorn saarthi.api:app --port 8026
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import service as S
from .config import WEB

app = FastAPI(title="SAARTHI prototype", docs_url="/api/docs")


def call(fn, **kw):
    try:
        return JSONResponse(S.clean(fn(**kw)))
    except S.NotFound as e:
        raise HTTPException(404, str(e))


@app.get("/api/meta")
def meta():
    return call(S.meta)


@app.get("/api/state")
def state(date: str, t: float):
    return call(S.state, date=date, t=t)


@app.get("/api/train")
def train(date: str, tid: int, t: float):
    return call(S.train, date=date, tid=tid, t=t)


@app.get("/api/station")
def station(date: str, code: str, t: float):
    return call(S.station, date=date, code=code, t=t)


@app.get("/api/passenger")
def passenger(date: str, t: float, tid: int, code: str, role: str = "board", travel: int = 30):
    return call(S.passenger, date=date, t=t, tid=tid, code=code, role=role, travel=travel)


@app.get("/api/messages")
def messages(date: str, t: float, tid: int, code: str, role: str = "board", travel: int = 30):
    return call(S.messages, date=date, t=t, tid=tid, code=code, role=role, travel=travel)


@app.get("/api/halt")
def halt(date: str, code: str, t: float):
    return call(S.halt, date=date, code=code, t=t)


@app.get("/api/board")
def board(date: str, code: str, t: float):
    return call(S.board, date=date, code=code, t=t)


@app.get("/api/report")
def report():
    return call(S.report)


@app.get("/p")
def phone():
    return FileResponse(WEB / "p.html")


# web/ at the site root: index.html, p.html, css/, js/ (same relative paths as on GitHub Pages)
app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
