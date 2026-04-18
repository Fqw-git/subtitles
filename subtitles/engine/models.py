from __future__ import annotations

from dataclasses import dataclass

from subtitles.asr import SpeechRecognitionConfig, TranscriptResult
from subtitles.audio import AudioCaptureConfig
from subtitles.engine.stabilizer import TranscriptDelta
from subtitles.vad import VoiceActivityConfig


@dataclass(frozen=True)
class StreamingSessionConfig:
    capture: AudioCaptureConfig
    recognition: SpeechRecognitionConfig
    vad: VoiceActivityConfig
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
