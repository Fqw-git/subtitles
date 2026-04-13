from __future__ import annotations

import argparse
import sys

from subtitles.audio import list_audio_devices, record_system_audio
from subtitles.config import (
    DEFAULT_AUDIO_OUTPUT,
    DEFAULT_BEAM_SIZE,
    DEFAULT_JSON_OUTPUT,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL,
    DEFAULT_RECORD_SECONDS,
)
from subtitles.io import print_transcript, save_transcript
from subtitles.transcriber import transcribe_audio
from subtitles.utils import resolve_output_path, validate_audio_file


def handle_record_command(args: argparse.Namespace) -> None:
    audio_path = resolve_output_path(args.audio_out)
    result_path = resolve_output_path(args.json_out)

    record_system_audio(audio_path, args.seconds, args.device)
    result = transcribe_audio(
        audio_path,
        model_name=args.model,
        language=args.language,
        beam_size=args.beam_size,
    )
    save_transcript(result, result_path)
    print_transcript(result, result_path)


def handle_transcribe_command(args: argparse.Namespace) -> None:
    audio_path = resolve_output_path(args.audio_file)
    result_path = resolve_output_path(args.json_out)

    validate_audio_file(audio_path)
    result = transcribe_audio(
        audio_path,
        model_name=args.model,
        language=args.language,
        beam_size=args.beam_size,
    )
    save_transcript(result, result_path)
    print_transcript(result, result_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record audio and transcribe speech into text."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    record_parser = subparsers.add_parser(
        "record",
        help="Record system audio first, then transcribe it.",
    )
    record_parser.add_argument("--seconds", type=int, default=DEFAULT_RECORD_SECONDS)
    record_parser.add_argument("--audio-out", default=DEFAULT_AUDIO_OUTPUT)
    record_parser.add_argument("--json-out", default=DEFAULT_JSON_OUTPUT)
    record_parser.add_argument("--device", default=None)
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

    subparsers.add_parser(
        "list-devices",
        help="List available Windows DirectShow audio devices through ffmpeg.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "record":
        handle_record_command(args)
        return

    if args.command == "transcribe":
        handle_transcribe_command(args)
        return

    if args.command == "list-devices":
        list_audio_devices()
        return

    raise SystemExit("Unknown command")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
