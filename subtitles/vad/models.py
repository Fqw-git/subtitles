from __future__ import annotations

from dataclasses import dataclass


class VoiceActivityError(RuntimeError):
    """Raised when voice activity detection cannot proceed."""


@dataclass(frozen=True)
class VoiceActivityConfig:
    enabled: bool = True
    aggressiveness: int = 2
    frame_duration_ms: int = 30
    min_speech_duration_ms: int = 300
    sample_rate: int = 16000


@dataclass(frozen=True)
class VoiceActivityResult:
    speech_detected: bool
    speech_frames: int
    total_frames: int
    speech_duration_ms: int
    frame_duration_ms: int
