from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from subtitles.audio import AudioChunk
from subtitles.engine.buffering.frames import BufferedAudioFrame, VoiceActivityState
from subtitles.engine.buffering.recognition import RecognitionCursor
from subtitles.engine.buffering.waveform import chunks_to_waveform


@dataclass(frozen=True)
class BufferSnapshot:
    frames: list[BufferedAudioFrame]
    chunks: list[AudioChunk]
    waveform: object
    window_start: float
    window_end: float
    committed_end_time: float = 0.0
    starts_with_speech_start: bool = False
    selection_reason: str = ""
    anchor_time: float = 0.0


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
                committed_end_time=0.0,
                starts_with_speech_start=False,
            )

        return BufferSnapshot(
            frames=frames,
            chunks=chunks,
            waveform=chunks_to_waveform(chunks, target_sample_rate=target_sample_rate),
            window_start=chunks[0].start_time,
            window_end=chunks[-1].end_time,
            committed_end_time=0.0,
            starts_with_speech_start=self._starts_with_speech_start(frames),
        )

    def _frame_start_time(self, frame: BufferedAudioFrame) -> float:
        return frame.chunk.start_time

    def _frame_end_time(self, frame: BufferedAudioFrame) -> float:
        return frame.chunk.end_time

    def _frame_duration_seconds(self, frame: BufferedAudioFrame) -> float:
        return self._frame_end_time(frame) - self._frame_start_time(frame)

    def _frames_start_time(self, frames: list[BufferedAudioFrame]) -> float:
        if not frames:
            return 0.0
        return self._frame_start_time(frames[0])

    def _frames_end_time(self, frames: list[BufferedAudioFrame]) -> float:
        if not frames:
            return 0.0
        return self._frame_end_time(frames[-1])

    def _find_first_frame_ending_after(
        self,
        frames: list[BufferedAudioFrame],
        threshold_time: float,
    ) -> int | None:
        for index, frame in enumerate(frames):
            if self._frame_end_time(frame) > threshold_time:
                return index
        return None

    def _find_last_frame_ending_at_or_before(
        self,
        frames: list[BufferedAudioFrame],
        threshold_time: float,
    ) -> int | None:
        matched_index: int | None = None
        for index, frame in enumerate(frames):
            if self._frame_end_time(frame) <= threshold_time:
                matched_index = index
                continue
            break
        return matched_index

    def _slice_frames_from(
        self,
        frames: list[BufferedAudioFrame],
        start_index: int,
    ) -> list[BufferedAudioFrame]:
        if not frames:
            return []
        bounded_start_index = max(0, min(start_index, len(frames) - 1))
        return frames[bounded_start_index:]

    def _starts_with_speech_start(
        self,
        frames: list[BufferedAudioFrame],
    ) -> bool:
        if not frames:
            return False
        return frames[0].vad_state == VoiceActivityState.SPEECH_START


@dataclass(frozen=True)
class SpeechFrameSpan:
    start_index: int
    end_index: int
    is_open: bool

    @property
    def frame_count(self) -> int:
        return self.end_index - self.start_index + 1


class LatestWindowSnapshotExtractor(BufferSnapshotExtractor):
    def extract(
        self,
        frames: list[BufferedAudioFrame],
        *,
        target_sample_rate: int = 16000,
    ) -> BufferSnapshot:
        return self._build_snapshot(frames, target_sample_rate=target_sample_rate)


class CursorSnapshotExtractor(BufferSnapshotExtractor):
    def __init__(
        self,
        *,
        cursor: RecognitionCursor,
        max_window_seconds: float,
        max_backtrack_seconds: float = 3.0,
    ) -> None:
        self.cursor = cursor
        self.max_window_seconds = max_window_seconds
        self.max_backtrack_seconds = max_backtrack_seconds

    def extract(
        self,
        frames: list[BufferedAudioFrame],
        *,
        target_sample_rate: int = 16000,
    ) -> BufferSnapshot:
        if not frames:
            return self._build_snapshot([], target_sample_rate=target_sample_rate)

        window_end = self._frames_end_time(frames)
        window_floor = max(
            window_end - self.max_window_seconds,
            self._frames_start_time(frames),
        )
        candidate_start_index = self._find_candidate_start_index(
            frames=frames,
            window_floor=window_floor,
        )
        selected_frames = self._slice_frames_from(frames, candidate_start_index)
        snapshot = self._build_snapshot(selected_frames, target_sample_rate=target_sample_rate)
        return BufferSnapshot(
            frames=snapshot.frames,
            chunks=snapshot.chunks,
            waveform=snapshot.waveform,
            window_start=snapshot.window_start,
            window_end=snapshot.window_end,
            committed_end_time=self.cursor.committed_end_time,
            starts_with_speech_start=snapshot.starts_with_speech_start,
            selection_reason=self._build_selection_reason(frames, candidate_start_index),
            anchor_time=self.cursor.committed_end_time,
        )

    def _find_candidate_start_index(
        self,
        *,
        frames: list[BufferedAudioFrame],
        window_floor: float,
    ) -> int:
        floor_index = self._find_first_frame_ending_after(frames, window_floor)
        if floor_index is None:
            return 0

        anchor_index = self._find_anchor_index(frames)
        if anchor_index is None:
            return self._find_first_voice_index(frames, floor_index)

        backtrack_limit = max(
            self.cursor.committed_end_time - self.max_backtrack_seconds,
            window_floor,
        )
        start_index = anchor_index
        while start_index > floor_index:
            previous_frame = frames[start_index - 1]
            if self._frame_start_time(previous_frame) < backtrack_limit:
                break
            if previous_frame.vad_state == VoiceActivityState.SPEECH_START:
                return start_index - 1
            start_index -= 1

        backtrack_index = self._find_first_frame_ending_after(frames, backtrack_limit)
        if backtrack_index is None:
            return floor_index
        return max(backtrack_index, floor_index)

    def _find_anchor_index(self, frames: list[BufferedAudioFrame]) -> int | None:
        return self._find_last_frame_ending_at_or_before(
            frames,
            self.cursor.committed_end_time,
        )

    def _find_first_voice_index(
        self,
        frames: list[BufferedAudioFrame],
        floor_index: int,
    ) -> int:
        for index in range(floor_index, len(frames)):
            if frames[index].is_voice_related:
                return index
        return floor_index

    def _build_selection_reason(
        self,
        frames: list[BufferedAudioFrame],
        start_index: int,
    ) -> str:
        if not frames:
            return "empty"
        if self.cursor.committed_end_time <= 0:
            return "bootstrap"
        if frames[start_index].vad_state == VoiceActivityState.SPEECH_START:
            return "backtracked_to_speech_start"
        return "anchored_near_committed_tail"


class SpeechAwareSnapshotExtractor(BufferSnapshotExtractor):
    def __init__(
        self,
        *,
        max_window_seconds: float,
        leading_context_seconds: float = 0.2,
        trailing_context_seconds: float = 0.25,
        merge_gap_seconds: float = 0.25,
        min_span_frames: int = 2,
    ) -> None:
        self.max_window_seconds = max_window_seconds
        self.leading_context_seconds = leading_context_seconds
        self.trailing_context_seconds = trailing_context_seconds
        self.merge_gap_seconds = merge_gap_seconds
        self.min_span_frames = min_span_frames

    def extract(
        self,
        frames: list[BufferedAudioFrame],
        *,
        target_sample_rate: int = 16000,
    ) -> BufferSnapshot:
        if not frames:
            return self._build_snapshot([], target_sample_rate=target_sample_rate)

        window_end = self._frames_end_time(frames)
        window_floor = max(
            window_end - self.max_window_seconds,
            self._frames_start_time(frames),
        )
        candidate_frames = [
            frame for frame in frames if self._frame_end_time(frame) > window_floor
        ]
        if not candidate_frames:
            return self._build_snapshot([], target_sample_rate=target_sample_rate)

        spans = self._build_speech_spans(candidate_frames)
        if not spans:
            return self._build_snapshot(candidate_frames, target_sample_rate=target_sample_rate)

        target_span = self._select_target_span(spans)
        selected_start_index = self._expand_start_index(
            candidate_frames,
            start_index=target_span.start_index,
        )
        selected_end_index = self._expand_end_index(
            candidate_frames,
            end_index=target_span.end_index,
            allow_trailing_context=not target_span.is_open,
        )
        selected_frames = candidate_frames[selected_start_index : selected_end_index + 1]
        return self._build_snapshot(selected_frames, target_sample_rate=target_sample_rate)

    def _build_speech_spans(
        self,
        frames: list[BufferedAudioFrame],
    ) -> list[SpeechFrameSpan]:
        spans: list[SpeechFrameSpan] = []
        active_start_index: int | None = None

        for index, frame in enumerate(frames):
            state = frame.vad_state
            if state == VoiceActivityState.SILENCE:
                if active_start_index is not None:
                    spans.append(
                        SpeechFrameSpan(
                            start_index=active_start_index,
                            end_index=index - 1,
                            is_open=False,
                        )
                    )
                    active_start_index = None
                continue

            if active_start_index is None:
                active_start_index = index

            if state == VoiceActivityState.SPEECH_END:
                spans.append(
                    SpeechFrameSpan(
                        start_index=active_start_index,
                        end_index=index,
                        is_open=False,
                    )
                )
                active_start_index = None

        if active_start_index is not None:
            spans.append(
                SpeechFrameSpan(
                    start_index=active_start_index,
                    end_index=len(frames) - 1,
                    is_open=True,
                )
            )

        return self._merge_adjacent_spans(frames, spans)

    def _merge_adjacent_spans(
        self,
        frames: list[BufferedAudioFrame],
        spans: list[SpeechFrameSpan],
    ) -> list[SpeechFrameSpan]:
        if not spans:
            return []

        merged_spans: list[SpeechFrameSpan] = [spans[0]]
        for span in spans[1:]:
            previous = merged_spans[-1]
            gap_seconds = self._gap_between_spans(frames, previous, span)
            if gap_seconds <= self.merge_gap_seconds:
                merged_spans[-1] = SpeechFrameSpan(
                    start_index=previous.start_index,
                    end_index=span.end_index,
                    is_open=span.is_open,
                )
                continue

            merged_spans.append(span)

        return merged_spans

    def _select_target_span(
        self,
        spans: list[SpeechFrameSpan],
    ) -> SpeechFrameSpan:
        viable_spans = [span for span in spans if span.frame_count >= self.min_span_frames]
        search_spans = viable_spans if viable_spans else spans

        for span in reversed(search_spans):
            if span.is_open:
                return span
        return search_spans[-1]

    def _expand_start_index(
        self,
        frames: list[BufferedAudioFrame],
        *,
        start_index: int,
    ) -> int:
        selected_start_index = start_index
        context_budget = self.leading_context_seconds

        while selected_start_index > 0 and context_budget > 0:
            previous_frame = frames[selected_start_index - 1]
            if previous_frame.is_voice_related:
                break

            frame_duration = self._frame_duration_seconds(previous_frame)
            selected_start_index -= 1
            if frame_duration > 0:
                context_budget -= frame_duration

        return selected_start_index

    def _expand_end_index(
        self,
        frames: list[BufferedAudioFrame],
        *,
        end_index: int,
        allow_trailing_context: bool,
    ) -> int:
        if not allow_trailing_context:
            return end_index

        selected_end_index = end_index
        context_budget = self.trailing_context_seconds
        while selected_end_index + 1 < len(frames) and context_budget > 0:
            next_frame = frames[selected_end_index + 1]
            if next_frame.is_voice_related:
                break

            frame_duration = self._frame_duration_seconds(next_frame)
            selected_end_index += 1
            if frame_duration > 0:
                context_budget -= frame_duration

        return selected_end_index

    def _gap_between_spans(
        self,
        frames: list[BufferedAudioFrame],
        left: SpeechFrameSpan,
        right: SpeechFrameSpan,
    ) -> float:
        if right.start_index <= left.end_index + 1:
            return 0.0

        gap_start = self._frame_end_time(frames[left.end_index])
        gap_end = self._frame_start_time(frames[right.start_index])
        return max(gap_end - gap_start, 0.0)
