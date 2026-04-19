from __future__ import annotations

import logging
import time

from subtitles.asr import SpeechRecognizer
from subtitles.engine.buffering import (
    BufferedAudioFrame,
)
from subtitles.engine.models import StreamingSessionConfig, StreamingSessionEvent
from subtitles.engine.runtime import StreamingRuntime
from subtitles.engine.stabilizer import TranscriptDeltaTracker
from subtitles.vad import VoiceActivityConfig, VoiceActivityResult

logger = logging.getLogger(__name__)


class StreamingScheduler:
    def __init__(
        self,
        *,
        recognizer: SpeechRecognizer,
    ) -> None:
        self.recognizer = recognizer

    def run(
        self,
        config: StreamingSessionConfig,
        runtime: StreamingRuntime,
        delta_tracker: TranscriptDeltaTracker,
    ) -> None:
        next_trigger_time = config.step_seconds
        update_index = 0
        try:
            while not runtime.stop_event.is_set():
                current_chunk_end = runtime.read_latest_chunk_end()
                if current_chunk_end < next_trigger_time or runtime.buffer.duration_seconds <= 0:
                    time.sleep(0.01)
                    continue

                snapshot = runtime.buffer.extract_snapshot()
                window_frames = snapshot.frames
                window_chunks = snapshot.chunks
                waveform = snapshot.waveform
                window_start = snapshot.window_start
                window_end = snapshot.window_end
                if not window_chunks:
                    next_trigger_time += config.step_seconds
                    continue

                vad_result = self.summarize_buffered_vad(
                    frames=window_frames,
                    config=config.vad,
                )
                if not vad_result.speech_detected:
                    logger.info(
                        "Scheduler skipped ASR at trigger=%.3f window=%.3f-%.3f because buffered VAD found no speech (speech_frames=%s total_frames=%s speech_duration_ms=%s)",
                        next_trigger_time,
                        window_start,
                        window_end,
                        vad_result.speech_frames,
                        vad_result.total_frames,
                        vad_result.speech_duration_ms,
                    )
                    runtime.buffer.mark_snapshot(start_time=window_start, end_time=window_end)
                    next_trigger_time += config.step_seconds
                    continue

                update_index += 1
                logger.info(
                    "Scheduler triggering ASR update=%s at trigger=%.3f window=%.3f-%.3f chunk_count=%s vad_speech_frames=%s vad_total_frames=%s selection_reason=%s committed_end=%.3f provisional_end=%.3f",
                    update_index,
                    next_trigger_time,
                    window_start,
                    window_end,
                    len(window_chunks),
                    vad_result.speech_frames,
                    vad_result.total_frames,
                    snapshot.selection_reason,
                    runtime.buffer.cursor.committed_end_time,
                    runtime.buffer.cursor.provisional_end_time,
                )

                transcript_result = self.recognizer.transcribe(
                    waveform,
                    config.recognition,
                )
                transcript_delta = delta_tracker.update(
                    transcript_result.segments,
                    snapshot=snapshot,
                )
                runtime.buffer.mark_snapshot(start_time=window_start, end_time=window_end)
                runtime.buffer.apply_delta(transcript_delta)
                logger.info(
                    "Streaming update=%s produced text=%r baseline=%r committed=%r unstable=%r revision=%s committed_end=%.3f provisional_end=%.3f",
                    update_index,
                    transcript_result.text,
                    transcript_delta.baseline_text,
                    transcript_delta.committed_text,
                    transcript_delta.unstable_text,
                    transcript_delta.is_revision,
                    runtime.buffer.cursor.committed_end_time,
                    runtime.buffer.cursor.provisional_end_time,
                )

                runtime.event_queue.put(
                    StreamingSessionEvent(
                        update_index=update_index,
                        transcript_result=transcript_result,
                        transcript_delta=transcript_delta,
                        window_start=window_start,
                        window_end=window_end,
                        trigger_time=next_trigger_time,
                    )
                )

                next_trigger_time += config.step_seconds
                if config.max_updates is not None and update_index >= config.max_updates:
                    logger.info("Streaming session stopped after reaching max_updates=%s", config.max_updates)
                    runtime.stop_event.set()
                    break
        except Exception as exc:
            logger.exception("Scheduler thread failed")
            runtime.event_queue.put(exc)
            runtime.stop_event.set()
        finally:
            logger.info("Scheduler thread stopped")
            runtime.event_queue.put(runtime.completed_marker)

    def summarize_buffered_vad(
        self,
        *,
        frames: list[BufferedAudioFrame],
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

        speech_frames = sum(1 for frame in frames if frame.speech_detected)
        voice_related_frames = sum(1 for frame in frames if frame.is_voice_related)
        total_frames = len(frames)
        speech_duration_ms = sum(frame.speech_duration_ms for frame in frames)
        return VoiceActivityResult(
            speech_detected=speech_duration_ms >= config.min_speech_duration_ms,
            speech_frames=voice_related_frames if voice_related_frames > speech_frames else speech_frames,
            total_frames=total_frames,
            speech_duration_ms=speech_duration_ms,
            frame_duration_ms=config.frame_duration_ms,
        )
