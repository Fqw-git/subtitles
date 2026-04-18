from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from subtitles.vad.base import VoiceActivityDetector
from subtitles.vad.models import (
    VoiceActivityConfig,
    VoiceActivityError,
    VoiceActivityResult,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import numpy as np


class WebRtcVoiceActivityDetector(VoiceActivityDetector):
    def _load_webrtcvad(self):
        try:
            import webrtcvad
        except ImportError as exc:
            raise VoiceActivityError(
                "Missing dependency: webrtcvad-wheels. Install dependencies with:\n"
                "pip install -r requirements.txt"
            ) from exc

        return webrtcvad

    def detect(
        self,
        waveform: "np.ndarray",
        config: VoiceActivityConfig,
    ) -> VoiceActivityResult:
        if not config.enabled:
            return VoiceActivityResult(
                speech_detected=True,
                speech_frames=0,
                total_frames=0,
                speech_duration_ms=0,
                frame_duration_ms=config.frame_duration_ms,
            )

        if config.aggressiveness < 0 or config.aggressiveness > 3:
            raise VoiceActivityError("VAD aggressiveness must be between 0 and 3.")
        if config.frame_duration_ms not in {10, 20, 30}:
            raise VoiceActivityError("VAD frame_duration_ms must be 10, 20, or 30.")
        if config.min_speech_duration_ms < 0:
            raise VoiceActivityError("VAD min_speech_duration_ms must be non-negative.")
        if config.sample_rate not in {8000, 16000, 32000, 48000}:
            raise VoiceActivityError("VAD sample_rate must be 8000, 16000, 32000, or 48000.")

        if waveform.size == 0:
            return VoiceActivityResult(
                speech_detected=False,
                speech_frames=0,
                total_frames=0,
                speech_duration_ms=0,
                frame_duration_ms=config.frame_duration_ms,
            )

        vad_module = self._load_webrtcvad()
        vad = vad_module.Vad(config.aggressiveness)
        pcm16 = self._to_pcm16(waveform)
        frame_size = int(config.sample_rate * config.frame_duration_ms / 1000)
        if frame_size <= 0:
            raise VoiceActivityError("Computed VAD frame size must be positive.")

        speech_frames = 0
        total_frames = 0
        for start in range(0, pcm16.shape[0] - frame_size + 1, frame_size):
            frame = pcm16[start : start + frame_size]
            if frame.shape[0] != frame_size:
                continue

            total_frames += 1
            if vad.is_speech(frame.tobytes(), config.sample_rate):
                speech_frames += 1

        speech_duration_ms = speech_frames * config.frame_duration_ms
        speech_detected = speech_duration_ms >= config.min_speech_duration_ms
        result = VoiceActivityResult(
            speech_detected=speech_detected,
            speech_frames=speech_frames,
            total_frames=total_frames,
            speech_duration_ms=speech_duration_ms,
            frame_duration_ms=config.frame_duration_ms,
        )
        logger.debug(
            "WebRTC VAD result: speech_detected=%s speech_frames=%s total_frames=%s speech_duration_ms=%s",
            result.speech_detected,
            result.speech_frames,
            result.total_frames,
            result.speech_duration_ms,
        )
        return result

    def _to_pcm16(self, waveform: "np.ndarray") -> "np.ndarray":
        try:
            import numpy as np
        except ImportError as exc:
            raise VoiceActivityError(
                "Missing dependency: numpy. Install dependencies with:\n"
                "pip install -r requirements.txt"
            ) from exc

        clipped = np.clip(waveform, -1.0, 1.0)
        return (clipped * 32767.0).astype(np.int16)
