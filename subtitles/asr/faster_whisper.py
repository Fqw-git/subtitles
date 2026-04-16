from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from subtitles.asr.base import SpeechRecognizer
from subtitles.asr.models import (
    SpeechRecognitionConfig,
    SpeechRecognitionError,
    TranscriptResult,
    TranscriptSegment,
)
from subtitles.config import (
    DEFAULT_COMPUTE_TYPE,
    DEFAULT_DEVICE,
    FALLBACK_COMPUTE_TYPE,
    FALLBACK_DEVICE,
)


class FasterWhisperRecognizer(SpeechRecognizer):
    def __init__(
        self,
        *,
        device: str = DEFAULT_DEVICE,
        compute_type: str = DEFAULT_COMPUTE_TYPE,
    ) -> None:
        self.device = device
        self.compute_type = compute_type
        self._model_cache: dict[str, object] = {}
        self._active_backend = (device, compute_type)

    def _set_backend(self, device: str, compute_type: str) -> None:
        self.device = device
        self.compute_type = compute_type
        self._active_backend = (device, compute_type)

    def _clear_model_cache(self) -> None:
        self._model_cache.clear()

    def _is_gpu_runtime_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "cublas" in message
            or "cudnn" in message
            or "cuda" in message
            or "cannot be loaded" in message
        )

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
        cached_model = self._model_cache.get(model_name)
        if cached_model is not None:
            return cached_model

        whisper_model = self._load_model_class()
        try:
            model = whisper_model(
                model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
            self._active_backend = (self.device, self.compute_type)
        except Exception as exc:
            if (self.device, self.compute_type) == (
                FALLBACK_DEVICE,
                FALLBACK_COMPUTE_TYPE,
            ):
                raise SpeechRecognitionError(
                    f"Failed to initialize recognition model '{model_name}'."
                ) from exc

            try:
                model = whisper_model(
                    model_name,
                    device=FALLBACK_DEVICE,
                    compute_type=FALLBACK_COMPUTE_TYPE,
                )
                self._set_backend(FALLBACK_DEVICE, FALLBACK_COMPUTE_TYPE)
            except Exception as fallback_exc:
                raise SpeechRecognitionError(
                    f"Failed to initialize recognition model '{model_name}' "
                    f"with GPU or CPU fallback."
                ) from fallback_exc

        self._model_cache[model_name] = model
        return model

    def transcribe(
        self,
        audio: Path | BinaryIO | object,
        config: SpeechRecognitionConfig,
    ) -> TranscriptResult:
        return self._transcribe_internal(audio, config)

    def transcribe_file(
        self,
        audio_path: Path,
        config: SpeechRecognitionConfig,
    ) -> TranscriptResult:
        return self._transcribe_internal(audio_path, config)

    def _transcribe_internal(
        self,
        audio: Path | BinaryIO | object,
        config: SpeechRecognitionConfig,
    ) -> TranscriptResult:
        model = self._create_model(config.model_name)

        try:
            segments, info = self._run_transcribe(model, audio, config)
        except Exception as exc:
            if self.device == "cuda" and self._is_gpu_runtime_error(exc):
                self._set_backend(FALLBACK_DEVICE, FALLBACK_COMPUTE_TYPE)
                self._clear_model_cache()
                model = self._create_model(config.model_name)
                try:
                    segments, info = self._run_transcribe(model, audio, config)
                except Exception as fallback_exc:
                    raise SpeechRecognitionError(
                        "Failed to transcribe audio input."
                    ) from fallback_exc
            else:
                raise SpeechRecognitionError(
                    "Failed to transcribe audio input."
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

    def _run_transcribe(self, model, audio: Path | BinaryIO | object, config: SpeechRecognitionConfig):
        segments, info = model.transcribe(
            str(audio) if isinstance(audio, Path) else audio,
            language=config.language,
            beam_size=config.beam_size,
            vad_filter=config.vad_filter,
        )
        return list(segments), info
