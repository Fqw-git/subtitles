from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from subtitles.engine.buffering.base import AudioFrameBuffer
from subtitles.engine.buffering.frames import BufferedAudioFrame
from subtitles.engine.stabilizer.models import TranscriptDelta

if TYPE_CHECKING:
    from subtitles.engine.buffering.snapshot import (
        BufferSnapshot,
        BufferSnapshotExtractor,
        CursorSnapshotExtractor,
    )


@dataclass
class RecognitionCursor:
    committed_end_time: float = 0.0
    provisional_end_time: float = 0.0
    last_snapshot_start_time: float = 0.0

    def mark_snapshot(self, *, start_time: float, end_time: float) -> None:
        self.last_snapshot_start_time = start_time
        if end_time > self.provisional_end_time:
            self.provisional_end_time = end_time

    def advance_committed(self, end_time: float) -> None:
        if end_time > self.committed_end_time:
            self.committed_end_time = end_time
        if self.provisional_end_time < self.committed_end_time:
            self.provisional_end_time = self.committed_end_time


@dataclass
class RecognitionBuffer(AudioFrameBuffer):
    audio_buffer: AudioFrameBuffer
    max_window_seconds: float
    target_sample_rate: int = 16000
    cursor: RecognitionCursor = field(default_factory=RecognitionCursor)
    snapshot_extractor: CursorSnapshotExtractor | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        from subtitles.engine.buffering.snapshot import CursorSnapshotExtractor

        self.snapshot_extractor = CursorSnapshotExtractor(
            cursor=self.cursor,
            max_window_seconds=self.max_window_seconds,
        )

    @property
    def duration_seconds(self) -> float:
        return self.audio_buffer.duration_seconds

    def append(self, frame: BufferedAudioFrame) -> None:
        self.audio_buffer.append(frame)

    def extract_snapshot(
        self,
        extractor: BufferSnapshotExtractor | None = None,
        *,
        target_sample_rate: int | None = None,
    ) -> BufferSnapshot:
        resolved_sample_rate = (
            self.target_sample_rate if target_sample_rate is None else target_sample_rate
        )
        resolved_extractor = extractor or self.snapshot_extractor
        if resolved_extractor is None:
            raise RuntimeError("snapshot_extractor is not initialized.")
        return self.audio_buffer.extract_snapshot(
            resolved_extractor,
            target_sample_rate=resolved_sample_rate,
        )

    def mark_snapshot(self, *, start_time: float, end_time: float) -> None:
        self.cursor.mark_snapshot(start_time=start_time, end_time=end_time)

    def apply_delta(self, delta: TranscriptDelta) -> None:
        self.cursor.advance_committed(delta.committed_end_time)
        if delta.provisional_end_time > self.cursor.provisional_end_time:
            self.cursor.provisional_end_time = delta.provisional_end_time
