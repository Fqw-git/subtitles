from __future__ import annotations

from pathlib import Path

from subtitles.asr.base import SpeechRecognizer
from subtitles.asr.models import (
    SpeechRecognitionConfig,
    SpeechRecognitionError,
    TranscriptResult,
    TranscriptSegment,
)
from subtitles.config import DEFAULT_COMPUTE_TYPE, DEFAULT_DEVICE


class FasterWhisperRecognizer(SpeechRecognizer):
    def __init__(
        self,
        *,
        device: str = DEFAULT_DEVICE,
        compute_type: str = DEFAULT_COMPUTE_TYPE,
    ) -> None:
        self.device = device
        self.compute_type = compute_type

    def _load_model_class(self):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise SpeechRecognitionError(
                "Missing dependency: faster-whisper. Install dependencies with:\n"
                "pip install -r requirements.txt"
            ) from exc

        return WhisperModel

    def _create_model(self, model_name: str):
        whisper_model = self._load_model_class()
        return whisper_model(
            model_name,
            device=self.device,
            compute_type=self.compute_type,
        )

    def transcribe_file(
        self,
        audio_path: Path,
        config: SpeechRecognitionConfig,
    ) -> TranscriptResult:
        model = self._create_model(config.model_name)

        try:
            segments, info = model.transcribe(
                str(audio_path),
                language=config.language,
                beam_size=config.beam_size,
                vad_filter=config.vad_filter,
            )
        except Exception as exc:
            raise SpeechRecognitionError(
                f"Failed to transcribe audio file: {audio_path}"
            ) from exc

        transcript_segments: list[TranscriptSegment] = []
        full_text: list[str] = []

        for segment in segments:
            text = segment.text.strip()
            transcript_segments.append(
                TranscriptSegment(
                    start=round(segment.start, 3),
                    end=round(segment.end, 3),
                    text=text,
                )
            )
            if text:
                full_text.append(text)

        return TranscriptResult(
            language=info.language,
            language_probability=info.language_probability,
            text="\n".join(full_text),
            segments=transcript_segments,
            model_name=config.model_name,
        )
