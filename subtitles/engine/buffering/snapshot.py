from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from subtitles.audio import AudioChunk
from subtitles.engine.buffering.frames import BufferedAudioFrame
from subtitles.engine.buffering.waveform import chunks_to_waveform


@dataclass(frozen=True)
class BufferSnapshot:
    frames: list[BufferedAudioFrame]
    chunks: list[AudioChunk]
    waveform: object
    window_start: float
    window_end: float


class BufferSnapshotExtractor(ABC):
    @abstractmethod
    def extract(
        self,
        frames: list[BufferedAudioFrame],
        *,
        target_sample_rate: int = 16000,
    ) -> BufferSnapshot:
        raise NotImplementedError

    def _build_snapshot(
        self,
        frames: list[BufferedAudioFrame],
        *,
        target_sample_rate: int,
    ) -> BufferSnapshot:
        chunks = [frame.chunk for frame in frames]
        if not chunks:
            return BufferSnapshot(
                frames=[],
                chunks=[],
                waveform=chunks_to_waveform([], target_sample_rate=target_sample_rate),
                window_start=0.0,
                window_end=0.0,
            )

        return BufferSnapshot(
            frames=frames,
            chunks=chunks,
            waveform=chunks_to_waveform(chunks, target_sample_rate=target_sample_rate),
            window_start=chunks[0].start_time,
            window_end=chunks[-1].end_time,
        )


class LatestWindowSnapshotExtractor(BufferSnapshotExtractor):
    def extract(
        self,
        frames: list[BufferedAudioFrame],
        *,
        target_sample_rate: int = 16000,
    ) -> BufferSnapshot:
        return self._build_snapshot(frames, target_sample_rate=target_sample_rate)


class SpeechAwareSnapshotExtractor(BufferSnapshotExtractor):
    def __init__(
        self,
        *,
        max_window_seconds: float,
        leading_context_seconds: float = 0.6,
        trailing_context_seconds: float = 0.3,
    ) -> None:
        self.max_window_seconds = max_window_seconds
        self.leading_context_seconds = leading_context_seconds
        self.trailing_context_seconds = trailing_context_seconds

    def extract(
        self,
        frames: list[BufferedAudioFrame],
        *,
        target_sample_rate: int = 16000,
    ) -> BufferSnapshot:
        if not frames:
            return self._build_snapshot([], target_sample_rate=target_sample_rate)

        window_end = frames[-1].chunk.end_time
        window_floor = max(window_end - self.max_window_seconds, frames[0].chunk.start_time)
        candidate_frames = [
            frame for frame in frames if frame.chunk.end_time > window_floor
        ]
        if not candidate_frames:
            return self._build_snapshot([], target_sample_rate=target_sample_rate)

        speech_indexes = [
            index for index, frame in enumerate(candidate_frames) if frame.is_voice_related
        ]
        if not speech_indexes:
            return self._build_snapshot(candidate_frames, target_sample_rate=target_sample_rate)

        first_speech_index = speech_indexes[0]
        last_speech_index = speech_indexes[-1]

        selected_start_index = first_speech_index
        context_budget = self.leading_context_seconds
        while selected_start_index > 0 and context_budget > 0:
            previous_frame = candidate_frames[selected_start_index - 1]
            frame_duration = previous_frame.chunk.end_time - previous_frame.chunk.start_time
            if frame_duration <= 0:
                selected_start_index -= 1
                continue
            context_budget -= frame_duration
            selected_start_index -= 1

        selected_end_index = last_speech_index
        trailing_budget = self.trailing_context_seconds
        while selected_end_index + 1 < len(candidate_frames) and trailing_budget > 0:
            next_frame = candidate_frames[selected_end_index + 1]
            frame_duration = next_frame.chunk.end_time - next_frame.chunk.start_time
            if frame_duration <= 0:
                selected_end_index += 1
                continue
            trailing_budget -= frame_duration
            selected_end_index += 1

        selected_frames = candidate_frames[selected_start_index : selected_end_index + 1]
        return self._build_snapshot(selected_frames, target_sample_rate=target_sample_rate)
