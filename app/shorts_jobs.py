import subprocess
import sys
import threading
import time
from pathlib import Path

from app import generation_pool
from app.generation_pool import build_slot

REPO_ROOT = Path(__file__).resolve().parent.parent

_jobs: dict[int, dict] = {}
_lock = threading.Lock()
_ACTIVE_STATUSES = ("queued", "running")


def start_job(idea_id: int, series_key: str, item_index: int, app, group_size: int = 1) -> None:
    with _lock:
        existing = _jobs.get(idea_id)
        if existing and existing["status"] in _ACTIVE_STATUSES:
            return
        _jobs[idea_id] = {"status": "queued", "log": [], "success": None, "started_at": time.time()}

    threading.Thread(target=_run, args=(idea_id, series_key, item_index, app, group_size), daemon=True).start()


def _cancel(idea_id: int) -> None:
    with _lock:
        _jobs[idea_id]["status"] = "done"
        _jobs[idea_id]["success"] = None
        _jobs[idea_id]["log"].append("Génération annulée (arrêt demandé).")


def _run(idea_id: int, series_key: str, item_index: int, app, group_size: int = 1) -> None:
    if generation_pool.is_stop_requested():
        _cancel(idea_id)
        return

    with build_slot():
        if generation_pool.is_stop_requested():
            _cancel(idea_id)
            return

        with _lock:
            _jobs[idea_id]["status"] = "running"

        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "pipeline",
                "build-short",
                series_key,
                str(item_index),
                "--group-size",
                str(group_size),
            ],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        generation_pool.register_process(process)
        try:
            for line in process.stdout:
                with _lock:
                    _jobs[idea_id]["log"].append(line.rstrip("\n"))
            process.wait()
        finally:
            generation_pool.unregister_process(process)
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


def count_active() -> int:
    with _lock:
        return sum(1 for job in _jobs.values() if job["status"] in _ACTIVE_STATUSES)
