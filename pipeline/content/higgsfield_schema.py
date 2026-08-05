from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Scene:
    narration: str
    prompt: str
    text_overlay: Optional[str] = None


@dataclass
class HiggsfieldSeriesConfig:
    key: str
    title: str
    voice: str
    aspect_ratio: str
    scenes: list[Scene] = field(default_factory=list)
