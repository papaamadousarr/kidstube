from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PodcastSegment:
    narration: str
    image_prompt: str


@dataclass
class PodcastSeriesConfig:
    key: str
    title: str
    voice: str
    linked_series_key: Optional[str] = None
    segments: list[PodcastSegment] = field(default_factory=list)
