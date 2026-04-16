from __future__ import annotations

from dataclasses import dataclass

from subtitles.asr import SpeechRecognitionConfig, SpeechRecognizer, TranscriptResult
from subtitles.audio import AudioCaptureConfig, AudioCapturer
from subtitles.streaming import TranscriptDelta
from subtitles.streaming import (
    StreamingRecognitionSession,
    StreamingSessionConfig,
)


@dataclass(frozen=True)
class RealtimeDemoConfig:
    capture: AudioCaptureConfig
    recognition: SpeechRecognitionConfig
    window_seconds: float
    step_seconds: float
    stability_seconds: float
    max_updates: int | None = None


@dataclass(frozen=True)
class RealtimeDemoEvent:
    update_index: int
    transcript_result: TranscriptResult
    transcript_delta: TranscriptDelta
    window_start: float
    window_end: float
    trigger_time: float


class RealtimeSystemAudioTranscriptionDemo:
    def __init__(
        self,
        *,
        capturer: AudioCapturer,
        recognizer: SpeechRecognizer,
    ) -> None:
        self.capturer = capturer
        self.recognizer = recognizer
        self.session = StreamingRecognitionSession(
            capturer=capturer,
            recognizer=recognizer,
        )

    def iter_events(self, config: RealtimeDemoConfig):
        for event in self.session.iter_events(
            StreamingSessionConfig(
                capture=config.capture,
                recognition=config.recognition,
                window_seconds=config.window_seconds,
                step_seconds=config.step_seconds,
                stability_seconds=config.stability_seconds,
                max_updates=config.max_updates,
            )
        ):
            yield RealtimeDemoEvent(
                update_index=event.update_index,
                transcript_result=event.transcript_result,
                transcript_delta=event.transcript_delta,
                window_start=event.window_start,
                window_end=event.window_end,
                trigger_time=event.trigger_time,
            )
