import tempfile
from pathlib import Path

from pipeline.assemble.video_builder import assemble_series_video, build_item_clip
from pipeline.config import MUSIC_DIR, OUTPUT_DIR, SHORT_FRAME_SIZE
from pipeline.content.loader import load_series
from pipeline.content.schema import ContentError
from pipeline.render.frame_builder import build_flashcard
from pipeline.tts.piper_engine import synth_to_wav


def short_output_path(series_key: str, item_index: int) -> Path:
    return OUTPUT_DIR / f"{series_key}_short_{item_index:02d}.mp4"


def build_short(series_key: str, item_index: int, out_path: Path | None = None) -> Path:
    series = load_series(series_key)
    if not (0 <= item_index < len(series.items)):
        raise ContentError(
            f"Index d'item invalide ({item_index}) pour la série '{series_key}' "
            f"({len(series.items)} item(s))."
        )
    item = series.items[item_index]

    out_path = out_path or short_output_path(series_key, item_index)

    with tempfile.TemporaryDirectory(prefix=f"kidstube_short_{series_key}_{item_index:02d}_") as tmp:
        tmp_dir = Path(tmp)

        audio_path = tmp_dir / "item.wav"
        duration = synth_to_wav(item.script, audio_path, series.voice)

        frame_path = tmp_dir / "item.png"
        build_flashcard(item, series, size=SHORT_FRAME_SIZE).save(frame_path)

        clip = build_item_clip(frame_path, audio_path, duration, size=SHORT_FRAME_SIZE)

        candidates = sorted(MUSIC_DIR.glob("*.mp3")) + sorted(MUSIC_DIR.glob("*.wav"))
        music_path = candidates[0] if candidates else None

        assemble_series_video([clip], music_path, out_path)

    return out_path
