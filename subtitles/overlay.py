from __future__ import annotations

import logging
import queue
import re
import threading
import tkinter as tk
from dataclasses import dataclass

from subtitles.asr import FasterWhisperRecognizer
from subtitles.audio import PyAudioWasapiLoopbackCapturer
from subtitles.demo import RealtimeDemoConfig, RealtimeSystemAudioTranscriptionDemo
from subtitles.vad import WebRtcVoiceActivityDetector

logger = logging.getLogger(__name__)
SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?。！？])\s+")


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
        self.root.geometry("1100x280+220+760")
        self.root.minsize(760, 180)

        self._drag_origin_x = 0
        self._drag_origin_y = 0

        self.status_var = tk.StringVar(value="Ready")
        self.subtitle_text: tk.Text | None = None

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

        subtitle_frame = tk.Frame(
            frame,
            bg="#111111",
        )
        subtitle_frame.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(subtitle_frame)
        scrollbar.pack(side="right", fill="y")

        subtitle_text = tk.Text(
            subtitle_frame,
            font=("Microsoft YaHei UI", 19, "bold"),
            fg="#f7f3e8",
            bg="#111111",
            insertbackground="#f7f3e8",
            relief="flat",
            borderwidth=0,
            wrap="word",
            padx=8,
            pady=8,
            yscrollcommand=scrollbar.set,
            spacing1=2,
            spacing2=4,
            spacing3=6,
            cursor="arrow",
        )
        subtitle_text.pack(side="left", fill="both", expand=True)
        subtitle_text.tag_configure(
            "committed",
            foreground="#f7f3e8",
            font=("Microsoft YaHei UI", 19, "bold"),
            justify="center",
        )
        subtitle_text.tag_configure(
            "unstable",
            foreground="#9ba3af",
            font=("Microsoft YaHei UI", 17),
            justify="center",
        )
        subtitle_text.tag_configure(
            "gap",
            spacing1=6,
            spacing3=6,
        )
        subtitle_text.configure(state="disabled")
        scrollbar.config(command=subtitle_text.yview)
        self.subtitle_text = subtitle_text

        for widget in [frame, header, status, subtitle_frame, subtitle_text]:
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
        self._render_subtitles(
            committed_text=state.committed_text,
            unstable_text=state.unstable_text,
        )
        self.status_var.set(state.status_text)
        logger.debug(
            "Overlay state updated: committed=%r unstable=%r status=%r",
            state.committed_text,
            state.unstable_text,
            state.status_text,
        )

    def _render_subtitles(self, *, committed_text: str, unstable_text: str) -> None:
        if self.subtitle_text is None:
            return

        self.subtitle_text.configure(state="normal")
        self.subtitle_text.delete("1.0", tk.END)

        if committed_text:
            self.subtitle_text.insert(tk.END, committed_text, ("committed",))

        if committed_text and unstable_text:
            self.subtitle_text.insert(tk.END, "\n", ("gap",))

        if unstable_text:
            self.subtitle_text.insert(tk.END, unstable_text, ("unstable",))

        if not committed_text and not unstable_text:
            self.subtitle_text.insert(tk.END, "...", ("unstable",))

        self.subtitle_text.configure(state="disabled")
        self.subtitle_text.see(tk.END)

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
            vad_detector=WebRtcVoiceActivityDetector(),
        )
        self.state_queue: queue.Queue[OverlaySubtitleState] = queue.Queue()
        self.stop_event = threading.Event()

    def _build_status_text(self, event) -> str:
        return (
            f"Listening  window={event.window_start:.1f}s-{event.window_end:.1f}s  "
            f"update={event.update_index}"
        )

    def _format_subtitle_text(self, text: str) -> str:
        normalized = " ".join(text.split()).strip()
        if not normalized:
            return ""

        sentences = [part.strip() for part in SENTENCE_BREAK_RE.split(normalized) if part.strip()]
        if not sentences:
            return normalized

        return "\n".join(sentences)

    def _worker(self) -> None:
        try:
            logger.info("Overlay worker started")
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

                committed = self._format_subtitle_text(
                    event.transcript_delta.committed_text
                )
                preview = self._format_subtitle_text(
                    event.transcript_delta.unstable_text
                )
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
            logger.exception("Overlay worker failed")
            self.state_queue.put(
                OverlaySubtitleState(
                    committed_text="",
                    unstable_text="",
                    status_text=f"Error: {exc}",
                )
            )
        finally:
            logger.info("Overlay worker stopped")
            self.stop_event.set()

    def run(self) -> None:
        worker = threading.Thread(target=self._worker, daemon=True)
        worker.start()
        window = SubtitleOverlayWindow()
        window.run(self.state_queue, self.stop_event)
