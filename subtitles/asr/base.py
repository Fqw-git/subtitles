from __future__ import annotations

from abc import ABC, abstractmethod
from typing import BinaryIO
from pathlib import Path

from subtitles.asr.models import SpeechRecognitionConfig, TranscriptResult


class SpeechRecognizer(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio: Path | BinaryIO | object,
        config: SpeechRecognitionConfig,
    ) -> TranscriptResult:
        """Transcribe audio from a file path or in-memory binary stream."""

    @abstractmethod
    def transcribe_file(
        self,
        audio_path: Path,
        config: SpeechRecognitionConfig,
    ) -> TranscriptResult:
        """Transcribe an audio file and return structured results."""
