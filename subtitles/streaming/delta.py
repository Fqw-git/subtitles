from __future__ import annotations

from dataclasses import dataclass
import logging
import re

from subtitles.asr import TranscriptSegment, TranscriptWord

logger = logging.getLogger(__name__)

LEADING_GUARD_SECONDS = 1.0
MAX_ALIGNMENT_HEAD_SKIP_WORDS = 2


@dataclass(frozen=True)
class TranscriptDelta:
    full_text: str
    committed_text: str
    committed_increment: str
    unstable_text: str
    is_revision: bool


class TranscriptDeltaTracker:
    def __init__(self) -> None:
        self._committed_words: list[str] = []
        self._pending_words: list[str] = []

    def update(
        self,
        segments: list[TranscriptSegment],
        *,
        window_start: float,
        window_end: float,
        stability_seconds: float,
    ) -> TranscriptDelta:
        if stability_seconds < 0:
            raise ValueError("stability_seconds must be greater than or equal to 0.")

        previous_committed_words = list(self._committed_words)
        previous_pending_words = list(self._pending_words)
        stable_cutoff = window_end - stability_seconds
        leading_guard_seconds = 0.0
        if previous_committed_words:
            leading_guard_seconds = min(
                LEADING_GUARD_SECONDS,
                max(0.0, (window_end - window_start) / 2),
            )
        leading_guard_cutoff = window_start + leading_guard_seconds
        logger.debug(
            "Delta update start: window_start=%.3f window_end=%.3f stability_seconds=%.3f stable_cutoff=%.3f leading_guard_seconds=%.3f leading_guard_cutoff=%.3f previous_committed=%r previous_pending=%r segment_count=%s",
            window_start,
            window_end,
            stability_seconds,
            stable_cutoff,
            leading_guard_seconds,
            leading_guard_cutoff,
            self._join_words(previous_committed_words),
            self._join_words(previous_pending_words),
            len(segments),
        )
        words = self._flatten_words(segments)
        if words:
            logger.debug("Delta using word-level timestamps: word_count=%s", len(words))
            current_committed_words, current_unstable_words = self._build_word_partitions(
                words=words,
                window_start=window_start,
                leading_guard_cutoff=leading_guard_cutoff,
                stable_cutoff=stable_cutoff,
            )
        else:
            logger.debug("Delta falling back to segment-level timestamps")
            current_committed_words, current_unstable_words = self._build_segment_partitions(
                segments=segments,
                window_start=window_start,
                leading_guard_cutoff=leading_guard_cutoff,
                stable_cutoff=stable_cutoff,
            )

        current_committed_text = self._join_words(current_committed_words)
        if not current_committed_words:
            unstable_words = list(previous_pending_words) + list(current_unstable_words)
            delta = TranscriptDelta(
                full_text="\n".join(
                    part
                    for part in [
                        self._join_words(self._committed_words),
                        self._join_words(unstable_words),
                    ]
                    if part
                ),
                committed_text=self._join_words(self._committed_words),
                committed_increment="",
                unstable_text=self._join_words(unstable_words),
                is_revision=False,
            )
            logger.debug("Delta result with no committed words: %s", delta)
            return delta

        head_skip_words, overlap_length = self._find_best_alignment(
            previous_words=previous_committed_words,
            current_words=current_committed_words,
        )
        aligned_current_committed_words = current_committed_words[head_skip_words:]
        candidate_words = aligned_current_committed_words[overlap_length:]

        confirmed_words, next_pending_words = self._confirm_pending_words(
            previous_pending_words=previous_pending_words,
            candidate_words=candidate_words,
        )
        if confirmed_words:
            self._committed_words.extend(confirmed_words)
        self._pending_words = next_pending_words

        committed_text = self._join_words(self._committed_words)
        committed_increment = self._join_words(confirmed_words)
        unstable_words = self._build_unstable_words(
            dropped_prefix_words=current_committed_words[:head_skip_words],
            current_committed_words=aligned_current_committed_words,
            current_unstable_words=current_unstable_words,
            pending_words=self._pending_words,
        )
        unstable_text = self._join_words(unstable_words)
        full_text = "\n".join(part for part in [committed_text, unstable_text] if part)
        is_revision = (
            bool(previous_committed_words)
            and overlap_length == 0
            and head_skip_words == 0
            and bool(candidate_words)
        )

        delta = TranscriptDelta(
            full_text=full_text,
            committed_text=committed_text,
            committed_increment=committed_increment,
            unstable_text=unstable_text,
            is_revision=is_revision,
        )
        logger.debug(
            "Delta final result: head_skip_words=%s overlap_length=%s previous=%r current=%r aligned_current=%r candidate=%r confirmed=%r next_pending=%r delta=%s",
            head_skip_words,
            overlap_length,
            self._join_words(previous_committed_words),
            current_committed_text,
            self._join_words(aligned_current_committed_words),
            self._join_words(candidate_words),
            committed_increment,
            self._join_words(self._pending_words),
            delta,
        )
        return delta

    def _flatten_words(self, segments: list[TranscriptSegment]) -> list[TranscriptWord]:
        words: list[TranscriptWord] = []
        for segment in segments:
            words.extend(segment.words)
        return words

    def _build_word_partitions(
        self,
        *,
        words: list[TranscriptWord],
        window_start: float,
        leading_guard_cutoff: float,
        stable_cutoff: float,
    ) -> tuple[list[str], list[str]]:
        committed_words: list[str] = []
        unstable_words: list[str] = []

        for word in words:
            absolute_start = window_start + word.start
            absolute_end = window_start + word.end
            in_leading_guard = absolute_start < leading_guard_cutoff
            logger.debug(
                "Delta word: rel_start=%.3f rel_end=%.3f abs_start=%.3f abs_end=%.3f word=%r leading_guard=%s committed=%s",
                word.start,
                word.end,
                absolute_start,
                absolute_end,
                word.word,
                in_leading_guard,
                (not in_leading_guard) and absolute_end <= stable_cutoff,
            )
            if in_leading_guard:
                continue
            if absolute_end <= stable_cutoff:
                committed_words.append(word.word)
            else:
                unstable_words.append(word.word)

        return (committed_words, unstable_words)

    def _build_segment_partitions(
        self,
        *,
        segments: list[TranscriptSegment],
        window_start: float,
        leading_guard_cutoff: float,
        stable_cutoff: float,
    ) -> tuple[list[str], list[str]]:
        committed_words: list[str] = []
        unstable_words: list[str] = []

        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue

            absolute_start = window_start + segment.start
            absolute_end = window_start + segment.end
            in_leading_guard = absolute_start < leading_guard_cutoff
            logger.debug(
                "Delta segment: rel_start=%.3f rel_end=%.3f abs_start=%.3f abs_end=%.3f text=%r leading_guard=%s committed=%s",
                segment.start,
                segment.end,
                absolute_start,
                absolute_end,
                text,
                in_leading_guard,
                (not in_leading_guard) and absolute_end <= stable_cutoff,
            )
            if in_leading_guard:
                continue
            if absolute_end <= stable_cutoff:
                committed_words.extend(self._tokenize_text(text))
            else:
                unstable_words.extend(self._tokenize_text(text))

        return (committed_words, unstable_words)

    def _build_unstable_words(
        self,
        *,
        dropped_prefix_words: list[str],
        current_committed_words: list[str],
        current_unstable_words: list[str],
        pending_words: list[str],
    ) -> list[str]:
        unstable_words = list(dropped_prefix_words) + list(pending_words) + list(current_unstable_words)

        if not unstable_words:
            return []
        return unstable_words

    def _confirm_pending_words(
        self,
        *,
        previous_pending_words: list[str],
        candidate_words: list[str],
    ) -> tuple[list[str], list[str]]:
        if not candidate_words:
            logger.debug(
                "Delta pending unchanged: previous_pending=%r candidate=%r",
                self._join_words(previous_pending_words),
                self._join_words(candidate_words),
            )
            return ([], previous_pending_words)

        if not previous_pending_words:
            logger.debug(
                "Delta pending initialized: candidate=%r",
                self._join_words(candidate_words),
            )
            return ([], candidate_words)

        skip_words, overlap_length = self._find_best_alignment(
            previous_words=previous_pending_words,
            current_words=candidate_words,
        )
        aligned_candidate_words = candidate_words[skip_words:]
        if overlap_length <= 0:
            logger.debug(
                "Delta pending replaced: previous_pending=%r candidate=%r",
                self._join_words(previous_pending_words),
                self._join_words(candidate_words),
            )
            return ([], candidate_words)

        confirmed_words = aligned_candidate_words[:overlap_length]
        next_pending_words = aligned_candidate_words[overlap_length:]
        logger.debug(
            "Delta pending confirmed: skip_words=%s overlap_length=%s previous_pending=%r candidate=%r confirmed=%r next_pending=%r",
            skip_words,
            overlap_length,
            self._join_words(previous_pending_words),
            self._join_words(candidate_words),
            self._join_words(confirmed_words),
            self._join_words(next_pending_words),
        )
        return (confirmed_words, next_pending_words)

    def _join_words(self, words: list[str]) -> str:
        if not words:
            return ""

        text = ""
        punctuation = {".", ",", "!", "?", ":", ";", "%", ")", "]", "}", "'s", "n't", "'re", "'ve", "'ll", "'d", "'m"}
        opening = {"(", "[", "{", '"', "'"}

        for raw_word in words:
            word = raw_word.strip()
            if not word:
                continue

            if not text:
                text = word
                continue

            if word in punctuation or word.startswith(("'", ".", ",", "!", "?", ":", ";")):
                text += word
            elif text[-1] in "([{\"'":
                text += word
            elif word in opening:
                text += " " + word
            else:
                text += " " + word

        return text.strip()

    def _find_overlap_length(
        self,
        *,
        previous_words: list[str],
        current_words: list[str],
    ) -> int:
        if not previous_words or not current_words:
            return 0

        max_overlap = min(len(previous_words), len(current_words))
        for overlap_length in range(max_overlap, 0, -1):
            previous_slice = previous_words[-overlap_length:]
            current_slice = current_words[:overlap_length]
            if self._normalized_words(previous_slice) == self._normalized_words(current_slice):
                return overlap_length

        return 0

    def _find_best_alignment(
        self,
        *,
        previous_words: list[str],
        current_words: list[str],
    ) -> tuple[int, int]:
        if not current_words:
            return (0, 0)

        best_skip_words = 0
        best_overlap_length = self._find_overlap_length(
            previous_words=previous_words,
            current_words=current_words,
        )
        max_skip_words = min(MAX_ALIGNMENT_HEAD_SKIP_WORDS, len(current_words) - 1)
        for skip_words in range(1, max_skip_words + 1):
            overlap_length = self._find_overlap_length(
                previous_words=previous_words,
                current_words=current_words[skip_words:],
            )
            if overlap_length > best_overlap_length:
                best_skip_words = skip_words
                best_overlap_length = overlap_length

        if best_skip_words > 0:
            logger.debug(
                "Delta alignment skipped current prefix words: skip_words=%s skipped=%r overlap_length=%s",
                best_skip_words,
                self._join_words(current_words[:best_skip_words]),
                best_overlap_length,
            )

        return (best_skip_words, best_overlap_length)

    def _normalized_words(self, words: list[str]) -> list[str]:
        return [self._normalize_word(word) for word in words]

    def _normalize_word(self, word: str) -> str:
        normalized = word.strip().lower()
        normalized = normalized.replace("\u2019", "'")
        normalized = re.sub(r"^[^\w']+|[^\w']+$", "", normalized)
        return normalized

    def _tokenize_text(self, text: str) -> list[str]:
        return [token for token in text.split() if token]
