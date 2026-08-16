"""Range dans leurs playlists (type + série) les vidéos déjà publiées sur
YouTube avant la mise en place de app/playlist_manager.py.

Traité par lots (limite par défaut : 15 vidéos/exécution) et reprend
automatiquement où il s'est arrêté (état persisté dans
secrets/playlist_backfill_state.txt) — nécessaire car chaque nouvelle
playlist série coûte du quota API partagé avec la publication vidéo
elle-même ; tout traiter d'un coup peut épuiser le quota du jour et bloquer
la publication normale (constaté : ~98 séries distinctes à couvrir, largement
au-dessus du budget quotidien à elles seules).

Sûr à relancer : add_video_to_playlist vérifie d'abord si la vidéo est déjà
dans la playlist avant d'appeler l'API d'ajout.

Usage :
    python scripts/backfill_playlists.py [--limit N]
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.app import create_app  # noqa: E402
from app.models import Idea  # noqa: E402
from app.playlist_manager import sync_playlists_for_idea  # noqa: E402

STATE_PATH = REPO_ROOT / "secrets" / "playlist_backfill_state.txt"
DEFAULT_LIMIT = 15


def _read_last_processed_id() -> int:
    if not STATE_PATH.exists():
        return 0
    raw = STATE_PATH.read_text().strip()
    return int(raw) if raw else 0


def _write_last_processed_id(idea_id: int) -> None:
    STATE_PATH.parent.mkdir(exist_ok=True)
    STATE_PATH.write_text(str(idea_id))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Nombre de vidéos à traiter dans cette exécution (défaut : {DEFAULT_LIMIT})",
    )
    args = parser.parse_args()

    app = create_app(start_scheduler=False)
    with app.app_context():
        last_processed_id = _read_last_processed_id()
        remaining_total = Idea.query.filter(
            Idea.status == "published",
            Idea.youtube_video_id.isnot(None),
            Idea.id > last_processed_id,
        ).count()
        ideas = (
            Idea.query.filter(
                Idea.status == "published",
                Idea.youtube_video_id.isnot(None),
                Idea.id > last_processed_id,
            )
            .order_by(Idea.id)
            .limit(args.limit)
            .all()
        )

        if not ideas:
            print("Rien à traiter — tout le catalogue publié est déjà rangé en playlists.")
            return 0

        print(f"{remaining_total} vidéo(s) restante(s) au total, {len(ideas)} traitée(s) dans cette exécution.")
        failures = 0
        for i, idea in enumerate(ideas, start=1):
            try:
                sync_playlists_for_idea(idea)
                print(f"[{i}/{len(ideas)}] OK — {idea.title}")
                _write_last_processed_id(idea.id)
            except Exception as exc:
                failures += 1
                print(f"[{i}/{len(ideas)}] ÉCHEC — {idea.title} : {exc}", file=sys.stderr)
                print("Arrêt — probablement un quota épuisé. Relance ce script demain.", file=sys.stderr)
                break

        left = remaining_total - (len(ideas) - failures if failures else len(ideas))
        print(f"\n{len(ideas) - failures} réussite(s) cette exécution. Environ {max(left, 0)} vidéo(s) restante(s).")
        return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
