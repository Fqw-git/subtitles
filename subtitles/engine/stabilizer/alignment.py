from __future__ import annotations

from dataclasses import dataclass

from subtitles.engine.stabilizer.text import normalize_word
from subtitles.engine.stabilizer.tokens import TimedToken


@dataclass(frozen=True)
class AlignmentMatch:
    baseline_start: int = 0
    current_start: int = 0
    matched_length: int = 0


def find_best_local_alignment(
    *,
    baseline_tokens: list[TimedToken],
    current_tokens: list[TimedToken],
    max_head_skip_words: int,
) -> AlignmentMatch:
    if not baseline_tokens or not current_tokens:
        return AlignmentMatch()

    best_match = AlignmentMatch(
        matched_length=_find_common_prefix_length(
            baseline_tokens=baseline_tokens,
            current_tokens=current_tokens,
        )
    )
    max_current_skip = min(max_head_skip_words, len(current_tokens) - 1)

    for baseline_start in range(len(baseline_tokens)):
        for current_start in range(max_current_skip + 1):
            candidate = AlignmentMatch(
                baseline_start=baseline_start,
                current_start=current_start,
                matched_length=_find_common_prefix_length(
                    baseline_tokens=baseline_tokens[baseline_start:],
                    current_tokens=current_tokens[current_start:],
                ),
            )
            if _is_better_match(candidate, best_match):
                best_match = candidate

    return best_match


def _is_better_match(candidate: AlignmentMatch, current_best: AlignmentMatch) -> bool:
    if candidate.matched_length != current_best.matched_length:
        return candidate.matched_length > current_best.matched_length

    candidate_total_skip = candidate.baseline_start + candidate.current_start
    current_total_skip = current_best.baseline_start + current_best.current_start
    if candidate_total_skip != current_total_skip:
        return candidate_total_skip < current_total_skip

    if candidate.current_start != current_best.current_start:
        return candidate.current_start < current_best.current_start

    return candidate.baseline_start < current_best.baseline_start


def _find_common_prefix_length(
    *,
    baseline_tokens: list[TimedToken],
    current_tokens: list[TimedToken],
) -> int:
    max_length = min(len(baseline_tokens), len(current_tokens))
    prefix_length = 0
    for index in range(max_length):
        if normalize_word(baseline_tokens[index].text) != normalize_word(
            current_tokens[index].text
        ):
            break
        prefix_length += 1
    return prefix_length
