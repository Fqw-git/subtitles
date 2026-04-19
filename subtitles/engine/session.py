from __future__ import annotations

import logging
import queue
import threading

from subtitles.asr import SpeechRecognizer
from subtitles.audio import AudioCapturer
from subtitles.engine.buffering import RecognitionBuffer, SlidingAudioBuffer
from subtitles.engine.capture_worker import StreamingCaptureWorker
from subtitles.engine.models import StreamingSessionConfig
from subtitles.engine.runtime import StreamingRuntime
from subtitles.engine.scheduler import StreamingScheduler
from subtitles.engine.stabilizer import TranscriptDeltaTracker
from subtitles.vad import VoiceActivityDetector

logger = logging.getLogger(__name__)


class StreamingRecognitionSession:
    def __init__(
        self,
        *,
        capturer: AudioCapturer,
        recognizer: SpeechRecognizer,
        vad_detector: VoiceActivityDetector | None = None,
    ) -> None:
        self.capturer = capturer
        self.recognizer = recognizer
        self.vad_detector = vad_detector
        self.capture_worker = StreamingCaptureWorker(
            capturer=capturer,
            vad_detector=vad_detector,
        )
        self.scheduler = StreamingScheduler(
            recognizer=recognizer,
        )

    def iter_events(self, config: StreamingSessionConfig):
        self._validate_config(config)

        runtime = StreamingRuntime(
            buffer=RecognitionBuffer(
                audio_buffer=SlidingAudioBuffer(
                    max_duration_seconds=max(
                        config.window_seconds * 2,
                        config.window_seconds + 3.0,
                    )
                ),
                max_window_seconds=config.window_seconds,
                target_sample_rate=config.vad.sample_rate,
            ),
            event_queue=queue.Queue(),
        )
        delta_tracker = TranscriptDeltaTracker(
            stability_seconds=config.stability_seconds,
        )

        capture_thread = threading.Thread(
            target=self.capture_worker.run,
            args=(config, runtime),
            name="capture-thread",
            daemon=True,
        )
        scheduler_thread = threading.Thread(
            target=self.scheduler.run,
            args=(config, runtime, delta_tracker),
            name="scheduler-thread",
            daemon=True,
        )

        logger.info(
            "Streaming session started: window_seconds=%.2f step_seconds=%.2f stability_seconds=%.2f sample_rate=%s channels=%s frames_per_buffer=%s device=%s vad_enabled=%s",
            config.window_seconds,
            config.step_seconds,
            config.stability_seconds,
            config.capture.sample_rate,
            config.capture.channels,
            config.capture.frames_per_buffer,
            config.capture.device_name,
            config.vad.enabled,
        )

        capture_thread.start()
        scheduler_thread.start()

        try:
            while True:
                message = runtime.event_queue.get()
                if message is runtime.completed_marker:
                    return
                if isinstance(message, Exception):
                    raise message
                yield message
        finally:
            runtime.stop_event.set()
            capture_thread.join(timeout=1.0)
            scheduler_thread.join(timeout=1.0)

    def _validate_config(self, config: StreamingSessionConfig) -> None:
        if config.window_seconds <= 0:
            raise ValueError("window_seconds must be greater than 0.")
        if config.step_seconds <= 0:
            raise ValueError("step_seconds must be greater than 0.")
        if config.stability_seconds < 0:
            raise ValueError("stability_seconds must be greater than or equal to 0.")
