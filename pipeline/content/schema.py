from dataclasses import dataclass, field
from typing import Optional


class ContentError(ValueError):
    pass


@dataclass
class Item:
    name: str
    script: str
    icon: Optional[str] = None
    accent_color: Optional[str] = None


@dataclass
class SeriesConfig:
    key: str
    title: str
    voice: str
    background_color: str
    intro_text: str
    items: list[Item] = field(default_factory=list)
