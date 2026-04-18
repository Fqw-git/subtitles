from __future__ import annotations

import logging

from subtitles.audio import AudioCapturer, AudioChunk
from subtitles.engine.buffering import (
    BufferedAudioFrame,
    VoiceActivityState,
    chunk_to_waveform,
)
from subtitles.engine.models import StreamingSessionConfig
from subtitles.engine.runtime import StreamingRuntime
from subtitles.vad import VoiceActivityConfig, VoiceActivityDetector

logger = logging.getLogger(__name__)


class StreamingCaptureWorker:
    def __init__(
        self,
        *,
        capturer: AudioCapturer,
        vad_detector: VoiceActivityDetector | None = None,
    ) -> None:
        self.capturer = capturer
        self.vad_detector = vad_detector
        self._previous_speech_detected = False

    def run(
        self,
        config: StreamingSessionConfig,
        runtime: StreamingRuntime,
    ) -> None:
        self._previous_speech_detected = False
        try:
            for chunk in self.capturer.iter_chunks(config.capture):
                if runtime.stop_event.is_set():
                    break

                buffered_frame = self.build_buffered_frame(
                    chunk=chunk,
                    vad_config=config.vad,
                )
                runtime.buffer.append(buffered_frame)
                runtime.update_latest_chunk_end(buffered_frame.chunk.end_time)

                logger.debug(
                    "Capture thread appended frame: start=%.3f end=%.3f frames=%s speech_detected=%s vad_state=%s speech_duration_ms=%s buffer_duration=%.3f",
                    buffered_frame.chunk.start_time,
                    buffered_frame.chunk.end_time,
                    buffered_frame.chunk.frames,
                    buffered_frame.speech_detected,
                    buffered_frame.vad_state,
                    buffered_frame.speech_duration_ms,
                    runtime.buffer.duration_seconds,
                )
        except Exception as exc:
            logger.exception("Capture thread failed")
            runtime.event_queue.put(exc)
            runtime.stop_event.set()
        finally:
            logger.info("Capture thread stopped")

    def build_buffered_frame(
        self,
        *,
        chunk: AudioChunk,
        vad_config: VoiceActivityConfig,
    ) -> BufferedAudioFrame:
        if not vad_config.enabled or self.vad_detector is None:
            vad_state = self._resolve_vad_state(current_speech_detected=True)
            return BufferedAudioFrame(
                chunk=chunk,
                speech_detected=True,
                vad_state=vad_state,
                speech_duration_ms=0,
            )

        chunk_vad_config = VoiceActivityConfig(
            enabled=True,
            aggressiveness=vad_config.aggressiveness,
            frame_duration_ms=10,
            min_speech_duration_ms=10,
            sample_rate=vad_config.sample_rate,
        )
        waveform = chunk_to_waveform(chunk, target_sample_rate=chunk_vad_config.sample_rate)
        vad_result = self.vad_detector.detect(waveform, chunk_vad_config)
        vad_state = self._resolve_vad_state(current_speech_detected=vad_result.speech_detected)
        buffered_chunk = chunk if vad_result.speech_detected else self._mute_chunk(chunk)
        return BufferedAudioFrame(
            chunk=buffered_chunk,
            speech_detected=vad_result.speech_detected,
            vad_state=vad_state,
            speech_duration_ms=vad_result.speech_duration_ms,
        )

    def _resolve_vad_state(self, *, current_speech_detected: bool) -> VoiceActivityState:
        previous_speech_detected = self._previous_speech_detected
        self._previous_speech_detected = current_speech_detected

        if not previous_speech_detected and not current_speech_detected:
            return VoiceActivityState.SILENCE
        if not previous_speech_detected and current_speech_detected:
            return VoiceActivityState.SPEECH_START
        if previous_speech_detected and current_speech_detected:
            return VoiceActivityState.SPEAKING
        return VoiceActivityState.SPEECH_END

    def _mute_chunk(self, chunk: AudioChunk) -> AudioChunk:
        return AudioChunk(
            data=b"\x00" * len(chunk.data),
            sample_rate=chunk.sample_rate,
            channels=chunk.channels,
            sample_width=chunk.sample_width,
            frames=chunk.frames,
            start_time=chunk.start_time,
            end_time=chunk.end_time,
            device=chunk.device,
        )
