from __future__ import annotations

from pathlib import Path

from subtitles.config import DEFAULT_CHANNELS, DEFAULT_SAMPLE_RATE
from subtitles.utils import ensure_ffmpeg, run_cmd


def list_audio_devices() -> None:
    ffmpeg = ensure_ffmpeg()
    cmd = [
        ffmpeg,
        "-list_devices",
        "true",
        "-f",
        "dshow",
        "-i",
        "dummy",
    ]
    run_cmd(cmd)


def record_system_audio(output: Path, seconds: int, device: str | None = None) -> None:
    ffmpeg = ensure_ffmpeg()
    audio_input = device or "virtual-audio-capturer"
    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "dshow",
        "-i",
        f"audio={audio_input}",
        "-t",
        str(seconds),
        "-ac",
        str(DEFAULT_CHANNELS),
        "-ar",
        str(DEFAULT_SAMPLE_RATE),
        str(output),
    ]
    run_cmd(cmd)
