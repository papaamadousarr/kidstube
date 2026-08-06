import json
import os
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = REPO_ROOT / "secrets" / "tiktok_token.json"

load_dotenv(REPO_ROOT / "secrets" / ".env")
CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

# Tant que l'app TikTok n'est pas auditée par TikTok, seule cette valeur est
# acceptée par l'API : les vidéos publiées restent visibles uniquement par
# le compte propriétaire, quelle que soit la valeur demandée par l'appelant.
UNAUDITED_PRIVACY_LEVEL = "SELF_ONLY"

# L'API exige un chunk entre 5 Mo et 64 Mo. Au-delà, il faut découper
# l'upload en plusieurs chunks — pas implémenté ici car les Shorts/Reels
# visés par ce pipeline tiennent largement sous cette limite.
MAX_SINGLE_CHUNK_BYTES = 64 * 1024 * 1024

# Marge de sécurité avant l'expiration réelle du token pour déclencher un
# rafraîchissement proactif plutôt que de risquer un 401 en plein upload.
REFRESH_MARGIN_SECONDS = 300


class TikTokAuthError(Exception):
    pass


class TikTokQuotaError(Exception):
    pass


class TikTokUploadError(Exception):
    pass


def _load_token() -> dict:
    if not TOKEN_PATH.exists():
        raise TikTokAuthError(
            f"Aucun token trouvé ({TOKEN_PATH}). Lance d'abord `python scripts/tiktok_auth.py`."
        )
    return json.loads(TOKEN_PATH.read_text())


def _save_token(token: dict) -> None:
    TOKEN_PATH.write_text(json.dumps(token, indent=2))


def _is_expired(token: dict) -> bool:
    obtained_at = token.get("obtained_at", 0)
    expires_in = token.get("expires_in", 0)
    return time.time() >= obtained_at + expires_in - REFRESH_MARGIN_SECONDS


def _refresh(token: dict) -> dict:
    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
        },
        timeout=30,
    )
    if response.status_code != 200 or "access_token" not in response.json():
        raise TikTokAuthError(
            "Le token TikTok a expiré et n'a pas pu être rafraîchi. "
            "Relance `python scripts/tiktok_auth.py` pour te reconnecter."
        )
    new_token = response.json()
    new_token["obtained_at"] = time.time()
    _save_token(new_token)
    return new_token


def load_credentials() -> dict:
    token = _load_token()
    if _is_expired(token):
        token = _refresh(token)
    return token


def upload_video(
    file_path: Path,
    title: str,
    disable_comment: bool = False,
    progress_callback: Optional[callable] = None,
) -> dict:
    token = load_credentials()
    access_token = token["access_token"]
    video_size = Path(file_path).stat().st_size

    if video_size > MAX_SINGLE_CHUNK_BYTES:
        raise TikTokUploadError(
            f"Vidéo trop volumineuse pour un upload en un seul chunk ({video_size} octets, "
            f"max {MAX_SINGLE_CHUNK_BYTES}). Upload multi-chunk non implémenté."
        )

    init_response = requests.post(
        INIT_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "post_info": {
                "title": title,
                "privacy_level": UNAUDITED_PRIVACY_LEVEL,
                "disable_duet": False,
                "disable_comment": disable_comment,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": video_size,
                "total_chunk_count": 1,
            },
        },
        timeout=30,
    )
    init_data = init_response.json()
    error_code = init_data.get("error", {}).get("code", "ok")
    if error_code != "ok":
        message = init_data["error"].get("message", "erreur inconnue")
        if error_code == "rate_limit_exceeded" or init_response.status_code == 429:
            raise TikTokQuotaError(f"Quota TikTok dépassé : {message}")
        if init_response.status_code == 401:
            raise TikTokAuthError("Authentification TikTok refusée. Relance `python scripts/tiktok_auth.py`.")
        raise TikTokUploadError(f"Échec de l'initialisation de l'upload TikTok : {message}")

    publish_id = init_data["data"]["publish_id"]
    upload_url = init_data["data"]["upload_url"]

    with open(file_path, "rb") as f:
        video_bytes = f.read()

    upload_response = requests.put(
        upload_url,
        headers={
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
        },
        data=video_bytes,
        timeout=120,
    )
    if upload_response.status_code not in (200, 201):
        raise TikTokUploadError(f"Échec de l'envoi de la vidéo TikTok ({upload_response.status_code}).")

    if progress_callback:
        progress_callback(100)

    return {"publish_id": publish_id}


def get_publish_status(publish_id: str) -> dict:
    token = load_credentials()
    response = requests.post(
        STATUS_URL,
        headers={
            "Authorization": f"Bearer {token['access_token']}",
            "Content-Type": "application/json",
        },
        json={"publish_id": publish_id},
        timeout=30,
    )
    data = response.json()
    error_code = data.get("error", {}).get("code", "ok")
    if error_code != "ok":
        raise TikTokUploadError(f"Échec de la vérification du statut TikTok : {data['error'].get('message')}")
    return data["data"]
