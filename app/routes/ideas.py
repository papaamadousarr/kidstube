from datetime import date, datetime

from flask import Blueprint, redirect, render_template, request, url_for

from app import idea_generator
from app.db import db
from app.models import STATUSES, Idea
from pipeline.content.loader import list_series, load_series
from pipeline.content.schema import ContentError

bp = Blueprint("ideas", __name__, url_prefix="/ideas")


def _short_options() -> list[tuple[str, str]]:
    options = []
    for series_key in list_series():
        try:
            series = load_series(series_key)
        except ContentError:
            continue
        for index, item in enumerate(series.items):
            options.append((f"{series_key}::{index}", f"{series.title} — {item.name}"))
    return options


@bp.route("/")
def ideas_list():
    ideas = Idea.query.order_by(Idea.created_at.desc()).all()
    return render_template(
        "ideas_list.html",
        ideas=ideas,
        statuses=STATUSES,
        generation_error=request.args.get("generation_error"),
        short_options=_short_options(),
    )


@bp.route("/create-short", methods=["POST"])
def create_short():
    selection = request.form.get("short_item", "")
    series_key, _, index_str = selection.partition("::")
    if not series_key or not index_str.isdigit():
        return redirect(url_for("ideas.ideas_list"))

    try:
        series = load_series(series_key)
    except ContentError:
        return redirect(url_for("ideas.ideas_list"))

    index = int(index_str)
    if not (0 <= index < len(series.items)):
        return redirect(url_for("ideas.ideas_list"))

    item = series.items[index]
    idea = Idea(
        title=f"{item.name} (Short)",
        series_key=series_key,
        video_pipeline="shorts",
        short_item_index=index,
        status="idea",
    )
    db.session.add(idea)
    db.session.commit()
    return redirect(url_for("ideas.ideas_list"))


@bp.route("/generate-ideas", methods=["POST"])
def generate_ideas():
    count = max(int(request.form.get("count", 3) or 3), 1)
    generation_error = None
    try:
        idea_generator.generate_new_series_ideas(count)
    except idea_generator.IdeaGenerationError as exc:
        generation_error = str(exc)
    return redirect(url_for("ideas.ideas_list", generation_error=generation_error))


@bp.route("/new", methods=["GET", "POST"])
def new_idea():
    if request.method == "POST":
        idea = Idea(
            title=request.form["title"],
            series_key=request.form.get("series_key") or None,
            notes=request.form.get("notes"),
        )
        db.session.add(idea)
        db.session.commit()
        return redirect(url_for("ideas.ideas_list"))
    return render_template("idea_form.html", idea=None, series_options=list_series(), statuses=STATUSES)


@bp.route("/<int:idea_id>/edit", methods=["GET", "POST"])
def edit_idea(idea_id: int):
    idea = db.get_or_404(Idea, idea_id)
    if request.method == "POST":
        idea.title = request.form["title"]
        idea.series_key = request.form.get("series_key") or None
        idea.notes = request.form.get("notes")
        idea.status = request.form.get("status", idea.status)
        date_str = request.form.get("scheduled_date")
        idea.scheduled_date = date.fromisoformat(date_str) if date_str else None
        time_str = request.form.get("scheduled_time")
        idea.scheduled_time = datetime.strptime(time_str, "%H:%M").time() if (date_str and time_str) else None
        db.session.commit()
        return redirect(url_for("ideas.ideas_list"))
    return render_template("idea_form.html", idea=idea, series_options=list_series(), statuses=STATUSES)


@bp.route("/<int:idea_id>/delete", methods=["POST"])
def delete_idea(idea_id: int):
    idea = db.get_or_404(Idea, idea_id)
    db.session.delete(idea)
    db.session.commit()
    return redirect(url_for("ideas.ideas_list"))
