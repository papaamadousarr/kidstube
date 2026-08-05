from pathlib import Path

import yaml

from pipeline.config import PODCAST_DATA_DIR
from pipeline.content.podcast_schema import PodcastSegment, PodcastSeriesConfig
from pipeline.content.schema import ContentError

REQUIRED_SERIES_KEYS = ("key", "title", "voice")
REQUIRED_SEGMENT_KEYS = ("narration", "image_prompt")


def list_podcast_series(data_dir: Path = PODCAST_DATA_DIR) -> list[str]:
    if not data_dir.exists():
        return []
    return sorted(p.stem for p in data_dir.glob("*.yaml"))


def load_podcast_series(name: str, data_dir: Path = PODCAST_DATA_DIR) -> PodcastSeriesConfig:
    path = data_dir / f"{name}.yaml"
    if not path.exists():
        available = ", ".join(list_podcast_series(data_dir)) or "(aucun)"
        raise ContentError(f"Podcast inconnu '{name}'. Podcasts disponibles : {available}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ContentError(f"YAML invalide dans {path}: {exc}") from exc

    if not isinstance(raw, dict) or "podcast_series" not in raw or "segments" not in raw:
        raise ContentError(f"{path} doit contenir les clés 'podcast_series' et 'segments'")

    series_raw = raw["podcast_series"]
    missing = [k for k in REQUIRED_SERIES_KEYS if k not in series_raw]
    if missing:
        raise ContentError(f"{path}: clés manquantes dans 'podcast_series': {missing}")

    segments_raw = raw["segments"]
    if not isinstance(segments_raw, list) or not segments_raw:
        raise ContentError(f"{path}: 'segments' doit être une liste non vide")

    segments: list[PodcastSegment] = []
    for i, seg_raw in enumerate(segments_raw):
        missing_seg = [k for k in REQUIRED_SEGMENT_KEYS if k not in seg_raw]
        if missing_seg:
            raise ContentError(f"{path}: segment #{i} manque les clés {missing_seg}")
        segments.append(
            PodcastSegment(narration=str(seg_raw["narration"]), image_prompt=str(seg_raw["image_prompt"]))
        )

    return PodcastSeriesConfig(
        key=series_raw["key"],
        title=series_raw["title"],
        voice=series_raw["voice"],
        linked_series_key=series_raw.get("linked_series_key"),
        segments=segments,
    )
