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

    def export_waveform(self, target_sample_rate: int = 16000):
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency: numpy. Install dependencies with:\n"
                "pip install numpy"
            ) from exc

        if not self._chunks:
            return np.empty(0, dtype=np.float32)

        first_chunk = self._chunks[0]
        if first_chunk.sample_width != 2:
            raise ValueError("Only 16-bit PCM audio chunks are currently supported.")
        if target_sample_rate <= 0:
            raise ValueError("target_sample_rate must be greater than 0.")

        pcm = np.frombuffer(self.export_bytes(), dtype=np.int16)
        channels = first_chunk.channels
        if channels > 1:
            pcm = pcm.reshape(-1, channels).mean(axis=1)

        waveform = pcm.astype(np.float32) / 32768.0
        source_sample_rate = first_chunk.sample_rate

        if source_sample_rate == target_sample_rate:
            return waveform

        if waveform.size == 0:
            return waveform

        source_positions = np.arange(waveform.shape[0], dtype=np.float32)
        target_length = max(
            1,
            int(round(waveform.shape[0] * target_sample_rate / source_sample_rate)),
        )
        target_positions = np.linspace(
            0,
            waveform.shape[0] - 1,
            num=target_length,
            dtype=np.float32,
        )
        resampled = np.interp(target_positions, source_positions, waveform)
        return resampled.astype(np.float32)

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
