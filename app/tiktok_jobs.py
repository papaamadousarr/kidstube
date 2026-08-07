import threading
import time
from datetime import datetime
from pathlib import Path

from app import tiktok_client

_jobs: dict[int, dict] = {}
_lock = threading.Lock()

POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 120


def start_job(idea_id: int, file_path: Path, title: str, app) -> None:
    with _lock:
        existing = _jobs.get(idea_id)
        if existing and existing["status"] == "running":
            return
        _jobs[idea_id] = {
            "status": "running",
            "message": "Envoi vers TikTok...",
            "success": None,
            "started_at": time.time(),
        }

    threading.Thread(target=_run, args=(idea_id, file_path, title, app), daemon=True).start()


def _set(idea_id: int, **kwargs) -> None:
    with _lock:
        _jobs[idea_id].update(kwargs)


def _run(idea_id: int, file_path: Path, title: str, app) -> None:
    try:
        result = tiktok_client.upload_video(file_path, title)
        publish_id = result["publish_id"]
        _set(idea_id, message="Vérification du statut de publication...")

        status = {"status": "PROCESSING_UPLOAD"}
        deadline = time.time() + POLL_TIMEOUT_SECONDS
        while time.time() < deadline:
            status = tiktok_client.get_publish_status(publish_id)
            if status.get("status") in ("PUBLISH_COMPLETE", "FAILED"):
                break
            time.sleep(POLL_INTERVAL_SECONDS)

        if status.get("status") != "PUBLISH_COMPLETE":
            raise tiktok_client.TikTokUploadError(f"Statut final inattendu : {status.get('status', 'inconnu')}")
    except Exception as exc:
        _set(idea_id, status="done", success=False, message=str(exc))
        return

    with app.app_context():
        from app.db import db
        from app.models import Idea

        idea = db.session.get(Idea, idea_id)
        if idea is not None:
            idea.tiktok_publish_id = publish_id
            idea.tiktok_published_at = datetime.utcnow()
            db.session.commit()

    _set(idea_id, status="done", success=True, message="Publié sur TikTok.")


def get_job(idea_id: int) -> dict | None:
    with _lock:
        job = _jobs.get(idea_id)
        if job is None:
            return None
        return {**job, "elapsed": time.time() - job["started_at"]}
