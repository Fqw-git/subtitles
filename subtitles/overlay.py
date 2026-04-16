from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass

from subtitles.asr import FasterWhisperRecognizer
from subtitles.audio import PyAudioWasapiLoopbackCapturer
from subtitles.demo import RealtimeDemoConfig, RealtimeSystemAudioTranscriptionDemo


@dataclass(frozen=True)
class OverlaySubtitleState:
    committed_text: str
    unstable_text: str
    status_text: str


class SubtitleOverlayWindow:
    def __init__(self, title: str = "Live Subtitles") -> None:
        self.root = tk.Tk()
        self.root.title(title)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="#111111")
        self.root.geometry("960x180+280+820")
        self.root.minsize(640, 120)

        self._drag_origin_x = 0
        self._drag_origin_y = 0

        self.status_var = tk.StringVar(value="Ready")
        self.committed_var = tk.StringVar(value="")
        self.preview_var = tk.StringVar(value="")

        self._build_layout()

    def _build_layout(self) -> None:
        frame = tk.Frame(self.root, bg="#111111", padx=20, pady=14)
        frame.pack(fill="both", expand=True)

        header = tk.Label(
            frame,
            text="Realtime Subtitles",
            font=("Segoe UI", 11, "bold"),
            fg="#c8d1dc",
            bg="#111111",
            anchor="w",
        )
        header.pack(fill="x")

        status = tk.Label(
            frame,
            textvariable=self.status_var,
            font=("Segoe UI", 10),
            fg="#93a4b5",
            bg="#111111",
            anchor="w",
        )
        status.pack(fill="x", pady=(4, 10))

        committed = tk.Label(
            frame,
            textvariable=self.committed_var,
            font=("Microsoft YaHei UI", 20, "bold"),
            fg="#f7f3e8",
            bg="#111111",
            justify="center",
            wraplength=900,
        )
        committed.pack(fill="both", expand=True)

        preview = tk.Label(
            frame,
            textvariable=self.preview_var,
            font=("Microsoft YaHei UI", 16),
            fg="#f2c66d",
            bg="#111111",
            justify="center",
            wraplength=900,
        )
        preview.pack(fill="x", pady=(8, 0))

        for widget in [frame, header, status, committed, preview]:
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag_window)

    def _start_drag(self, event) -> None:
        self._drag_origin_x = event.x_root - self.root.winfo_x()
        self._drag_origin_y = event.y_root - self.root.winfo_y()

    def _drag_window(self, event) -> None:
        x = event.x_root - self._drag_origin_x
        y = event.y_root - self._drag_origin_y
        self.root.geometry(f"+{x}+{y}")

    def update_state(self, state: OverlaySubtitleState) -> None:
        self.committed_var.set(state.committed_text)
        self.preview_var.set(state.unstable_text)
        self.status_var.set(state.status_text)

    def poll_queue(self, state_queue: queue.Queue, stop_event: threading.Event) -> None:
        while True:
            try:
                state = state_queue.get_nowait()
            except queue.Empty:
                break
            else:
                self.update_state(state)

        if stop_event.is_set():
            self.status_var.set("Stopped")
            return

        self.root.after(100, self.poll_queue, state_queue, stop_event)

    def run(self, state_queue: queue.Queue, stop_event: threading.Event) -> None:
        self.root.after(100, self.poll_queue, state_queue, stop_event)
        self.root.mainloop()
        stop_event.set()


class SubtitleOverlayApp:
    def __init__(self, config: RealtimeDemoConfig) -> None:
        self.config = config
        self.demo = RealtimeSystemAudioTranscriptionDemo(
            capturer=PyAudioWasapiLoopbackCapturer(),
            recognizer=FasterWhisperRecognizer(),
        )
        self.state_queue: queue.Queue[OverlaySubtitleState] = queue.Queue()
        self.stop_event = threading.Event()

    def _build_status_text(self, event) -> str:
        return (
            f"Listening  window={event.window_start:.1f}s-{event.window_end:.1f}s  "
            f"update={event.update_index}"
        )

    def _worker(self) -> None:
        try:
            self.state_queue.put(
                OverlaySubtitleState(
                    committed_text="",
                    unstable_text="",
                    status_text="Starting recognition...",
                )
            )
            for event in self.demo.iter_events(self.config):
                if self.stop_event.is_set():
                    break

                committed = event.transcript_delta.committed_text.strip()
                preview = event.transcript_delta.unstable_text.strip()
                if not committed and not preview:
                    preview = "..."

                self.state_queue.put(
                    OverlaySubtitleState(
                        committed_text=committed,
                        unstable_text=preview,
                        status_text=self._build_status_text(event),
                    )
                )
        except Exception as exc:
            self.state_queue.put(
                OverlaySubtitleState(
                    committed_text="",
                    unstable_text="",
                    status_text=f"Error: {exc}",
                )
            )
        finally:
            self.stop_event.set()

    def run(self) -> None:
        worker = threading.Thread(target=self._worker, daemon=True)
        worker.start()
        window = SubtitleOverlayWindow()
        window.run(self.state_queue, self.stop_event)
