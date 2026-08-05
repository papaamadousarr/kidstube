from flask import Blueprint, current_app, redirect, render_template, request, url_for

from app import channel_stats, jobs, podcast_jobs, scheduler, shorts_jobs
from app.db import db
from app.models import STATUSES, Idea

bp = Blueprint("board", __name__, url_prefix="/board")

# Flashcards/Shorts : génération locale gratuite, sûre à déclencher en masse
# (protégée par la limite de concurrence de app.generation_pool).
GENERATABLE_PIPELINES = ("flashcards", "shorts")
# Podcast : passe par l'API payante Higgsfield (crédits) — pas inclus dans le
# bouton "Générer toutes", seulement déclenchable idée par idée pour éviter
# qu'un clic groupé ne consomme les crédits d'un coup.
WIDGET_PIPELINES = ("flashcards", "shorts", "podcast")
ACTIVE_JOB_STATUSES = ("queued", "running")


def _get_job_for(idea: Idea):
    if idea.video_pipeline == "shorts":
        return shorts_jobs.get_job(idea.id)
    if idea.video_pipeline == "podcast":
        return podcast_jobs.get_job(idea.id)
    return jobs.get_job(idea.id)


def _generatable_ideas():
    return Idea.query.filter(
        Idea.status == "idea",
        Idea.series_key.isnot(None),
        Idea.video_pipeline.in_(GENERATABLE_PIPELINES),
    ).all()


@bp.route("/")
def board_view():
    columns = {status: Idea.query.filter_by(status=status).order_by(Idea.created_at).all() for status in STATUSES}
    stats = channel_stats.get_channel_stats()
    automation_log = scheduler.get_recent_log()

    job_status = {}
    for ideas in columns.values():
        for idea in ideas:
            if idea.series_key and idea.video_pipeline in WIDGET_PIPELINES:
                job_status[idea.id] = _get_job_for(idea)

    generatable_count = sum(
        1
        for idea in columns["idea"]
        if idea.series_key
        and idea.video_pipeline in GENERATABLE_PIPELINES
        and not (job_status.get(idea.id) and job_status[idea.id]["status"] in ACTIVE_JOB_STATUSES)
    )

    return render_template(
        "board.html",
        columns=columns,
        statuses=STATUSES,
        stats=stats,
        automation_log=automation_log,
        job_status=job_status,
        generatable_count=generatable_count,
    )


@bp.route("/generate-all", methods=["POST"])
def generate_all():
    app_obj = current_app._get_current_object()
    for idea in _generatable_ideas():
        if idea.video_pipeline == "shorts":
            shorts_jobs.start_job(idea.id, idea.series_key, idea.short_item_index or 0, app_obj)
        else:
            jobs.start_job(idea.id, idea.series_key, app_obj)
    return redirect(url_for("board.board_view"))


@bp.route("/<int:idea_id>/status", methods=["POST"])
def update_status(idea_id: int):
    idea = db.get_or_404(Idea, idea_id)
    new_status = request.form.get("status")
    if new_status in STATUSES:
        idea.status = new_status
        db.session.commit()
    return redirect(url_for("board.board_view"))
