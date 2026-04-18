from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from subtitles.audio import AudioChunk


class VoiceActivityState(StrEnum):
    SILENCE = "silence"
    SPEECH_START = "speech_start"
    SPEAKING = "speaking"
    SPEECH_END = "speech_end"


@dataclass(frozen=True)
class BufferedAudioFrame:
    chunk: AudioChunk
    speech_detected: bool
    vad_state: VoiceActivityState
    speech_duration_ms: int = 0

    @property
    def is_voice_related(self) -> bool:
        return self.vad_state != VoiceActivityState.SILENCE
