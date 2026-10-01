from __future__ import annotations

from dataclasses import dataclass, field

from collectors.base import Item


@dataclass
class ItemAnalysis:
    item: Item
    overall: str                                   # positive | neutral | negative
    dimensions: dict[str, tuple[str, str]] = field(default_factory=dict)  # key -> (sentiment, verbatim quote)
    praise: list[str] = field(default_factory=list)
    complaints: list[str] = field(default_factory=list)
    competitors: list[str] = field(default_factory=list)
