from __future__ import annotations

from collections import deque
import threading

from subtitles.engine.buffering.base import AudioFrameBuffer
from subtitles.engine.buffering.frames import BufferedAudioFrame
from subtitles.engine.buffering.snapshot import (
    BufferSnapshot,
    BufferSnapshotExtractor,
    LatestWindowSnapshotExtractor,
)


class SlidingAudioBuffer(AudioFrameBuffer):
    def __init__(self, max_duration_seconds: float) -> None:
        if max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be greater than 0.")

        self.max_duration_seconds = max_duration_seconds
        self._frames: deque[BufferedAudioFrame] = deque()
        self._duration_seconds = 0.0
        self._lock = threading.RLock()

    @property
    def duration_seconds(self) -> float:
        with self._lock:
            return self._duration_seconds

    def append(self, frame: BufferedAudioFrame) -> None:
        with self._lock:
            self._frames.append(frame)
            self._duration_seconds += frame.chunk.end_time - frame.chunk.start_time
            self._trim()

    def extract_snapshot(
        self,
        extractor: BufferSnapshotExtractor | None = None,
        *,
        target_sample_rate: int | None = None,
    ) -> BufferSnapshot:
        with self._lock:
            frames = list(self._frames)
        resolved_sample_rate = 16000 if target_sample_rate is None else target_sample_rate
        resolved_extractor = extractor or LatestWindowSnapshotExtractor()
        return resolved_extractor.extract(frames, target_sample_rate=resolved_sample_rate)

    def _trim(self) -> None:
        while self._frames and self._duration_seconds > self.max_duration_seconds:
            frame = self._frames.popleft()
            self._duration_seconds -= frame.chunk.end_time - frame.chunk.start_time
