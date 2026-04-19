from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from subtitles.engine.buffering.frames import BufferedAudioFrame

if TYPE_CHECKING:
    from subtitles.engine.buffering.snapshot import BufferSnapshot, BufferSnapshotExtractor


class AudioFrameBuffer(ABC):
    @property
    @abstractmethod
    def duration_seconds(self) -> float:
        raise NotImplementedError

    @abstractmethod
    def append(self, frame: BufferedAudioFrame) -> None:
        raise NotImplementedError

    @abstractmethod
    def extract_snapshot(
        self,
        extractor: BufferSnapshotExtractor | None = None,
        *,
        target_sample_rate: int | None = None,
    ) -> BufferSnapshot:
        raise NotImplementedError
