import threading
import time
from datetime import datetime
from pathlib import Path

from app import youtube_client

_jobs: dict[int, dict] = {}
_lock = threading.Lock()

# Plusieurs vidéos "dues" en même temps (ex. après un redémarrage qui laisse
# le tick suivant traiter tout le retard d'un coup) lançaient auparavant un
# upload YouTube par idée sans aucune limite — des dizaines de connexions
# simultanées faisaient timeout en cascade (bande passante saturée) au lieu
# de réussir les unes après les autres. On borne donc le nombre d'uploads
# réellement actifs en même temps, comme pour la génération vidéo
# (cf. app/generation_pool.py).
MAX_CONCURRENT_UPLOADS = 3
_upload_semaphore = threading.Semaphore(MAX_CONCURRENT_UPLOADS)


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
        if existing and existing["status"] in ("queued", "running"):
            return
        _jobs[idea_id] = {
            "status": "queued",
            "progress": 0,
            "message": "En file d'attente...",
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
        with _upload_semaphore:
            with _lock:
                _jobs[idea_id]["status"] = "running"
                _jobs[idea_id]["message"] = "Démarrage de l'upload..."
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
            idea.published_at = datetime.utcnow()
            db.session.commit()

            # Le rangement en playlist est un bonus, pas une condition de
            # succès de la publication : un souci ici (ex. playlist déjà
            # supprimée manuellement) ne doit pas faire repasser la vidéo
            # pour "échec de publication" alors qu'elle est bien en ligne.
            try:
                from app.playlist_manager import sync_playlists_for_idea

                sync_playlists_for_idea(idea)
            except Exception as exc:
                with _lock:
                    _jobs[idea_id]["message"] = f"Publiée, mais échec du rangement en playlist : {exc}"

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
