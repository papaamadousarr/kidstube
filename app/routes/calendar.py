import calendar as cal_module
from datetime import date, datetime, timedelta

from flask import Blueprint, redirect, render_template, request, url_for

from app import idea_generator
from app.db import db
from app.models import Idea

bp = Blueprint("calendar", __name__, url_prefix="/calendar")


@bp.route("/")
def calendar_view():
    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))

    weeks = cal_module.Calendar(firstweekday=0).monthdayscalendar(year, month)

    ideas_by_day: dict[int, list[Idea]] = {}
    scheduled = Idea.query.filter(Idea.scheduled_date.isnot(None)).all()
    for idea in scheduled:
        if idea.scheduled_date.year == year and idea.scheduled_date.month == month:
            ideas_by_day.setdefault(idea.scheduled_date.day, []).append(idea)

    prev_month, prev_year = (12, year - 1) if month == 1 else (month - 1, year)
    next_month, next_year = (1, year + 1) if month == 12 else (month + 1, year)

    unscheduled = (
        Idea.query.filter(Idea.scheduled_date.is_(None), Idea.status != "published")
        .order_by(Idea.created_at)
        .all()
    )

    return render_template(
        "calendar.html",
        year=year,
        month=month,
        month_name=cal_module.month_name[month],
        weeks=weeks,
        ideas_by_day=ideas_by_day,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        unscheduled=unscheduled,
        today_day=today.day,
        today_month=today.month,
        today_year=today.year,
        today_iso=today.isoformat(),
        generation_error=request.args.get("generation_error"),
    )


@bp.route("/auto-schedule", methods=["POST"])
def auto_schedule():
    count = int(request.form.get("count", 0) or 0)
    interval_days = max(int(request.form.get("interval_days", 1) or 1), 1)
    videos_per_day = max(int(request.form.get("videos_per_day", 1) or 1), 1)
    start_str = request.form.get("start_date")
    start = date.fromisoformat(start_str) if start_str else date.today()
    time_str = request.form.get("publish_time")
    publish_time = datetime.strptime(time_str, "%H:%M").time() if time_str else None

    schedulable = Idea.query.filter(Idea.scheduled_date.is_(None), Idea.status != "published")

    available = schedulable.count()
    generation_error = None
    if available < count:
        try:
            idea_generator.generate_new_series_ideas(count - available)
        except idea_generator.IdeaGenerationError as exc:
            generation_error = str(exc)

    ideas = schedulable.order_by(Idea.created_at).limit(max(count, 0)).all()
    for i, idea in enumerate(ideas):
        idea.scheduled_date = start + timedelta(days=(i // videos_per_day) * interval_days)
        idea.scheduled_time = publish_time
    db.session.commit()

    return redirect(
        url_for(
            "calendar.calendar_view",
            year=start.year,
            month=start.month,
            generation_error=generation_error,
        )
    )


@bp.route("/<int:idea_id>/schedule", methods=["POST"])
def schedule_idea(idea_id: int):
    idea = db.get_or_404(Idea, idea_id)
    date_str = request.form.get("scheduled_date")
    idea.scheduled_date = date.fromisoformat(date_str) if date_str else None
    time_str = request.form.get("scheduled_time")
    idea.scheduled_time = datetime.strptime(time_str, "%H:%M").time() if (date_str and time_str) else None
    db.session.commit()
    return redirect(url_for("calendar.calendar_view", year=request.form.get("year"), month=request.form.get("month")))
