from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptDelta:
    full_text: str
    committed_text: str
    committed_increment: str
    unstable_text: str
    is_revision: bool
    committed_end_time: float = 0.0
    provisional_end_time: float = 0.0
    baseline_text: str = ""
    current_text: str = ""
