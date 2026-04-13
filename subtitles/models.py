from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class SegmentResult:
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    language: str
    language_probability: float
    text: str
    segments: list[SegmentResult]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["segments"] = [asdict(segment) for segment in self.segments]
        return payload
