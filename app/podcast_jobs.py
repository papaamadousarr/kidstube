import threading
import time

from app.generation_pool import build_slot
from pipeline.videogen.podcast_builder import build_podcast_series

_jobs: dict[int, dict] = {}
_lock = threading.Lock()
_ACTIVE_STATUSES = ("queued", "running")


def start_job(idea_id: int, podcast_series_key: str, aspect_ratio: str, app) -> None:
    with _lock:
        existing = _jobs.get(idea_id)
        if existing and existing["status"] in _ACTIVE_STATUSES:
            return
        _jobs[idea_id] = {
            "status": "queued",
            "message": "En file d'attente...",
            "success": None,
            "started_at": time.time(),
        }

    threading.Thread(
        target=_run,
        args=(idea_id, podcast_series_key, aspect_ratio, app),
        daemon=True,
    ).start()


def _set(idea_id: int, **kwargs) -> None:
    with _lock:
        _jobs[idea_id].update(kwargs)


def _run(idea_id: int, podcast_series_key: str, aspect_ratio: str, app) -> None:
    try:
        with build_slot():
            _set(idea_id, status="running", message="Démarrage...")
            build_podcast_series(
                podcast_series_key,
                aspect_ratio=aspect_ratio,
                progress_callback=lambda msg: _set(idea_id, message=msg),
            )

        with app.app_context():
            from app.db import db
            from app.models import Idea

            idea = db.session.get(Idea, idea_id)
            if idea is not None:
                idea.status = "assembled"
                db.session.commit()

        _set(idea_id, status="done", success=True, message="Podcast généré avec succès.")
    except Exception as exc:
        _set(idea_id, status="done", success=False, message=str(exc))


def get_job(idea_id: int) -> dict | None:
    with _lock:
        job = _jobs.get(idea_id)
        if job is None:
            return None
        return {
            "status": job["status"],
            "success": job["success"],
            "message": job["message"],
            "elapsed": time.time() - job["started_at"],
        }
