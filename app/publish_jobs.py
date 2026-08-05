import threading
import time
from pathlib import Path

from app import youtube_client

_jobs: dict[int, dict] = {}
_lock = threading.Lock()


def start_job(
    idea_id: int,
    file_path: Path,
    title: str,
    description: str,
    tags: list[str],
    privacy_status: str,
    made_for_kids: bool,
    app,
) -> None:
    with _lock:
        existing = _jobs.get(idea_id)
        if existing and existing["status"] == "running":
            return
        _jobs[idea_id] = {
            "status": "running",
            "progress": 0,
            "message": "Démarrage de l'upload...",
            "success": None,
            "video_id": None,
            "error": None,
            "started_at": time.time(),
        }

    threading.Thread(
        target=_run,
        args=(idea_id, file_path, title, description, tags, privacy_status, made_for_kids, app),
        daemon=True,
    ).start()


def _set_progress(idea_id: int, pct: int) -> None:
    with _lock:
        _jobs[idea_id]["progress"] = pct
        _jobs[idea_id]["message"] = f"Envoi en cours... {pct}%"


def _run(
    idea_id: int,
    file_path: Path,
    title: str,
    description: str,
    tags: list[str],
    privacy_status: str,
    made_for_kids: bool,
    app,
) -> None:
    try:
        result = youtube_client.upload_video(
            file_path,
            title,
            description,
            tags,
            privacy_status=privacy_status,
            made_for_kids=made_for_kids,
            progress_callback=lambda pct: _set_progress(idea_id, pct),
        )
    except Exception as exc:
        with _lock:
            _jobs[idea_id]["status"] = "done"
            _jobs[idea_id]["success"] = False
            _jobs[idea_id]["error"] = str(exc)
        return

    with app.app_context():
        from app.db import db
        from app.models import Idea

        idea = db.session.get(Idea, idea_id)
        if idea is not None:
            idea.status = "published"
            idea.youtube_video_id = result["video_id"]
            db.session.commit()

    with _lock:
        _jobs[idea_id]["status"] = "done"
        _jobs[idea_id]["success"] = True
        _jobs[idea_id]["video_id"] = result["video_id"]
        _jobs[idea_id]["progress"] = 100


def get_job(idea_id: int) -> dict | None:
    with _lock:
        job = _jobs.get(idea_id)
        if job is None:
            return None
        return {**job, "elapsed": time.time() - job["started_at"]}
