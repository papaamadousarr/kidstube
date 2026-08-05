import subprocess
import sys
import threading
import time
from pathlib import Path

from app.generation_pool import build_slot

REPO_ROOT = Path(__file__).resolve().parent.parent

_jobs: dict[int, dict] = {}
_lock = threading.Lock()
_ACTIVE_STATUSES = ("queued", "running")


def start_job(idea_id: int, series_key: str, item_index: int, app) -> None:
    with _lock:
        existing = _jobs.get(idea_id)
        if existing and existing["status"] in _ACTIVE_STATUSES:
            return
        _jobs[idea_id] = {"status": "queued", "log": [], "success": None, "started_at": time.time()}

    threading.Thread(target=_run, args=(idea_id, series_key, item_index, app), daemon=True).start()


def _run(idea_id: int, series_key: str, item_index: int, app) -> None:
    with build_slot():
        with _lock:
            _jobs[idea_id]["status"] = "running"

        process = subprocess.Popen(
            [sys.executable, "-u", "-m", "pipeline", "build-short", series_key, str(item_index)],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for line in process.stdout:
            with _lock:
                _jobs[idea_id]["log"].append(line.rstrip("\n"))
        process.wait()
        success = process.returncode == 0

    with app.app_context():
        from app.db import db
        from app.models import Idea

        idea = db.session.get(Idea, idea_id)
        if success and idea is not None:
            idea.status = "assembled"
            db.session.commit()

    with _lock:
        _jobs[idea_id]["status"] = "done"
        _jobs[idea_id]["success"] = success


def get_job(idea_id: int) -> dict | None:
    with _lock:
        job = _jobs.get(idea_id)
        if job is None:
            return None
        return {
            "status": job["status"],
            "success": job["success"],
            "log": "\n".join(job["log"]),
            "elapsed": time.time() - job["started_at"],
        }
