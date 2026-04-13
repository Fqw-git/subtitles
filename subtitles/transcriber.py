from __future__ import annotations

from pathlib import Path

from subtitles.config import DEFAULT_COMPUTE_TYPE, DEFAULT_DEVICE
from subtitles.models import SegmentResult, TranscriptResult


def load_whisper_model(model_name: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: faster-whisper. Install dependencies with:\n"
            "pip install -r requirements.txt"
        ) from exc

    return WhisperModel(
        model_name,
        device=DEFAULT_DEVICE,
        compute_type=DEFAULT_COMPUTE_TYPE,
    )


def transcribe_audio(
    audio_path: Path,
    model_name: str,
    language: str,
    beam_size: int,
) -> TranscriptResult:
    model = load_whisper_model(model_name)
    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        beam_size=beam_size,
        vad_filter=True,
    )

    result_segments: list[SegmentResult] = []
    full_text: list[str] = []

    for segment in segments:
        text = segment.text.strip()
        result_segments.append(
            SegmentResult(
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
        segments=result_segments,
    )
