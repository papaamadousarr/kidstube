from flask import Blueprint, current_app, jsonify, render_template, request

from app import publish_jobs, seo_defaults
from app.db import db
from app.models import Idea

bp = Blueprint("publish", __name__, url_prefix="/ideas")


@bp.route("/<int:idea_id>/publish", methods=["GET"])
def publish_form(idea_id: int):
    idea = db.get_or_404(Idea, idea_id)

    if idea.status != "assembled" or not idea.video_path.exists():
        return render_template("publish_log.html", idea=idea, not_ready=True)

    seo = seo_defaults.build_seo_defaults(idea)
    return render_template("publish_form.html", idea=idea, seo=seo)


@bp.route("/<int:idea_id>/publish", methods=["POST"])
def trigger_publish(idea_id: int):
    idea = db.get_or_404(Idea, idea_id)

    if idea.status != "assembled" or not idea.video_path.exists():
        return render_template("publish_log.html", idea=idea, not_ready=True)

    title = request.form.get("title") or idea.title
    description = request.form.get("description") or ""
    tags = [t.strip() for t in request.form.get("tags", "").split(",") if t.strip()]
    privacy_status = request.form.get("privacy_status", "public")
    made_for_kids = request.form.get("made_for_kids") == "on"

    publish_jobs.start_job(
        idea.id,
        idea.video_path,
        title,
        description,
        tags,
        privacy_status,
        made_for_kids,
        current_app._get_current_object(),
    )
    return render_template("publish_log.html", idea=idea, not_ready=False)


@bp.route("/<int:idea_id>/publish/poll")
def poll_publish(idea_id: int):
    job = publish_jobs.get_job(idea_id)
    if job is None:
        return jsonify({"status": "unknown"}), 404
    return jsonify(job)
