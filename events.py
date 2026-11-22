"""Structured record of what an audit is doing, for the dashboard.

Each audit gets a folder runs/<id>/ with:
  meta.json     - url, status, start/end time, final counts
  events.jsonl  - one JSON object per line: {"t": secs since start, "ts": epoch, "type": ..., ...}

The dashboard server starts audits with CODEGUARD_RUN_DIR set to the folder it
created; audits started from the terminal create their own folder. Code that
never calls start_run() (e.g. querytest.py) just doesn't record anything.
"""
import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parent / "runs"
RUN_DIR_ENV = "CODEGUARD_RUN_DIR"

_lock = threading.Lock()  # agents run in parallel threads
_run_dir: Path | None = None
_t0 = 0.0


def repo_name(url: str) -> str:
    return url.rstrip("/").removesuffix(".git").split("/")[-1] or "repo"


def new_run_dir(url: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", repo_name(url))
    run_dir = RUNS_DIR / f"{stamp}-{safe}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def read_meta(run_dir: Path) -> dict:
    for _ in range(5):  # the file may be mid-replace by the other process (Windows)
        try:
            return json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (PermissionError, json.JSONDecodeError):
            time.sleep(0.05)
    return {}


def write_meta(run_dir: Path, **fields):
    meta = {**read_meta(run_dir), **fields}
    tmp = run_dir / "meta.json.tmp"
    tmp.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    for _ in range(5):
        try:
            os.replace(tmp, run_dir / "meta.json")
            return
        except PermissionError:  # reader has it open (Windows); try again shortly
            time.sleep(0.05)


def start_run(url: str) -> Path:
    global _run_dir, _t0
    env_dir = os.environ.get(RUN_DIR_ENV)
    _run_dir = Path(env_dir) if env_dir else new_run_dir(url)
    _run_dir.mkdir(parents=True, exist_ok=True)
    _t0 = time.time()
    write_meta(_run_dir, id=_run_dir.name, url=url, repo=repo_name(url),
               status="running", started=_t0, pid=os.getpid())
    emit("run_started", url=url, repo=repo_name(url))
    return _run_dir


def emit(type_: str, **data):
    if _run_dir is None:
        return
    now = time.time()
    line = json.dumps({"t": round(now - _t0, 2), "ts": now, "type": type_, **data},
                      ensure_ascii=False, default=str)
    with _lock:
        with open(_run_dir / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")


def finish_run(status: str, **fields):
    if _run_dir is None:
        return
    write_meta(_run_dir, status=status, ended=time.time(), **fields)


def agent_from_prefix(prefix: str) -> str | None:
    # agent.py labels its output "[security] "; recover the name for events
    name = prefix.strip().strip("[]")
    return name or None
