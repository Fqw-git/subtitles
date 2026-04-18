from __future__ import annotations

from collections import deque
import threading

from subtitles.engine.buffering.frames import BufferedAudioFrame
from subtitles.engine.buffering.snapshot import (
    BufferSnapshot,
    BufferSnapshotExtractor,
    LatestWindowSnapshotExtractor,
)


class SlidingAudioBuffer:
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

    def is_empty(self) -> bool:
        with self._lock:
            return not self._frames

    def export_window(self) -> list:
        with self._lock:
            return [frame.chunk for frame in self._frames]

    def export_frames(self) -> list[BufferedAudioFrame]:
        with self._lock:
            return list(self._frames)

    def current_time_range(self) -> tuple[float, float]:
        with self._lock:
            if not self._frames:
                return (0.0, 0.0)
            return (self._frames[0].chunk.start_time, self._frames[-1].chunk.end_time)

    def export_snapshot(self, target_sample_rate: int = 16000):
        with self._lock:
            frames = list(self._frames)
        extractor = LatestWindowSnapshotExtractor()
        return extractor.extract(frames, target_sample_rate=target_sample_rate)

    def extract_snapshot(
        self,
        extractor: BufferSnapshotExtractor,
        *,
        target_sample_rate: int = 16000,
    ) -> BufferSnapshot:
        with self._lock:
            frames = list(self._frames)
        return extractor.extract(frames, target_sample_rate=target_sample_rate)

    def _trim(self) -> None:
        while self._frames and self._duration_seconds > self.max_duration_seconds:
            frame = self._frames.popleft()
            self._duration_seconds -= frame.chunk.end_time - frame.chunk.start_time
