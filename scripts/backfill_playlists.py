"""Range dans leurs playlists (type + série) les vidéos déjà publiées sur
YouTube avant la mise en place de app/playlist_manager.py.

Sûr à relancer plusieurs fois : add_video_to_playlist vérifie d'abord si la
vidéo est déjà dans la playlist avant d'appeler l'API d'ajout.

Usage :
    python scripts/backfill_playlists.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.app import create_app  # noqa: E402
from app.models import Idea  # noqa: E402
from app.playlist_manager import sync_playlists_for_idea  # noqa: E402


def main() -> int:
    app = create_app(start_scheduler=False)
    with app.app_context():
        ideas = Idea.query.filter(
            Idea.status == "published",
            Idea.youtube_video_id.isnot(None),
        ).all()

        print(f"{len(ideas)} vidéo(s) publiée(s) à ranger en playlists.")
        failures = 0
        for i, idea in enumerate(ideas, start=1):
            try:
                sync_playlists_for_idea(idea)
                print(f"[{i}/{len(ideas)}] OK — {idea.title}")
            except Exception as exc:
                failures += 1
                print(f"[{i}/{len(ideas)}] ÉCHEC — {idea.title} : {exc}", file=sys.stderr)

        print(f"\nTerminé. {len(ideas) - failures} réussite(s), {failures} échec(s).")
        return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
