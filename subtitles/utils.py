from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def run_cmd(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as exc:
        raise SystemExit(f"Command not found: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Command failed: {' '.join(cmd)}") from exc


def ensure_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit(
            "ffmpeg was not found in PATH. Please install ffmpeg first."
        )
    return ffmpeg


def resolve_output_path(raw_path: str) -> Path:
    return Path(raw_path).expanduser().resolve()


def validate_audio_file(audio_path: Path) -> None:
    if not audio_path.exists():
        raise SystemExit(f"Audio file not found: {audio_path}")
    if not audio_path.is_file():
        raise SystemExit(f"Audio path is not a file: {audio_path}")
