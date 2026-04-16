from __future__ import annotations

from collections import deque

from subtitles.audio import AudioChunk


class SlidingAudioBuffer:
    def __init__(self, max_duration_seconds: float) -> None:
        if max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be greater than 0.")

        self.max_duration_seconds = max_duration_seconds
        self._chunks: deque[AudioChunk] = deque()
        self._duration_seconds = 0.0

    @property
    def duration_seconds(self) -> float:
        return self._duration_seconds

    def append(self, chunk: AudioChunk) -> None:
        self._chunks.append(chunk)
        self._duration_seconds += chunk.end_time - chunk.start_time
        self._trim()

    def is_empty(self) -> bool:
        return not self._chunks

    def export_bytes(self) -> bytes:
        return b"".join(chunk.data for chunk in self._chunks)

    def export_window(self) -> list[AudioChunk]:
        return list(self._chunks)

    def current_time_range(self) -> tuple[float, float]:
        if not self._chunks:
            return (0.0, 0.0)

        return (self._chunks[0].start_time, self._chunks[-1].end_time)

    def _trim(self) -> None:
        while self._chunks and self._duration_seconds > self.max_duration_seconds:
            chunk = self._chunks.popleft()
            self._duration_seconds -= chunk.end_time - chunk.start_time
