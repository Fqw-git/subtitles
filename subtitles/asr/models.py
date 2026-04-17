from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


class SpeechRecognitionError(RuntimeError):
    """Raised when speech recognition cannot proceed."""


@dataclass(frozen=True)
class SpeechRecognitionConfig:
    model_name: str
    language: str
    beam_size: int
    vad_filter: bool = True
    word_timestamps: bool = False


@dataclass(frozen=True)
class TranscriptWord:
    start: float
    end: float
    word: str
    probability: float | None = None


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str
    words: list[TranscriptWord]


@dataclass(frozen=True)
class TranscriptResult:
    language: str
    language_probability: float
    text: str
    segments: list[TranscriptSegment]
    model_name: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["segments"] = [asdict(segment) for segment in self.segments]
        return payload
