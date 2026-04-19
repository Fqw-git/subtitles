from __future__ import annotations

from dataclasses import dataclass

from subtitles.engine.stabilizer.tokens import TimedToken


@dataclass(frozen=True)
class DeltaUpdateInputs:
    stable_cutoff: float
    current_tokens: list[TimedToken]
    current_tokens_trimmed: bool
    committed_tail_tokens: list[TimedToken]
    baseline_tokens: list[TimedToken]
    baseline_text: str
    current_text: str


@dataclass(frozen=True)
class DeltaResolution:
    confirmed_tokens: list[TimedToken]
    next_pending_tokens: list[TimedToken]
    committed_end_time: float
    provisional_end_time: float
    is_revision: bool
    baseline_skip_words: int = 0
    current_skip_words: int = 0
    matched_prefix_length: int = 0
