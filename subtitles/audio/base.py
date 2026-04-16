from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

from subtitles.audio.models import (
    AudioCaptureConfig,
    AudioChunk,
    AudioCaptureDevice,
    AudioCaptureResult,
)


class AudioCapturer(ABC):
    @abstractmethod
    def list_devices(self) -> list[AudioCaptureDevice]:
        """Return supported capture devices."""

    @abstractmethod
    def resolve_device(self, device_name: str | None = None) -> AudioCaptureDevice:
        """Resolve the requested device or the default device."""

    @abstractmethod
    def capture_to_file(
        self,
        output_path: Path,
        config: AudioCaptureConfig,
    ) -> AudioCaptureResult:
        """Capture audio and write it to a file."""

    @abstractmethod
    def iter_chunks(self, config: AudioCaptureConfig) -> Iterator[AudioChunk]:
        """Yield audio chunks from a live capture stream."""
