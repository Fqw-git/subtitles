from __future__ import annotations

import argparse
import sys

from subtitles.asr import (
    FasterWhisperRecognizer,
    SpeechRecognitionConfig,
    SpeechRecognitionError,
)
from subtitles.audio import (
    AudioCaptureConfig,
    AudioCaptureError,
    PyAudioWasapiLoopbackCapturer,
)
from subtitles.config import (
    DEFAULT_AUDIO_OUTPUT,
    DEFAULT_BEAM_SIZE,
    DEFAULT_CHANNELS,
    DEFAULT_JSON_OUTPUT,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    DEFAULT_RECORD_SECONDS,
    DEFAULT_SAMPLE_RATE,
)
from subtitles.demo import (
    RealtimeDemoConfig,
    RealtimeSystemAudioTranscriptionDemo,
)
from subtitles.io import print_transcript, save_transcript
from subtitles.logging_utils import configure_logging
from subtitles.overlay import SubtitleOverlayApp
from subtitles.utils import resolve_output_path, validate_audio_file


def build_capture_config(args: argparse.Namespace) -> AudioCaptureConfig:
    return AudioCaptureConfig(
        seconds=args.seconds,
        sample_rate=args.sample_rate,
        channels=args.channels,
        frames_per_buffer=args.frames_per_buffer,
        device_name=args.device,
    )


def build_recognition_config(args: argparse.Namespace) -> SpeechRecognitionConfig:
    return SpeechRecognitionConfig(
        model_name=args.model,
        language=args.language,
        beam_size=args.beam_size,
        word_timestamps=getattr(args, "word_timestamps", False),
    )


def handle_capture_command(args: argparse.Namespace) -> None:
    capturer = PyAudioWasapiLoopbackCapturer()
    audio_path = resolve_output_path(args.audio_out)
    result = capturer.capture_to_file(audio_path, build_capture_config(args))
    print(f"Saved recorded system audio to: {result.output_path}")
    print(f"Captured from device: {result.device.name}")


def handle_capture_transcribe_command(args: argparse.Namespace) -> None:
    capturer = PyAudioWasapiLoopbackCapturer()
    recognizer = FasterWhisperRecognizer()
    audio_path = resolve_output_path(args.audio_out)
    result_path = resolve_output_path(args.json_out)

    capture_result = capturer.capture_to_file(audio_path, build_capture_config(args))
    transcript = recognizer.transcribe_file(
        audio_path,
        build_recognition_config(args),
    )
    save_transcript(transcript, result_path)
    print(f"Captured from device: {capture_result.device.name}")
    print_transcript(transcript, result_path)


def handle_demo_command(args: argparse.Namespace) -> None:
    demo = RealtimeSystemAudioTranscriptionDemo(
        capturer=PyAudioWasapiLoopbackCapturer(),
        recognizer=FasterWhisperRecognizer(),
    )

    print("Starting realtime demo. Press Ctrl+C to stop.")
    for event in demo.iter_events(
        RealtimeDemoConfig(
            capture=AudioCaptureConfig(
                seconds=0,
                sample_rate=args.sample_rate,
                channels=args.channels,
                frames_per_buffer=args.frames_per_buffer,
                device_name=args.device,
            ),
            recognition=build_recognition_config(args),
            window_seconds=args.window_seconds,
            step_seconds=args.step_seconds,
            stability_seconds=args.stability_seconds,
            max_updates=args.max_updates,
        )
    ):
        print(
            f"[update {event.update_index}] "
            f"window={event.window_start:.2f}s-{event.window_end:.2f}s"
        )
        if event.transcript_delta.committed_increment:
            if event.transcript_delta.is_revision:
                print(f"[revised] {event.transcript_delta.committed_increment}")
            else:
                print(event.transcript_delta.committed_increment)
        elif event.transcript_delta.committed_text:
            print("(no new committed text)")
        elif event.transcript_delta.unstable_text:
            print("(waiting for stable text)")
        else:
            print("(no speech detected)")

        if event.transcript_delta.unstable_text:
            print(f"[preview] {event.transcript_delta.unstable_text}")
        print()


def handle_overlay_command(args: argparse.Namespace) -> None:
    app = SubtitleOverlayApp(
        RealtimeDemoConfig(
            capture=AudioCaptureConfig(
                seconds=0,
                sample_rate=args.sample_rate,
                channels=args.channels,
                frames_per_buffer=args.frames_per_buffer,
                device_name=args.device,
            ),
            recognition=build_recognition_config(args),
            window_seconds=args.window_seconds,
            step_seconds=args.step_seconds,
            stability_seconds=args.stability_seconds,
            max_updates=args.max_updates,
        )
    )
    app.run()


def handle_transcribe_command(args: argparse.Namespace) -> None:
    recognizer = FasterWhisperRecognizer()
    audio_path = resolve_output_path(args.audio_file)
    result_path = resolve_output_path(args.json_out)

    validate_audio_file(audio_path)
    result = recognizer.transcribe_file(
        audio_path,
        build_recognition_config(args),
    )
    save_transcript(result, result_path)
    print_transcript(result, result_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record audio and transcribe speech into text."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    record_audio_parser = subparsers.add_parser(
        "capture",
        help="Capture system playback audio through WASAPI loopback and save it as a wav file.",
    )
    record_audio_parser.add_argument(
        "--seconds", type=int, default=DEFAULT_RECORD_SECONDS
    )
    record_audio_parser.add_argument("--audio-out", default=DEFAULT_AUDIO_OUTPUT)
    record_audio_parser.add_argument("--device", default=None)
    record_audio_parser.add_argument(
        "--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE
    )
    record_audio_parser.add_argument("--channels", type=int, default=DEFAULT_CHANNELS)
    record_audio_parser.add_argument("--frames-per-buffer", type=int, default=1024)

    record_parser = subparsers.add_parser(
        "capture-transcribe",
        help="Capture system playback audio through WASAPI loopback, then transcribe it.",
    )
    record_parser.add_argument("--seconds", type=int, default=DEFAULT_RECORD_SECONDS)
    record_parser.add_argument("--audio-out", default=DEFAULT_AUDIO_OUTPUT)
    record_parser.add_argument("--json-out", default=DEFAULT_JSON_OUTPUT)
    record_parser.add_argument("--device", default=None)
    record_parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    record_parser.add_argument("--channels", type=int, default=DEFAULT_CHANNELS)
    record_parser.add_argument("--frames-per-buffer", type=int, default=1024)
    record_parser.add_argument("--model", default=DEFAULT_MODEL)
    record_parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    record_parser.add_argument("--beam-size", type=int, default=DEFAULT_BEAM_SIZE)

    demo_parser = subparsers.add_parser(
        "demo",
        help="Run a realtime demo: capture system audio in chunks and transcribe each chunk.",
    )
    demo_parser.add_argument("--window-seconds", type=float, default=6.0)
    demo_parser.add_argument("--step-seconds", type=float, default=1.0)
    demo_parser.add_argument("--stability-seconds", type=float, default=2.0)
    demo_parser.add_argument("--device", default=None)
    demo_parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    demo_parser.add_argument("--channels", type=int, default=DEFAULT_CHANNELS)
    demo_parser.add_argument("--frames-per-buffer", type=int, default=1024)
    demo_parser.add_argument("--max-updates", type=int, default=None)
    demo_parser.add_argument("--model", default=DEFAULT_MODEL)
    demo_parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    demo_parser.add_argument("--beam-size", type=int, default=DEFAULT_BEAM_SIZE)
    demo_parser.add_argument(
        "--word-timestamps",
        action=argparse.BooleanOptionalAction,
        default=True,
    )

    overlay_parser = subparsers.add_parser(
        "overlay",
        help="Show realtime subtitles in a floating window.",
    )
    overlay_parser.add_argument("--window-seconds", type=float, default=6.0)
    overlay_parser.add_argument("--step-seconds", type=float, default=0.5)
    overlay_parser.add_argument("--stability-seconds", type=float, default=2.0)
    overlay_parser.add_argument("--device", default=None)
    overlay_parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    overlay_parser.add_argument("--channels", type=int, default=DEFAULT_CHANNELS)
    overlay_parser.add_argument("--frames-per-buffer", type=int, default=1024)
    overlay_parser.add_argument("--max-updates", type=int, default=None)
    overlay_parser.add_argument("--model", default=DEFAULT_MODEL)
    overlay_parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    overlay_parser.add_argument("--beam-size", type=int, default=DEFAULT_BEAM_SIZE)
    overlay_parser.add_argument(
        "--word-timestamps",
        action=argparse.BooleanOptionalAction,
        default=True,
    )

    transcribe_parser = subparsers.add_parser(
        "transcribe",
        help="Transcribe an existing audio file.",
    )
    transcribe_parser.add_argument("audio_file")
    transcribe_parser.add_argument("--json-out", default=DEFAULT_JSON_OUTPUT)
    transcribe_parser.add_argument("--model", default=DEFAULT_MODEL)
    transcribe_parser.add_argument("--language", default=DEFAULT_LANGUAGE)
    transcribe_parser.add_argument("--beam-size", type=int, default=DEFAULT_BEAM_SIZE)

    subparsers.add_parser("devices", help="List available WASAPI loopback devices.")

    return parser


def main() -> None:
    log_path = configure_logging()
    parser = build_parser()
    args = parser.parse_args()
    print(f"Logs: {log_path}")

    try:
        if args.command == "capture":
            handle_capture_command(args)
            return

        if args.command == "capture-transcribe":
            handle_capture_transcribe_command(args)
            return

        if args.command == "demo":
            handle_demo_command(args)
            return

        if args.command == "overlay":
            handle_overlay_command(args)
            return

        if args.command == "transcribe":
            handle_transcribe_command(args)
            return

        if args.command == "devices":
            capturer = PyAudioWasapiLoopbackCapturer()
            devices = capturer.list_devices()
            print("Available WASAPI loopback devices:")
            for device in devices:
                suffix = " (default)" if device.is_default else ""
                print(f"- {device.name}{suffix}")
            return
    except (AudioCaptureError, SpeechRecognitionError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    raise SystemExit("Unknown command")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
