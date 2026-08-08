import os
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv
from requests_oauthlib import OAuth1

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / "secrets" / ".env")

API_KEY = os.getenv("X_API_KEY")
API_SECRET = os.getenv("X_API_SECRET")
ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")

# Endpoint v1.1 "command" (INIT/APPEND/FINALIZE/STATUS) — celui qui fonctionne
# de façon fiable avec OAuth 1.0a pour l'upload média ; les nouveaux endpoints
# /2/media/upload/{initialize,append,finalize} posent des soucis d'auth
# documentés (403 en OAuth2, comportement instable en OAuth1) au moment de
# l'écriture de ce client.
MEDIA_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
TWEET_URL = "https://api.x.com/2/tweets"

MAX_VIDEO_BYTES = 512 * 1024 * 1024
MAX_DURATION_SECONDS = 140
CHUNK_SIZE = 4 * 1024 * 1024


class XAuthError(Exception):
    pass


class XUploadError(Exception):
    pass


def is_connected() -> bool:
    return all([API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET])


def _auth() -> OAuth1:
    if not is_connected():
        raise XAuthError(
            "Credentials X manquants dans secrets/.env "
            "(X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET)."
        )
    return OAuth1(API_KEY, API_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)


def upload_video(file_path: Path, progress_callback: Optional[callable] = None) -> dict:
    auth = _auth()
    video_size = Path(file_path).stat().st_size

    if video_size > MAX_VIDEO_BYTES:
        raise XUploadError(f"Vidéo trop volumineuse ({video_size} octets, max {MAX_VIDEO_BYTES}).")

    init_response = requests.post(
        MEDIA_UPLOAD_URL,
        auth=auth,
        data={
            "command": "INIT",
            "total_bytes": video_size,
            "media_type": "video/mp4",
            "media_category": "tweet_video",
        },
        timeout=30,
    )
    if init_response.status_code not in (200, 201, 202):
        raise XUploadError(f"Échec INIT upload X ({init_response.status_code}) : {init_response.text}")
    media_id = init_response.json()["media_id_string"]

    with open(file_path, "rb") as f:
        segment_index = 0
        uploaded = 0
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            append_response = requests.post(
                MEDIA_UPLOAD_URL,
                auth=auth,
                data={"command": "APPEND", "media_id": media_id, "segment_index": segment_index},
                files={"media": chunk},
                timeout=60,
            )
            if append_response.status_code not in (200, 201, 202, 204):
                raise XUploadError(f"Échec APPEND upload X ({append_response.status_code}) : {append_response.text}")
            uploaded += len(chunk)
            segment_index += 1
            if progress_callback:
                progress_callback(int(uploaded / video_size * 100))

    finalize_response = requests.post(
        MEDIA_UPLOAD_URL,
        auth=auth,
        data={"command": "FINALIZE", "media_id": media_id},
        timeout=30,
    )
    if finalize_response.status_code not in (200, 201):
        raise XUploadError(f"Échec FINALIZE upload X ({finalize_response.status_code}) : {finalize_response.text}")

    processing_info = finalize_response.json().get("processing_info")
    while processing_info and processing_info.get("state") in ("pending", "in_progress"):
        time.sleep(processing_info.get("check_after_secs", 3))
        status_response = requests.get(
            MEDIA_UPLOAD_URL,
            auth=auth,
            params={"command": "STATUS", "media_id": media_id},
            timeout=30,
        )
        processing_info = status_response.json().get("processing_info")
        if processing_info and processing_info.get("state") == "failed":
            raise XUploadError(f"Traitement vidéo X échoué : {processing_info.get('error')}")

    if progress_callback:
        progress_callback(100)

    return {"media_id": media_id}


def post_tweet(text: str, media_id: str) -> dict:
    auth = _auth()
    response = requests.post(
        TWEET_URL,
        auth=auth,
        json={"text": text, "media": {"media_ids": [media_id]}},
        timeout=30,
    )
    data = response.json()
    if response.status_code not in (200, 201):
        raise XUploadError(f"Échec de la publication du tweet ({response.status_code}) : {data}")
    return data.get("data", {})
