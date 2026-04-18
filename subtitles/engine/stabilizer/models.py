from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptDelta:
    full_text: str
    committed_text: str
    committed_increment: str
    unstable_text: str
    is_revision: bool
