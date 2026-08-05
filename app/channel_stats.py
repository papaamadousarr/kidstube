import threading
import time

from app import youtube_client
from app.youtube_client import YouTubeAuthError

_CACHE_TTL_SECONDS = 600
_cache: dict = {"data": None, "fetched_at": 0.0}
_lock = threading.Lock()


def get_channel_stats(force_refresh: bool = False) -> dict:
    now = time.time()
    with _lock:
        cached = _cache["data"]
        if not force_refresh and cached and (now - _cache["fetched_at"] < _CACHE_TTL_SECONDS):
            return cached

    try:
        info = youtube_client.get_channel_info()
        result = {
            "connected": True,
            "subscriber_count": info["subscriber_count"],
            "view_count": info["view_count"],
            "channel_id": info["channel_id"],
            "studio_url": f"https://studio.youtube.com/channel/{info['channel_id']}/monetization",
        }
    except YouTubeAuthError:
        result = {"connected": False, "reason": "not_authenticated", "error": None}
    except Exception as exc:
        result = {"connected": False, "reason": "error", "error": str(exc)}

    with _lock:
        _cache["data"] = result
        _cache["fetched_at"] = now

    return result
