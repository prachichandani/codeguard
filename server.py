"""CodeGuard dashboard backend.

    python server.py      -> http://localhost:8000

Starts audits (audit.py) as separate processes, lists past runs, and streams a
run's events to the browser live (Server-Sent Events). It only reads/writes the
runs/ folder - the audit itself never talks to this server, so either can crash
without taking down the other, and audits started from the terminal show up too.
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from events import RUN_DIR_ENV, RUNS_DIR, new_run_dir, read_meta, repo_name, write_meta

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
GITHUB_URL = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?(\.git)?/?$")
RUN_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
ACTIVE = ("starting", "running")
STALE_AFTER = 15 * 60  # a terminal-started run with no new events for this long is presumed dead

app = FastAPI(title="CodeGuard")

# The one audit this server is running (one at a time: Groq's per-minute token
# limit is shared, so two audits would just slow each other down)
_lock = threading.Lock()
_current: dict = {"id": None, "proc": None}


# ---------- helpers ----------

def _run_dir(run_id: str) -> Path:
    if not RUN_ID.match(run_id) or not (RUNS_DIR / run_id).is_dir():
        raise HTTPException(404, "run not found")
    return RUNS_DIR / run_id


def _append_event(run_dir: Path, type_: str, **data):
    # Only used once the audit process is gone, so there's no concurrent writer
    meta = read_meta(run_dir)
    now = time.time()
    line = json.dumps({"t": round(now - meta.get("started", now), 2), "ts": now, "type": type_, **data})
    with open(run_dir / "events.jsonl", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _refresh_status(run_dir: Path) -> dict:
    # meta.json says "running" until the audit marks itself finished/failed; if the
    # process died without doing that (killed, crashed hard), correct it here.
    meta = read_meta(run_dir)
    if meta.get("status") not in ACTIVE:
        return meta
    with _lock:
        ours = _current["id"] == run_dir.name
        proc = _current["proc"] if ours else None
    if proc is not None:
        code = proc.poll()
        if code is None:
            return meta
        meta = read_meta(run_dir)  # it may have just finished normally
        if meta.get("status") in ACTIVE:
            _append_event(run_dir, "run_failed", error=f"audit process exited with code {code}")
            write_meta(run_dir, status="failed", ended=time.time(), error=f"exit code {code}")
            meta = read_meta(run_dir)
        return meta
    events = run_dir / "events.jsonl"
    last = events.stat().st_mtime if events.exists() else meta.get("started", 0)
    if time.time() - last > STALE_AFTER:
        write_meta(run_dir, status="interrupted")
        meta = read_meta(run_dir)
    return meta


# ---------- API ----------

class NewRun(BaseModel):
    url: str


@app.post("/api/runs")
def start_run(body: NewRun):
    url = body.url.strip()
    if not GITHUB_URL.match(url):
        raise HTTPException(400, "Enter a GitHub repository URL like https://github.com/owner/repo")
    with _lock:
        if _current["proc"] is not None and _current["proc"].poll() is None:
            raise HTTPException(409, f"An audit is already running ({_current['id']}). Stop it or wait.")
        run_dir = new_run_dir(url)
        write_meta(run_dir, id=run_dir.name, url=url, repo=repo_name(url), status="starting", started=time.time())
        log = open(run_dir / "output.log", "w", encoding="utf-8")
        env = {**os.environ, RUN_DIR_ENV: str(run_dir), "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.Popen([sys.executable, "-u", "audit.py", url], cwd=BASE_DIR, env=env,
                                stdout=log, stderr=subprocess.STDOUT)
        log.close()  # the child has its own handle
        _current.update(id=run_dir.name, proc=proc)
    return {"id": run_dir.name}


@app.get("/api/runs")
def list_runs():
    if not RUNS_DIR.exists():
        return []
    runs = []
    for d in sorted((p for p in RUNS_DIR.iterdir() if p.is_dir()), reverse=True):
        meta = _refresh_status(d)
        if meta:
            runs.append(meta)
    return runs


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    return _refresh_status(_run_dir(run_id))


@app.get("/api/runs/{run_id}/events")
def get_events(run_id: str):
    path = _run_dir(run_id) / "events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # a line being written right now
    return events


@app.get("/api/runs/{run_id}/stream")
async def stream_events(run_id: str, request: Request):
    # Sends every event (from the start), then new ones as the audit writes them;
    # ends with an "end" event once the run is over.
    run_dir = _run_dir(run_id)
    path = run_dir / "events.jsonl"

    async def gen():
        pos, partial, last_ping = 0, b"", time.time()
        while not await request.is_disconnected():
            # Check status BEFORE reading, so a run that just finished gets fully drained
            done = _refresh_status(run_dir).get("status") not in ACTIVE
            if path.exists():
                with open(path, "rb") as f:
                    f.seek(pos)
                    chunk = f.read()
                    pos = f.tell()
                *lines, partial = (partial + chunk).split(b"\n")
                for line in lines:
                    if line.strip():
                        yield f"data: {line.decode('utf-8', 'replace')}\n\n"
            if done:
                yield "event: end\ndata: {}\n\n"
                return
            if time.time() - last_ping > 15:
                yield ": ping\n\n"  # keeps proxies from closing an idle connection
                last_ping = time.time()
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/runs/{run_id}/stop")
def stop_run(run_id: str):
    run_dir = _run_dir(run_id)
    with _lock:
        proc = _current["proc"] if _current["id"] == run_id else None
    if proc is None or proc.poll() is not None:
        raise HTTPException(409, "This run isn't running in this server")
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    _append_event(run_dir, "run_stopped")
    write_meta(run_dir, status="stopped", ended=time.time())
    return {"stopped": run_id}


# ---------- frontend ----------

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:
    @app.get("/", response_class=HTMLResponse)
    def no_frontend():
        return ("<h2>CodeGuard API is running.</h2><p>The dashboard isn't built yet: run "
                "<code>npm install</code> and <code>npm run build</code> in <code>frontend/</code>, "
                "or use <code>npm run dev</code> there and open http://localhost:5173.</p>")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
