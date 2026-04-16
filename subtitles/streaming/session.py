from __future__ import annotations

from dataclasses import dataclass

from subtitles.asr import SpeechRecognitionConfig, SpeechRecognizer, TranscriptResult
from subtitles.audio import AudioCaptureConfig, AudioCapturer
from subtitles.streaming.buffer import SlidingAudioBuffer
from subtitles.streaming.delta import TranscriptDelta, TranscriptDeltaTracker


@dataclass(frozen=True)
class StreamingSessionConfig:
    capture: AudioCaptureConfig
    recognition: SpeechRecognitionConfig
    window_seconds: float
    step_seconds: float
    stability_seconds: float
    max_updates: int | None = None


@dataclass(frozen=True)
class StreamingSessionEvent:
    update_index: int
    transcript_result: TranscriptResult
    transcript_delta: TranscriptDelta
    window_start: float
    window_end: float
    trigger_time: float


class StreamingRecognitionSession:
    def __init__(
        self,
        *,
        capturer: AudioCapturer,
        recognizer: SpeechRecognizer,
    ) -> None:
        self.capturer = capturer
        self.recognizer = recognizer

    def iter_events(self, config: StreamingSessionConfig):
        if config.window_seconds <= 0:
            raise ValueError("window_seconds must be greater than 0.")
        if config.step_seconds <= 0:
            raise ValueError("step_seconds must be greater than 0.")
        if config.stability_seconds < 0:
            raise ValueError("stability_seconds must be greater than or equal to 0.")

        buffer = SlidingAudioBuffer(max_duration_seconds=config.window_seconds)
        delta_tracker = TranscriptDeltaTracker()
        next_trigger_time = config.step_seconds
        update_index = 0

        for chunk in self.capturer.iter_chunks(config.capture):
            buffer.append(chunk)

            if buffer.duration_seconds <= 0:
                continue

            if chunk.end_time < next_trigger_time:
                continue

            window_chunks = buffer.export_window()
            if not window_chunks:
                continue

            update_index += 1
            transcript_result = self.recognizer.transcribe(
                buffer.export_waveform(),
                config.recognition,
            )
            window_start, window_end = buffer.current_time_range()
            transcript_delta = delta_tracker.update(
                transcript_result.segments,
                window_start=window_start,
                window_end=window_end,
                stability_seconds=config.stability_seconds,
            )

            yield StreamingSessionEvent(
                update_index=update_index,
                transcript_result=transcript_result,
                transcript_delta=transcript_delta,
                window_start=window_start,
                window_end=window_end,
                trigger_time=chunk.end_time,
            )

            next_trigger_time += config.step_seconds
            if config.max_updates is not None and update_index >= config.max_updates:
                return
