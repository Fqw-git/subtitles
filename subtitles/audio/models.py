from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class AudioCaptureError(RuntimeError):
    """Raised when audio capture cannot proceed."""


@dataclass(frozen=True)
class AudioCaptureDevice:
    index: int
    name: str
    max_input_channels: int
    default_sample_rate: int
    is_default: bool = False
    is_loopback: bool = True


@dataclass(frozen=True)
class AudioCaptureConfig:
    seconds: int
    sample_rate: int
    channels: int
    frames_per_buffer: int = 1024
    device_name: str | None = None


@dataclass(frozen=True)
class AudioCaptureResult:
    output_path: Path
    device: AudioCaptureDevice
    seconds: int
    sample_rate: int
    channels: int
    frames_per_buffer: int
