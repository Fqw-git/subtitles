from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from subtitles.asr.models import SpeechRecognitionConfig, TranscriptResult


class SpeechRecognizer(ABC):
    @abstractmethod
    def transcribe_file(
        self,
        audio_path: Path,
        config: SpeechRecognitionConfig,
    ) -> TranscriptResult:
        """Transcribe an audio file and return structured results."""
