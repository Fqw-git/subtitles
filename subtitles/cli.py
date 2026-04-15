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
from subtitles.io import print_transcript, save_transcript
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
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "capture":
            handle_capture_command(args)
            return

        if args.command == "capture-transcribe":
            handle_capture_transcribe_command(args)
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
    except (AudioCaptureError, SpeechRecognitionError) as exc:
        raise SystemExit(str(exc)) from exc

    raise SystemExit("Unknown command")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
