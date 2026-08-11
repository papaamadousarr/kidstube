from flask import Blueprint, current_app, jsonify, render_template, request

from app import jobs, podcast_jobs, shorts_jobs
from app.db import db
from app.models import Idea

bp = Blueprint("generate", __name__, url_prefix="/ideas")

_ACTIVE_STATUSES = ("queued", "running")


def _get_job(idea: Idea) -> dict | None:
    if idea.video_pipeline == "shorts":
        return shorts_jobs.get_job(idea.id)
    if idea.video_pipeline == "podcast":
        return podcast_jobs.get_job(idea.id)
    return jobs.get_job(idea.id)


def _start_job(idea: Idea, app_obj) -> None:
    if idea.video_pipeline == "shorts":
        shorts_jobs.start_job(idea.id, idea.series_key, idea.short_item_index or 0, app_obj, idea.short_group_size)
    elif idea.video_pipeline == "podcast":
        podcast_jobs.start_job(idea.id, idea.series_key, "9:16", app_obj)
    else:
        jobs.start_job(idea.id, idea.series_key, app_obj)


@bp.route("/<int:idea_id>/generate", methods=["GET", "POST"])
def trigger_generate(idea_id: int):
    idea = db.get_or_404(Idea, idea_id)

    if not idea.series_key:
        return render_template("generate_log.html", idea=idea, no_series=True)

    current_job = _get_job(idea)
    already_active = current_job is not None and current_job["status"] in _ACTIVE_STATUSES

    # En GET (lien "Voir le détail" depuis le Kanban), on ne relance une génération
    # que si aucune n'est déjà en cours — on veut juste ouvrir la page de suivi.
    if request.method == "POST" or not already_active:
        _start_job(idea, current_app._get_current_object())
    return render_template("generate_log.html", idea=idea, no_series=False)


@bp.route("/<int:idea_id>/generate/poll")
def poll_generate(idea_id: int):
    idea = db.session.get(Idea, idea_id)
    job = _get_job(idea) if idea else None
    if job is None:
        return jsonify({"status": "unknown"}), 404
    return jsonify(job)
