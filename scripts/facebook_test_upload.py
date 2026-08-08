"""Test manuel de publication vidéo sur une Page Facebook.

Prérequis : `python scripts/meta_auth.py` déjà lancé avec succès (crée
secrets/meta_token.json).

Usage :
    python scripts/facebook_test_upload.py chemin/vers/video.mp4 "Description"
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app import facebook_client  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print(f"Usage : python {sys.argv[0]} chemin/vers/video.mp4 \"Description\"", file=sys.stderr)
        return 1

    video_path = Path(sys.argv[1])
    description = sys.argv[2]

    if not video_path.exists():
        print(f"Fichier introuvable : {video_path}", file=sys.stderr)
        return 1

    print("Upload et publication vers la Page Facebook...")
    result = facebook_client.upload_video(video_path, description)
    print(f"Résultat : {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
