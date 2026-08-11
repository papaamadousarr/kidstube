import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

from pipeline.assemble.video_builder import (
    assemble_series_video,
    build_animated_item_clip,
    build_intro_clip,
    build_outro_clip,
)
from pipeline.config import MUSIC_DIR, OUTPUT_DIR
from pipeline.content.higgsfield_loader import list_higgsfield_series
from pipeline.content.loader import list_series, load_series
from pipeline.content.schema import ContentError
from pipeline.shorts import build_short
from pipeline.tts.piper_engine import synth_to_wav
from pipeline.videogen.builder import build_higgsfield_series
from pipeline.videogen.higgsfield_client import HiggsfieldError


def build_series(
    series_key: str,
    voice: str | None = None,
    use_music: bool = True,
    out_path: Path | None = None,
) -> Path:
    series = load_series(series_key)
    if voice:
        series.voice = voice

    out_path = out_path or (OUTPUT_DIR / f"{series_key}.mp4")
    t0 = time.time()

    with tempfile.TemporaryDirectory(prefix=f"kidstube_{series_key}_") as tmp:
        tmp_dir = Path(tmp)

        print("[1/4] Intro...")
        intro_clip = build_intro_clip(series, tmp_dir)

        print(f"[2/4] {len(series.items)} items (TTS + flashcards)...")
        item_clips = []
        for i, item in enumerate(series.items):
            audio_path = tmp_dir / f"item_{i:02d}.wav"
            duration = synth_to_wav(item.script, audio_path, series.voice)
            item_clips.append(build_animated_item_clip(item, series, audio_path, duration, tmp_dir, i))
            print(f"    - {item.name} ok ({duration:.2f}s)")

        print("[3/4] Outro...")
        outro_clip = build_outro_clip(series, tmp_dir)

        print("[4/4] Assemblage final...")
        music_path = None
        if use_music:
            candidates = sorted(MUSIC_DIR.glob("*.mp3")) + sorted(MUSIC_DIR.glob("*.wav"))
            music_path = candidates[0] if candidates else None
            if music_path is None:
                print("    (pas de musique trouvée dans pipeline/assets/music/, on continue sans)")

        assemble_series_video([intro_clip, *item_clips, outro_clip], music_path, out_path)

    print(f"Terminé en {time.time() - t0:.1f}s -> {out_path}")
    return out_path


def cmd_build(args: argparse.Namespace) -> int:
    try:
        build_series(
            args.series_key,
            voice=args.voice,
            use_music=not args.no_music,
            out_path=Path(args.out) if args.out else None,
        )
    except ContentError as exc:
        print(f"Erreur de contenu : {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_build_higgsfield(args: argparse.Namespace) -> int:
    try:
        build_higgsfield_series(args.series_key, aspect_ratio=args.aspect_ratio)
    except ContentError as exc:
        print(f"Erreur de contenu : {exc}", file=sys.stderr)
        return 1
    except HiggsfieldError as exc:
        print(f"Erreur Higgsfield : {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_build_short(args: argparse.Namespace) -> int:
    try:
        build_short(args.series_key, args.item_index, group_size=args.group_size)
    except ContentError as exc:
        print(f"Erreur de contenu : {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    for key in list_series():
        print(key)
    return 0


def cmd_list_higgsfield(_args: argparse.Namespace) -> int:
    for key in list_higgsfield_series():
        print(key)
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    if args.series_key:
        target = OUTPUT_DIR / f"{args.series_key}.mp4"
        if target.exists():
            target.unlink()
            print(f"Supprimé : {target}")
        else:
            print(f"Rien à supprimer pour '{args.series_key}'")
    else:
        if OUTPUT_DIR.exists():
            shutil.rmtree(OUTPUT_DIR)
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Nettoyé : {OUTPUT_DIR}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline", description="Génère des vidéos pour enfants à partir de séries de contenu.")
    sub = parser.add_subparsers(dest="command", required=True)

    build_parser = sub.add_parser("build", help="Génère une vidéo complète pour une série")
    build_parser.add_argument("series_key")
    build_parser.add_argument("--voice", default=None, help="Nom de la voix Piper à utiliser")
    build_parser.add_argument("--no-music", action="store_true", help="Ne pas ajouter de musique de fond")
    build_parser.add_argument("--out", default=None, help="Chemin de sortie du MP4")
    build_parser.set_defaults(func=cmd_build)

    build_higgsfield_parser = sub.add_parser(
        "build-higgsfield", help="Génère une vidéo réaliste (Higgsfield) pour une série de scènes"
    )
    build_higgsfield_parser.add_argument("series_key")
    build_higgsfield_parser.add_argument(
        "--aspect-ratio", default=None, help="Format vidéo (ex. 16:9), sinon celui défini dans la série"
    )
    build_higgsfield_parser.set_defaults(func=cmd_build_higgsfield)

    build_short_parser = sub.add_parser(
        "build-short", help="Génère un Short (vertical) pour un ou plusieurs items d'une série existante"
    )
    build_short_parser.add_argument("series_key")
    build_short_parser.add_argument("item_index", type=int)
    build_short_parser.add_argument(
        "--group-size", type=int, default=1, help="Nombre de mots consécutifs à couvrir dans ce Short (défaut : 1)"
    )
    build_short_parser.set_defaults(func=cmd_build_short)

    list_parser = sub.add_parser("list", help="Liste les séries de contenu disponibles")
    list_parser.set_defaults(func=cmd_list)

    list_higgsfield_parser = sub.add_parser(
        "list-higgsfield", help="Liste les séries de scènes Higgsfield disponibles"
    )
    list_higgsfield_parser.set_defaults(func=cmd_list_higgsfield)

    clean_parser = sub.add_parser("clean", help="Supprime les vidéos générées")
    clean_parser.add_argument("series_key", nargs="?", default=None)
    clean_parser.set_defaults(func=cmd_clean)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
