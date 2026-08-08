import json
from pathlib import Path
from typing import Optional

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = REPO_ROOT / "secrets" / "meta_token.json"

GRAPH_API_VERSION = "v23.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
GRAPH_VIDEO_URL = f"https://graph-video.facebook.com/{GRAPH_API_VERSION}"


class FacebookAuthError(Exception):
    pass


class FacebookUploadError(Exception):
    pass


def is_connected() -> bool:
    return TOKEN_PATH.exists()


def _load_token() -> dict:
    if not TOKEN_PATH.exists():
        raise FacebookAuthError(f"Aucun token trouvé ({TOKEN_PATH}). Lance d'abord `python scripts/meta_auth.py`.")
    return json.loads(TOKEN_PATH.read_text())


def upload_video(
    file_path: Path,
    description: str,
    progress_callback: Optional[callable] = None,
) -> dict:
    """Publie une vidéo sur la Page Facebook via l'Upload API resumable :
    init de session -> envoi des octets -> création du post vidéo avec le
    file_handle renvoyé. Contrairement à Instagram Reels, pas besoin
    d'héberger la vidéo sur une URL publique au préalable."""
    token = _load_token()
    page_id = token["page_id"]
    access_token = token["page_access_token"]
    video_size = Path(file_path).stat().st_size

    init_response = requests.post(
        f"{GRAPH_URL}/{page_id}/uploads",
        params={
            "file_length": video_size,
            "file_type": "video/mp4",
            "access_token": access_token,
        },
        timeout=30,
    )
    init_data = init_response.json()
    if "id" not in init_data:
        raise FacebookUploadError(f"Échec de l'initialisation de l'upload Facebook : {init_data}")
    upload_session_id = init_data["id"]

    with open(file_path, "rb") as f:
        video_bytes = f.read()

    upload_response = requests.post(
        f"{GRAPH_URL}/{upload_session_id}",
        headers={"Authorization": f"OAuth {access_token}"},
        data=video_bytes,
        timeout=180,
    )
    upload_data = upload_response.json()
    if "h" not in upload_data:
        raise FacebookUploadError(f"Échec de l'envoi de la vidéo Facebook : {upload_data}")

    if progress_callback:
        progress_callback(100)

    publish_response = requests.post(
        f"{GRAPH_VIDEO_URL}/{page_id}/videos",
        data={
            "file_handle": upload_data["h"],
            "description": description,
            "access_token": access_token,
        },
        timeout=60,
    )
    publish_data = publish_response.json()
    if "id" not in publish_data:
        raise FacebookUploadError(f"Échec de la publication Facebook : {publish_data}")

    return {"video_id": publish_data["id"]}
