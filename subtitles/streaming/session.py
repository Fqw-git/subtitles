from __future__ import annotations

from dataclasses import dataclass
import logging

from subtitles.asr import SpeechRecognitionConfig, SpeechRecognizer, TranscriptResult
from subtitles.audio import AudioCaptureConfig, AudioCapturer
from subtitles.streaming.buffer import SlidingAudioBuffer
from subtitles.streaming.delta import TranscriptDelta, TranscriptDeltaTracker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StreamingSessionConfig:
    capture: AudioCaptureConfig
    recognition: SpeechRecognitionConfig
    window_seconds: float
    step_seconds: float
    stability_seconds: float
    max_updates: int | None = None


@dataclass(frozen=True)
class StreamingSessionEvent:
    update_index: int
    transcript_result: TranscriptResult
    transcript_delta: TranscriptDelta
    window_start: float
    window_end: float
    trigger_time: float


class StreamingRecognitionSession:
    def __init__(
        self,
        *,
        capturer: AudioCapturer,
        recognizer: SpeechRecognizer,
    ) -> None:
        self.capturer = capturer
        self.recognizer = recognizer

    def iter_events(self, config: StreamingSessionConfig):
        if config.window_seconds <= 0:
            raise ValueError("window_seconds must be greater than 0.")
        if config.step_seconds <= 0:
            raise ValueError("step_seconds must be greater than 0.")
        if config.stability_seconds < 0:
            raise ValueError("stability_seconds must be greater than or equal to 0.")

        buffer = SlidingAudioBuffer(max_duration_seconds=config.window_seconds)
        delta_tracker = TranscriptDeltaTracker()
        next_trigger_time = config.step_seconds
        update_index = 0
        logger.info(
            "Streaming session started: window_seconds=%.2f step_seconds=%.2f stability_seconds=%.2f sample_rate=%s channels=%s frames_per_buffer=%s device=%s",
            config.window_seconds,
            config.step_seconds,
            config.stability_seconds,
            config.capture.sample_rate,
            config.capture.channels,
            config.capture.frames_per_buffer,
            config.capture.device_name,
        )

        for chunk in self.capturer.iter_chunks(config.capture):
            buffer.append(chunk)
            logger.debug(
                "Chunk appended: start=%.3f end=%.3f frames=%s buffer_duration=%.3f",
                chunk.start_time,
                chunk.end_time,
                chunk.frames,
                buffer.duration_seconds,
            )

            if buffer.duration_seconds <= 0:
                continue

            if chunk.end_time < next_trigger_time:
                continue

            window_chunks = buffer.export_window()
            if not window_chunks:
                continue

            update_index += 1
            logger.info(
                "Triggering streaming ASR update=%s at chunk_end=%.3f window=%.3f-%.3f chunk_count=%s",
                update_index,
                chunk.end_time,
                buffer.current_time_range()[0],
                buffer.current_time_range()[1],
                len(window_chunks),
            )
            transcript_result = self.recognizer.transcribe(
                buffer.export_waveform(),
                config.recognition,
            )
            window_start, window_end = buffer.current_time_range()
            transcript_delta = delta_tracker.update(
                transcript_result.segments,
                window_start=window_start,
                window_end=window_end,
                stability_seconds=config.stability_seconds,
            )
            logger.info(
                "Streaming update=%s produced text=%r committed=%r unstable=%r revision=%s",
                update_index,
                transcript_result.text,
                transcript_delta.committed_text,
                transcript_delta.unstable_text,
                transcript_delta.is_revision,
            )

            yield StreamingSessionEvent(
                update_index=update_index,
                transcript_result=transcript_result,
                transcript_delta=transcript_delta,
                window_start=window_start,
                window_end=window_end,
                trigger_time=chunk.end_time,
            )

            next_trigger_time += config.step_seconds
            if config.max_updates is not None and update_index >= config.max_updates:
                logger.info("Streaming session stopped after reaching max_updates=%s", config.max_updates)
                return
