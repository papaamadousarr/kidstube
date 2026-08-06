from datetime import date, timedelta

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app import youtube_client
from app.youtube_client import YouTubeAuthError

DEFAULT_WINDOW_DAYS = 28


class YouTubeAnalyticsError(Exception):
    pass


def _build_client():
    creds = youtube_client.load_credentials()
    return build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)


def _date_range(days: int) -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def _run_query(analytics, **kwargs) -> dict:
    try:
        return analytics.reports().query(**kwargs).execute()
    except HttpError as exc:
        raise YouTubeAnalyticsError(
            f"Échec de l'appel à l'API YouTube Analytics : {exc.reason or exc}"
        ) from exc


def get_channel_summary(days: int = DEFAULT_WINDOW_DAYS) -> dict:
    """Vue d'ensemble chaîne sur la période : vues, temps de visionnage, durée
    moyenne de vue, abonnés gagnés/perdus, likes, commentaires."""
    analytics = _build_client()
    start, end = _date_range(days)
    resp = _run_query(
        analytics,
        ids="channel==MINE",
        startDate=start,
        endDate=end,
        metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
        "subscribersGained,subscribersLost,likes,comments,shares",
    )
    rows = resp.get("rows") or [[0] * 9]
    values = rows[0]
    keys = [c["name"] for c in resp.get("columnHeaders", [])]
    summary = dict(zip(keys, values))
    summary["period_start"] = start
    summary["period_end"] = end
    summary["days"] = days
    return summary


def get_daily_trend(days: int = DEFAULT_WINDOW_DAYS) -> list[dict]:
    """Séries jour par jour (vues, minutes regardées, abonnés gagnés) pour un
    graphique de tendance simple."""
    analytics = _build_client()
    start, end = _date_range(days)
    resp = _run_query(
        analytics,
        ids="channel==MINE",
        startDate=start,
        endDate=end,
        metrics="views,estimatedMinutesWatched,subscribersGained",
        dimensions="day",
        sort="day",
    )
    keys = [c["name"] for c in resp.get("columnHeaders", [])]
    return [dict(zip(keys, row)) for row in resp.get("rows", [])]


def get_top_videos(days: int = DEFAULT_WINDOW_DAYS, limit: int = 10) -> list[dict]:
    """Vidéos les plus vues sur la période, avec titres résolus depuis notre
    propre base (Idea.youtube_video_id) plutôt qu'un appel API supplémentaire."""
    from app.models import Idea

    analytics = _build_client()
    start, end = _date_range(days)
    resp = _run_query(
        analytics,
        ids="channel==MINE",
        startDate=start,
        endDate=end,
        metrics="views,estimatedMinutesWatched,averageViewPercentage,likes",
        dimensions="video",
        sort="-views",
        maxResults=limit,
    )
    keys = [c["name"] for c in resp.get("columnHeaders", [])]
    rows = [dict(zip(keys, row)) for row in resp.get("rows", [])]

    video_ids = [r["video"] for r in rows]
    ideas_by_video_id = {
        idea.youtube_video_id: idea
        for idea in Idea.query.filter(Idea.youtube_video_id.in_(video_ids)).all()
    }
    for row in rows:
        idea = ideas_by_video_id.get(row["video"])
        row["title"] = idea.title if idea else row["video"]
        row["video_pipeline"] = idea.video_pipeline if idea else None
    return rows


def get_traffic_sources(days: int = DEFAULT_WINDOW_DAYS) -> list[dict]:
    """Répartition des vues par source de trafic (recherche, suggestions,
    Shorts feed, externe...)."""
    analytics = _build_client()
    start, end = _date_range(days)
    resp = _run_query(
        analytics,
        ids="channel==MINE",
        startDate=start,
        endDate=end,
        metrics="views",
        dimensions="insightTrafficSourceType",
        sort="-views",
    )
    keys = [c["name"] for c in resp.get("columnHeaders", [])]
    return [dict(zip(keys, row)) for row in resp.get("rows", [])]


def is_connected() -> bool:
    return youtube_client.TOKEN_PATH.exists()
