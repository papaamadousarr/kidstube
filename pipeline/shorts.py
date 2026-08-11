import tempfile
from pathlib import Path

from pipeline.assemble.video_builder import assemble_series_video, build_animated_item_clip
from pipeline.config import MUSIC_DIR, OUTPUT_DIR, SHORT_FRAME_SIZE
from pipeline.content.loader import load_series
from pipeline.content.schema import ContentError
from pipeline.tts.piper_engine import synth_to_wav

# Padding généreux pour un Short à un seul mot (group_size=1, modèle des
# 1618 Shorts déjà catalogués) : la durée totale est presque entièrement
# portée par ce padding — sans quoi la vidéo ne dure que le temps de la voix
# off (1-2s). Pour un Short groupé (plusieurs mots), chaque item garde un
# padding plus proche de celui des flashcards (video_builder.PADDING) : la
# durée s'accumule déjà naturellement en concaténant plusieurs items.
SHORT_PADDING = 2.5
GROUPED_ITEM_PADDING = 0.8


def short_output_path(series_key: str, item_index: int) -> Path:
    return OUTPUT_DIR / f"{series_key}_short_{item_index:02d}.mp4"


def build_short(
    series_key: str,
    item_index: int,
    group_size: int = 1,
    out_path: Path | None = None,
) -> Path:
    """group_size=1 : modèle historique, un seul mot par Short (les 1618
    Shorts déjà catalogués restent sur ce modèle). group_size>1 : Shorts plus
    récents qui couvrent plusieurs mots consécutifs de la série pour une
    durée totale plus substantielle."""
    series = load_series(series_key)
    if not (0 <= item_index < len(series.items)):
        raise ContentError(
            f"Index d'item invalide ({item_index}) pour la série '{series_key}' "
            f"({len(series.items)} item(s))."
        )
    group_items = series.items[item_index : item_index + group_size]
    padding = SHORT_PADDING if group_size == 1 else GROUPED_ITEM_PADDING

    out_path = out_path or short_output_path(series_key, item_index)

    with tempfile.TemporaryDirectory(prefix=f"kidstube_short_{series_key}_{item_index:02d}_") as tmp:
        tmp_dir = Path(tmp)

        clips = []
        for i, item in enumerate(group_items):
            audio_path = tmp_dir / f"item_{i:02d}.wav"
            duration = synth_to_wav(item.script, audio_path, series.voice)
            clips.append(
                build_animated_item_clip(
                    item, series, audio_path, duration, tmp_dir, i, size=SHORT_FRAME_SIZE, padding=padding
                )
            )

        candidates = sorted(MUSIC_DIR.glob("*.mp3")) + sorted(MUSIC_DIR.glob("*.wav"))
        music_path = candidates[0] if candidates else None

        assemble_series_video(clips, music_path, out_path)

    return out_path
