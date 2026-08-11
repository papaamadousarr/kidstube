from pathlib import Path
from typing import Callable, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = REPO_ROOT / "secrets" / "youtube_token.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    # Nécessaire pour créer/modifier des playlists (playlists.insert,
    # playlistItems.insert) — youtube.upload seul ne couvre que les vidéos.
    "https://www.googleapis.com/auth/youtube",
]
CATEGORY_EDUCATION = "27"


class YouTubeAuthError(Exception):
    pass


class YouTubeQuotaError(Exception):
    pass


def load_credentials() -> Credentials:
    if not TOKEN_PATH.exists():
        raise YouTubeAuthError(
            f"Aucun token trouvé ({TOKEN_PATH}). Lance d'abord `python scripts/youtube_auth.py`."
        )

    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:
            raise YouTubeAuthError(
                "Le token YouTube a expiré et n'a pas pu être rafraîchi. "
                "Relance `python scripts/youtube_auth.py` pour te reconnecter."
            ) from exc
        TOKEN_PATH.write_text(creds.to_json())

    if not creds.valid:
        raise YouTubeAuthError(
            "Token YouTube invalide. Relance `python scripts/youtube_auth.py` pour te reconnecter."
        )

    return creds


def get_channel_info() -> dict:
    creds = load_credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    response = youtube.channels().list(part="statistics,id", mine=True).execute()

    items = response.get("items", [])
    if not items:
        raise YouTubeAuthError("Aucune chaîne YouTube associée à ce compte.")

    stats = items[0]["statistics"]
    return {
        "channel_id": items[0]["id"],
        "subscriber_count": int(stats.get("subscriberCount", 0)),
        "view_count": int(stats.get("viewCount", 0)),
    }


def upload_video(
    file_path: Path,
    title: str,
    description: str,
    tags: list[str],
    privacy_status: str = "private",
    made_for_kids: bool = False,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> dict:
    creds = load_credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": CATEGORY_EDUCATION,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": made_for_kids,
        },
    }

    media = MediaFileUpload(str(file_path), mimetype="video/mp4", chunksize=1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    try:
        while response is None:
            status, response = request.next_chunk()
            if status and progress_callback:
                progress_callback(int(status.progress() * 100))
    except HttpError as exc:
        status_code = exc.resp.status if exc.resp else None
        reason = (exc.reason or "").lower()
        if status_code == 403 and ("quota" in reason or "limit" in reason):
            raise YouTubeQuotaError(
                "Quota YouTube dépassé (upload = 1600 unités, quota par défaut = 10000/jour, "
                "soit ~6 vidéos/jour). Réessaie demain ou demande une augmentation de quota "
                "dans Google Cloud Console."
            ) from exc
        if status_code == 401:
            raise YouTubeAuthError(
                "Authentification YouTube refusée. Relance `python scripts/youtube_auth.py`."
            ) from exc
        raise RuntimeError(f"Échec de l'upload YouTube ({status_code}) : {exc.reason}") from exc

    if progress_callback:
        progress_callback(100)

    video_id = response["id"]
    return {"video_id": video_id, "url": f"https://youtu.be/{video_id}"}


def create_playlist(title: str, description: str = "") -> str:
    creds = load_credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    body = {
        "snippet": {"title": title, "description": description},
        "status": {"privacyStatus": "public"},
    }
    try:
        response = youtube.playlists().insert(part="snippet,status", body=body).execute()
    except HttpError as exc:
        status_code = exc.resp.status if exc.resp else None
        raise RuntimeError(f"Échec de la création de la playlist YouTube ({status_code}) : {exc.reason}") from exc

    return response["id"]


def add_video_to_playlist(playlist_id: str, video_id: str) -> None:
    creds = load_credentials()
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {"kind": "youtube#video", "videoId": video_id},
        }
    }
    try:
        youtube.playlistItems().insert(part="snippet", body=body).execute()
    except HttpError as exc:
        status_code = exc.resp.status if exc.resp else None
        raise RuntimeError(f"Échec de l'ajout à la playlist YouTube ({status_code}) : {exc.reason}") from exc
