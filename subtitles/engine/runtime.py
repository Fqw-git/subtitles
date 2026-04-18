from __future__ import annotations

from dataclasses import dataclass, field
import queue
import threading

from subtitles.engine.buffering import SlidingAudioBuffer
from subtitles.engine.models import StreamingSessionEvent


@dataclass
class StreamingRuntime:
    buffer: SlidingAudioBuffer
    event_queue: queue.Queue[StreamingSessionEvent | Exception | object]
    stop_event: threading.Event = field(default_factory=threading.Event)
    latest_chunk_end: float = 0.0
    latest_chunk_lock: threading.Lock = field(default_factory=threading.Lock)
    completed_marker: object = field(default_factory=object)

    def update_latest_chunk_end(self, chunk_end: float) -> None:
        with self.latest_chunk_lock:
            self.latest_chunk_end = chunk_end

    def read_latest_chunk_end(self) -> float:
        with self.latest_chunk_lock:
            return self.latest_chunk_end
