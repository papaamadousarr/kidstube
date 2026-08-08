import json
import time
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
TOKEN_PATH = REPO_ROOT / "secrets" / "meta_token.json"

GRAPH_API_VERSION = "v23.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 180


class InstagramAuthError(Exception):
    pass


class InstagramUploadError(Exception):
    pass


def is_connected() -> bool:
    if not TOKEN_PATH.exists():
        return False
    return "ig_user_id" in json.loads(TOKEN_PATH.read_text())


def _load_token() -> dict:
    if not TOKEN_PATH.exists():
        raise InstagramAuthError(f"Aucun token trouvé ({TOKEN_PATH}). Lance d'abord `python scripts/meta_auth.py`.")
    token = json.loads(TOKEN_PATH.read_text())
    if "ig_user_id" not in token:
        raise InstagramAuthError(
            "Aucun compte Instagram lié dans meta_token.json. Lie un compte Instagram "
            "Business/Creator à la Page (Meta Business Suite -> Comptes liés), puis "
            "relance `python scripts/meta_auth.py`."
        )
    return token


def publish_reel(video_url: str, caption: str) -> dict:
    """Publie un Reel à partir d'une vidéo déjà hébergée sur une URL HTTPS
    publique — contrairement à YouTube/TikTok/X/Facebook, l'API Instagram
    Content Publishing n'accepte PAS l'envoi direct des octets du fichier,
    seulement une URL qu'elle va elle-même télécharger. Il faut donc héberger
    la vidéo quelque part de public avant d'appeler cette fonction (pas géré
    ici — c'est à l'appelant de le faire, ex. un bucket S3/R2, ou un dossier
    servi publiquement)."""
    token = _load_token()
    ig_user_id = token["ig_user_id"]
    access_token = token["page_access_token"]

    create_response = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": access_token,
        },
        timeout=30,
    )
    create_data = create_response.json()
    if "id" not in create_data:
        raise InstagramUploadError(f"Échec de la création du conteneur Reel : {create_data}")
    container_id = create_data["id"]

    deadline = time.time() + POLL_TIMEOUT_SECONDS
    status_code = "IN_PROGRESS"
    while time.time() < deadline:
        status_response = requests.get(
            f"{GRAPH_URL}/{container_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=30,
        )
        status_code = status_response.json().get("status_code", "IN_PROGRESS")
        if status_code in ("FINISHED", "ERROR"):
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    if status_code != "FINISHED":
        raise InstagramUploadError(f"Traitement du Reel non abouti (statut : {status_code}).")

    publish_response = requests.post(
        f"{GRAPH_URL}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": access_token},
        timeout=30,
    )
    publish_data = publish_response.json()
    if "id" not in publish_data:
        raise InstagramUploadError(f"Échec de la publication du Reel : {publish_data}")

    return {"media_id": publish_data["id"]}
