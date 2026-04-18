from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from subtitles.vad.models import VoiceActivityConfig, VoiceActivityResult

if TYPE_CHECKING:
    import numpy as np


class VoiceActivityDetector(ABC):
    @abstractmethod
    def detect(
        self,
        waveform: "np.ndarray",
        config: VoiceActivityConfig,
    ) -> VoiceActivityResult:
        raise NotImplementedError
