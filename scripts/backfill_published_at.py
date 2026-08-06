"""Remplit idea.published_at pour les vidéos déjà publiées, à partir des vraies
dates de publication YouTube (appariées par youtube_video_id). À lancer une
fois après scripts/migrate_add_published_at.py."""

import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from googleapiclient.discovery import build  # noqa: E402

from app import youtube_client  # noqa: E402
from app.app import create_app  # noqa: E402
from app.db import db  # noqa: E402
from app.models import Idea  # noqa: E402


def main() -> int:
    app = create_app()
    with app.app_context():
        creds = youtube_client.load_credentials()
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

        ideas_by_video_id = {
            idea.youtube_video_id: idea
            for idea in Idea.query.filter(Idea.youtube_video_id.isnot(None)).all()
        }
        if not ideas_by_video_id:
            print("Aucune vidéo publiée en base — rien à faire.")
            return 0

        video_ids = list(ideas_by_video_id.keys())
        updated = 0
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i : i + 50]
            resp = youtube.videos().list(part="snippet", id=",".join(batch)).execute()
            for item in resp.get("items", []):
                idea = ideas_by_video_id.get(item["id"])
                if idea is None:
                    continue
                published_at = item["snippet"]["publishedAt"]
                idea.published_at = datetime.strptime(published_at, "%Y-%m-%dT%H:%M:%SZ")
                updated += 1

        db.session.commit()
        print(f"{updated} idée(s) mise(s) à jour avec leur vraie date de publication YouTube.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
