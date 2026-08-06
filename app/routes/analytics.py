from flask import Blueprint, redirect, render_template, request, url_for

from app import analytics_insights, youtube_analytics
from app.youtube_client import YouTubeAuthError

bp = Blueprint("analytics", __name__, url_prefix="/analytics")

WINDOW_DAYS = 28


@bp.route("/")
def analytics_view():
    insight_error = request.args.get("insight_error")

    if not youtube_analytics.is_connected():
        return render_template("analytics.html", connected=False, error=None, insight_error=insight_error)

    try:
        summary = youtube_analytics.get_channel_summary(WINDOW_DAYS)
        trend = youtube_analytics.get_daily_trend(WINDOW_DAYS)
        top_videos = youtube_analytics.get_top_videos(WINDOW_DAYS)
        traffic_sources = youtube_analytics.get_traffic_sources(WINDOW_DAYS)
    except (YouTubeAuthError, youtube_analytics.YouTubeAnalyticsError) as exc:
        return render_template("analytics.html", connected=True, error=str(exc), insight_error=insight_error)

    latest_insight = analytics_insights.get_latest_insight()
    priority_themes = analytics_insights.priority_themes_list(latest_insight) if latest_insight else []

    max_trend_views = max((row.get("views", 0) for row in trend), default=0) or 1

    return render_template(
        "analytics.html",
        connected=True,
        error=None,
        insight_error=insight_error,
        summary=summary,
        trend=trend,
        max_trend_views=max_trend_views,
        top_videos=top_videos,
        traffic_sources=traffic_sources,
        latest_insight=latest_insight,
        priority_themes=priority_themes,
        window_days=WINDOW_DAYS,
    )


@bp.route("/generate-insight", methods=["POST"])
def generate_insight():
    try:
        summary = youtube_analytics.get_channel_summary(WINDOW_DAYS)
        trend = youtube_analytics.get_daily_trend(WINDOW_DAYS)
        top_videos = youtube_analytics.get_top_videos(WINDOW_DAYS)
        traffic_sources = youtube_analytics.get_traffic_sources(WINDOW_DAYS)
    except (YouTubeAuthError, youtube_analytics.YouTubeAnalyticsError) as exc:
        return redirect(url_for("analytics.analytics_view", insight_error=str(exc)))

    analytics_data = {
        "resume_chaine": summary,
        "tendance_quotidienne": trend,
        "meilleures_videos": top_videos,
        "sources_de_trafic": traffic_sources,
    }

    try:
        analytics_insights.generate_insight(analytics_data, WINDOW_DAYS)
    except analytics_insights.InsightGenerationError as exc:
        return redirect(url_for("analytics.analytics_view", insight_error=str(exc)))

    return redirect(url_for("analytics.analytics_view"))
