"""Test manuel de publication vidéo sur X (upload + tweet).

Prérequis dans secrets/.env :
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
(générés directement dans le portail développeur X pour ton propre compte —
pas de flow OAuth avec navigateur nécessaire pour cet usage single-account.)

Usage :
    python scripts/x_test_upload.py chemin/vers/video.mp4 "Texte du tweet"
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app import x_client  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print(f"Usage : python {sys.argv[0]} chemin/vers/video.mp4 \"Texte du tweet\"", file=sys.stderr)
        return 1

    video_path = Path(sys.argv[1])
    text = sys.argv[2]

    if not video_path.exists():
        print(f"Fichier introuvable : {video_path}", file=sys.stderr)
        return 1

    print("[1/2] Upload de la vidéo vers X...")
    result = x_client.upload_video(video_path, progress_callback=lambda pct: print(f"      {pct}%"))
    media_id = result["media_id"]
    print(f"      media_id = {media_id}")

    print("[2/2] Publication du tweet...")
    tweet = x_client.post_tweet(text, media_id)
    print(f"Résultat : {tweet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
