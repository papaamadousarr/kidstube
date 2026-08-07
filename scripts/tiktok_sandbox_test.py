"""Test manuel du flow Content Posting API en Sandbox — à lancer toi-même,
écran en cours d'enregistrement, pour produire la vidéo de démo exigée par
l'App Review TikTok.

Prérequis :
1. Ton compte TikTok ajouté comme Target User dans l'onglet Sandbox du
   portail développeur.
2. `python scripts/tiktok_auth.py --sandbox` déjà lancé avec succès (crée
   secrets/tiktok_sandbox_token.json).

Usage :
    python scripts/tiktok_sandbox_test.py chemin/vers/video.mp4 "Titre de test"
"""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app import tiktok_client  # noqa: E402

POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 120


def main() -> int:
    if len(sys.argv) < 3:
        print(f"Usage : python {sys.argv[0]} chemin/vers/video.mp4 \"Titre de test\"", file=sys.stderr)
        return 1

    video_path = Path(sys.argv[1])
    title = sys.argv[2]

    if not video_path.exists():
        print(f"Fichier introuvable : {video_path}", file=sys.stderr)
        return 1

    print(f"[1/3] INIT — envoi de la requête à l'API TikTok pour « {title} »...")
    result = tiktok_client.upload_video(video_path, title, sandbox=True)
    publish_id = result["publish_id"]
    print(f"      publish_id = {publish_id}")

    print("[2/3] UPLOAD terminé, vérification du statut de publication...")
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while time.time() < deadline:
        status = tiktok_client.get_publish_status(publish_id, sandbox=True)
        print(f"      statut actuel : {status.get('status')}")
        if status.get("status") in ("PUBLISH_COMPLETE", "FAILED"):
            break
        time.sleep(POLL_INTERVAL_SECONDS)

    print(f"[3/3] Résultat final : {status}")
    return 0 if status.get("status") == "PUBLISH_COMPLETE" else 1


if __name__ == "__main__":
    sys.exit(main())
