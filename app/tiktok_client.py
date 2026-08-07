import json
import os
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = REPO_ROOT / "secrets"

load_dotenv(SECRETS_DIR / ".env")


def is_connected(sandbox: bool = False) -> bool:
    token_path, _, _ = _credentials(sandbox)
    return token_path.exists()


def _credentials(sandbox: bool) -> tuple[Path, str, str]:
    if sandbox:
        return (
            SECRETS_DIR / "tiktok_sandbox_token.json",
            os.getenv("TIKTOK_SANDBOX_CLIENT_KEY"),
            os.getenv("TIKTOK_SANDBOX_CLIENT_SECRET"),
        )
    return (
        SECRETS_DIR / "tiktok_token.json",
        os.getenv("TIKTOK_CLIENT_KEY"),
        os.getenv("TIKTOK_CLIENT_SECRET"),
    )

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

# Repli si, pour une raison quelconque, l'appel à creator_info ne renvoie
# aucune option de confidentialité exploitable.
FALLBACK_PRIVACY_LEVEL = "SELF_ONLY"

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


def _load_token(token_path: Path, auth_hint: str) -> dict:
    if not token_path.exists():
        raise TikTokAuthError(f"Aucun token trouvé ({token_path}). Lance d'abord `{auth_hint}`.")
    return json.loads(token_path.read_text())


def _is_expired(token: dict) -> bool:
    obtained_at = token.get("obtained_at", 0)
    expires_in = token.get("expires_in", 0)
    return time.time() >= obtained_at + expires_in - REFRESH_MARGIN_SECONDS


def _refresh(token: dict, token_path: Path, client_key: str, client_secret: str, auth_hint: str) -> dict:
    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
        },
        timeout=30,
    )
    if response.status_code != 200 or "access_token" not in response.json():
        raise TikTokAuthError(
            f"Le token TikTok a expiré et n'a pas pu être rafraîchi. Relance `{auth_hint}` pour te reconnecter."
        )
    new_token = response.json()
    new_token["obtained_at"] = time.time()
    token_path.write_text(json.dumps(new_token, indent=2))
    return new_token


def load_credentials(sandbox: bool = False) -> dict:
    token_path, client_key, client_secret = _credentials(sandbox)
    auth_hint = "python scripts/tiktok_auth.py --sandbox" if sandbox else "python scripts/tiktok_auth.py"
    token = _load_token(token_path, auth_hint)
    if _is_expired(token):
        token = _refresh(token, token_path, client_key, client_secret, auth_hint)
    return token


def get_creator_info(sandbox: bool = False) -> dict:
    """À appeler avant tout post : les Content Sharing Guidelines de TikTok
    exigent d'utiliser les options réellement disponibles pour ce compte
    (privacy_level_options, interactions déjà désactivées par le créateur)
    plutôt que de forcer des valeurs en dur — un post qui ignore ça est
    rejeté par /video/init/ avec un renvoi générique vers les guidelines."""
    token = load_credentials(sandbox)
    response = requests.post(
        CREATOR_INFO_URL,
        headers={
            "Authorization": f"Bearer {token['access_token']}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        timeout=30,
    )
    data = response.json()
    error_code = data.get("error", {}).get("code", "ok")
    if error_code != "ok":
        raise TikTokUploadError(
            f"Échec de la récupération des infos créateur TikTok : {data['error'].get('message')}"
        )
    return data["data"]


def upload_video(
    file_path: Path,
    title: str,
    disable_comment: bool = False,
    progress_callback: Optional[callable] = None,
    sandbox: bool = False,
) -> dict:
    token = load_credentials(sandbox)
    access_token = token["access_token"]
    video_size = Path(file_path).stat().st_size

    if video_size > MAX_SINGLE_CHUNK_BYTES:
        raise TikTokUploadError(
            f"Vidéo trop volumineuse pour un upload en un seul chunk ({video_size} octets, "
            f"max {MAX_SINGLE_CHUNK_BYTES}). Upload multi-chunk non implémenté."
        )

    creator_info = get_creator_info(sandbox)
    privacy_options = creator_info.get("privacy_level_options") or [FALLBACK_PRIVACY_LEVEL]
    privacy_level = FALLBACK_PRIVACY_LEVEL if FALLBACK_PRIVACY_LEVEL in privacy_options else privacy_options[0]

    init_response = requests.post(
        INIT_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={
            "post_info": {
                "title": title,
                "privacy_level": privacy_level,
                "disable_duet": creator_info.get("duet_disabled", False),
                "disable_comment": disable_comment or creator_info.get("comment_disabled", False),
                "disable_stitch": creator_info.get("stitch_disabled", False),
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
            auth_hint = "python scripts/tiktok_auth.py --sandbox" if sandbox else "python scripts/tiktok_auth.py"
            raise TikTokAuthError(f"Authentification TikTok refusée. Relance `{auth_hint}`.")
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


def get_publish_status(publish_id: str, sandbox: bool = False) -> dict:
    token = load_credentials(sandbox)
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
