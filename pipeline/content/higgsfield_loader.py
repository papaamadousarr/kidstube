from pathlib import Path

import yaml

from pipeline.config import HIGGSFIELD_DATA_DIR
from pipeline.content.higgsfield_schema import HiggsfieldSeriesConfig, Scene
from pipeline.content.schema import ContentError

REQUIRED_SERIES_KEYS = ("key", "title", "voice", "aspect_ratio")
REQUIRED_SCENE_KEYS = ("narration", "prompt")


def list_higgsfield_series(data_dir: Path = HIGGSFIELD_DATA_DIR) -> list[str]:
    if not data_dir.exists():
        return []
    return sorted(p.stem for p in data_dir.glob("*.yaml"))


def load_higgsfield_series(name: str, data_dir: Path = HIGGSFIELD_DATA_DIR) -> HiggsfieldSeriesConfig:
    path = data_dir / f"{name}.yaml"
    if not path.exists():
        available = ", ".join(list_higgsfield_series(data_dir)) or "(aucune)"
        raise ContentError(f"Série Higgsfield inconnue '{name}'. Séries disponibles : {available}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ContentError(f"YAML invalide dans {path}: {exc}") from exc

    if not isinstance(raw, dict) or "higgsfield_series" not in raw or "scenes" not in raw:
        raise ContentError(f"{path} doit contenir les clés 'higgsfield_series' et 'scenes'")

    series_raw = raw["higgsfield_series"]
    missing = [k for k in REQUIRED_SERIES_KEYS if k not in series_raw]
    if missing:
        raise ContentError(f"{path}: clés manquantes dans 'higgsfield_series': {missing}")

    scenes_raw = raw["scenes"]
    if not isinstance(scenes_raw, list) or not scenes_raw:
        raise ContentError(f"{path}: 'scenes' doit être une liste non vide")

    scenes: list[Scene] = []
    for i, scene_raw in enumerate(scenes_raw):
        missing_scene = [k for k in REQUIRED_SCENE_KEYS if k not in scene_raw]
        if missing_scene:
            raise ContentError(f"{path}: scène #{i} manque les clés {missing_scene}")
        scenes.append(
            Scene(
                narration=str(scene_raw["narration"]),
                prompt=str(scene_raw["prompt"]),
                text_overlay=scene_raw.get("text_overlay"),
            )
        )

    return HiggsfieldSeriesConfig(
        key=series_raw["key"],
        title=series_raw["title"],
        voice=series_raw["voice"],
        aspect_ratio=series_raw["aspect_ratio"],
        scenes=scenes,
    )
