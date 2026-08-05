from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for

from app import higgsfield_jobs
from app.db import db
from app.models import Idea
from pipeline.content.higgsfield_loader import list_higgsfield_series, load_higgsfield_series
from pipeline.content.schema import ContentError
from pipeline.videogen import higgsfield_client

bp = Blueprint("higgsfield", __name__, url_prefix="/higgsfield")


@bp.route("/")
def higgsfield_view():
    connected = higgsfield_client.is_connected()
    series_keys = list_higgsfield_series()
    ideas = Idea.query.filter_by(video_pipeline="higgsfield").order_by(Idea.created_at.desc()).all()
    available_ideas = (
        Idea.query.filter(Idea.video_pipeline == "flashcards", Idea.status.in_(["idea", "script"]))
        .order_by(Idea.created_at)
        .all()
    )
    return render_template(
        "higgsfield.html",
        connected=connected,
        series_keys=series_keys,
        ideas=ideas,
        available_ideas=available_ideas,
    )


@bp.route("/generate", methods=["POST"])
def trigger_generate():
    if not higgsfield_client.is_connected():
        return redirect(url_for("higgsfield.higgsfield_view"))

    series_key = request.form.get("series_key", "").strip()
    try:
        series = load_higgsfield_series(series_key)
    except ContentError:
        return redirect(url_for("higgsfield.higgsfield_view"))

    aspect_ratio = request.form.get("aspect_ratio") or series.aspect_ratio
    idea_id = request.form.get("idea_id")

    if idea_id:
        idea = db.get_or_404(Idea, int(idea_id))
    else:
        idea = Idea(title=series.title, status="idea")
        db.session.add(idea)

    idea.series_key = series_key
    idea.video_pipeline = "higgsfield"
    db.session.commit()

    higgsfield_jobs.start_job(idea.id, series_key, aspect_ratio, current_app._get_current_object())
    return render_template("higgsfield_progress.html", idea=idea)


@bp.route("/<int:idea_id>/poll")
def poll_generate(idea_id: int):
    job = higgsfield_jobs.get_job(idea_id)
    if job is None:
        return jsonify({"status": "unknown"}), 404
    return jsonify(job)
