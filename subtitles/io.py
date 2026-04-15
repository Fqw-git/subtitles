from __future__ import annotations

import json
from pathlib import Path

from subtitles.asr.models import TranscriptResult


def save_transcript(result: TranscriptResult, output: Path) -> None:
    output.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def print_transcript(result: TranscriptResult, output_path: Path) -> None:
    print(result.text)
    print(f"\nSaved transcript to: {output_path}")
