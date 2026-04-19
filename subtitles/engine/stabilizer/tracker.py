from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from subtitles.asr import TranscriptSegment
from subtitles.engine.stabilizer.alignment import find_best_local_alignment
from subtitles.engine.stabilizer.models import TranscriptDelta
from subtitles.engine.stabilizer.state import DeltaResolution, DeltaUpdateInputs
from subtitles.engine.stabilizer.text import join_tokens
from subtitles.engine.stabilizer.tokens import (
    TimedToken,
    build_committed_tail,
    flatten_tokens,
    stable_prefix_length,
)

if TYPE_CHECKING:
    from subtitles.engine.buffering.snapshot import BufferSnapshot

logger = logging.getLogger(__name__)

ALIGNMENT_TAIL_MAX_WORDS = 24
MAX_ALIGNMENT_HEAD_SKIP_WORDS = 2
UNSTABLE_SNAPSHOT_HEAD_TRIM_TOKENS = 1


class TranscriptDeltaTracker:
    def __init__(self, stability_seconds: float = 0.5) -> None:
        if stability_seconds < 0:
            raise ValueError("stability_seconds must be greater than or equal to 0.")

        self.stability_seconds = stability_seconds
        self._committed_tokens: list[TimedToken] = []
        self._pending_tokens: list[TimedToken] = []

    def update(
        self,
        segments: list[TranscriptSegment],
        *,
        snapshot: BufferSnapshot,
    ) -> TranscriptDelta:
        update_inputs = self._prepare_update_inputs(
            segments=segments,
            snapshot=snapshot,
        )

        logger.debug(
            "Delta update start: window_start=%.3f window_end=%.3f starts_with_speech_start=%s current_tokens_trimmed=%s stable_cutoff=%.3f committed_end_time=%.3f baseline=%r current=%r committed_tail=%r pending=%r",
            snapshot.window_start,
            snapshot.window_end,
            snapshot.starts_with_speech_start,
            update_inputs.current_tokens_trimmed,
            update_inputs.stable_cutoff,
            snapshot.committed_end_time,
            update_inputs.baseline_text,
            update_inputs.current_text,
            join_tokens(update_inputs.committed_tail_tokens),
            join_tokens(self._pending_tokens),
        )

        if not update_inputs.current_tokens:
            delta = self._build_delta(
                confirmed_tokens=[],
                next_pending_tokens=self._pending_tokens,
                is_revision=False,
                committed_end_time=snapshot.committed_end_time,
                provisional_end_time=snapshot.committed_end_time,
                baseline_text=update_inputs.baseline_text,
                current_text=update_inputs.current_text,
            )
            logger.debug("Delta update with empty current tokens: %s", delta)
            return delta

        if not update_inputs.baseline_tokens:
            next_pending_tokens = update_inputs.current_tokens
            delta = self._build_delta(
                confirmed_tokens=[],
                next_pending_tokens=next_pending_tokens,
                is_revision=False,
                committed_end_time=snapshot.committed_end_time,
                provisional_end_time=update_inputs.current_tokens[-1].end,
                baseline_text=update_inputs.baseline_text,
                current_text=update_inputs.current_text,
            )
            self._pending_tokens = next_pending_tokens
            logger.debug("Delta bootstrap pending initialized: %s", delta)
            return delta

        resolution = self._resolve_delta(
            update_inputs=update_inputs,
            committed_end_time=snapshot.committed_end_time,
        )
        delta = self._build_delta(
            confirmed_tokens=resolution.confirmed_tokens,
            next_pending_tokens=resolution.next_pending_tokens,
            is_revision=resolution.is_revision,
            committed_end_time=resolution.committed_end_time,
            provisional_end_time=resolution.provisional_end_time,
            baseline_text=update_inputs.baseline_text,
            current_text=update_inputs.current_text,
        )
        self._apply_resolution(resolution)
        logger.debug(
            "Delta final result: baseline_skip_words=%s current_skip_words=%s matched_prefix_length=%s confirmed=%r next_pending=%r committed_end_time=%.3f provisional_end_time=%.3f delta=%s",
            resolution.baseline_skip_words,
            resolution.current_skip_words,
            resolution.matched_prefix_length,
            join_tokens(resolution.confirmed_tokens),
            join_tokens(resolution.next_pending_tokens),
            delta.committed_end_time,
            delta.provisional_end_time,
            delta,
        )
        return delta

    def _prepare_update_inputs(
        self,
        *,
        segments: list[TranscriptSegment],
        snapshot: BufferSnapshot,
    ) -> DeltaUpdateInputs:
        stable_cutoff = snapshot.window_end - self.stability_seconds
        raw_current_tokens = flatten_tokens(segments, window_start=snapshot.window_start)
        current_tokens, current_tokens_trimmed = self._prepare_current_tokens(
            raw_current_tokens,
            starts_with_speech_start=snapshot.starts_with_speech_start,
        )
        committed_tail_tokens = build_committed_tail(
            self._committed_tokens,
            snapshot_start_time=snapshot.window_start,
            committed_end_time=snapshot.committed_end_time,
            alignment_tail_max_words=ALIGNMENT_TAIL_MAX_WORDS,
        )
        baseline_tokens = committed_tail_tokens + list(self._pending_tokens)
        return DeltaUpdateInputs(
            stable_cutoff=stable_cutoff,
            current_tokens=current_tokens,
            current_tokens_trimmed=current_tokens_trimmed,
            committed_tail_tokens=committed_tail_tokens,
            baseline_tokens=baseline_tokens,
            baseline_text=join_tokens(baseline_tokens),
            current_text=join_tokens(current_tokens),
        )

    def _prepare_current_tokens(
        self,
        current_tokens: list[TimedToken],
        *,
        starts_with_speech_start: bool,
    ) -> tuple[list[TimedToken], bool]:
        if starts_with_speech_start:
            return (current_tokens, False)

        trim_count = min(UNSTABLE_SNAPSHOT_HEAD_TRIM_TOKENS, len(current_tokens))
        if trim_count <= 0:
            return (current_tokens, False)

        return (current_tokens[trim_count:], True)

    def _resolve_delta(
        self,
        *,
        update_inputs: DeltaUpdateInputs,
        committed_end_time: float,
    ) -> DeltaResolution:
        alignment = find_best_local_alignment(
            baseline_tokens=update_inputs.baseline_tokens,
            current_tokens=update_inputs.current_tokens,
            max_head_skip_words=MAX_ALIGNMENT_HEAD_SKIP_WORDS,
        )
        committed_tail_length = len(update_inputs.committed_tail_tokens)
        pending_start = committed_tail_length
        overlap_start = alignment.baseline_start
        overlap_end = alignment.baseline_start + alignment.matched_length
        pending_overlap_start = max(pending_start, overlap_start)
        pending_overlap_end = max(
            pending_overlap_start,
            min(overlap_end, len(update_inputs.baseline_tokens)),
        )
        overlap_pending_length = pending_overlap_end - pending_overlap_start
        current_pending_start = alignment.current_start + max(
            0,
            pending_start - overlap_start,
        )
        candidate_confirmed_start = alignment.current_start + max(
            0,
            pending_overlap_start - overlap_start,
        )
        candidate_confirmed_tokens = update_inputs.current_tokens[
            candidate_confirmed_start : candidate_confirmed_start + overlap_pending_length
        ]
        can_confirm_overlap = pending_overlap_start == pending_start
        if not can_confirm_overlap:
            candidate_confirmed_tokens = []
        confirmed_length = stable_prefix_length(
            candidate_confirmed_tokens,
            stable_cutoff=update_inputs.stable_cutoff,
        )
        confirmed_tokens = candidate_confirmed_tokens[:confirmed_length]
        preserved_pending_prefix = update_inputs.baseline_tokens[
            pending_start:pending_overlap_start
        ]
        if alignment.matched_length > 0:
            current_pending_tokens = update_inputs.current_tokens[current_pending_start:]
            next_pending_tokens = preserved_pending_prefix + current_pending_tokens[
                confirmed_length:
            ]
        else:
            next_pending_tokens = update_inputs.current_tokens
        next_committed_end_time = committed_end_time
        if confirmed_tokens:
            next_committed_end_time = max(next_committed_end_time, confirmed_tokens[-1].end)
        provisional_source_tokens = next_pending_tokens or confirmed_tokens
        provisional_end_time = committed_end_time
        if provisional_source_tokens:
            provisional_end_time = provisional_source_tokens[-1].end

        return DeltaResolution(
            confirmed_tokens=confirmed_tokens,
            next_pending_tokens=next_pending_tokens,
            committed_end_time=next_committed_end_time,
            provisional_end_time=provisional_end_time,
            is_revision=bool(self._pending_tokens) and alignment.matched_length == 0,
            baseline_skip_words=alignment.baseline_start,
            current_skip_words=alignment.current_start,
            matched_prefix_length=alignment.matched_length,
        )

    def _apply_resolution(self, resolution: DeltaResolution) -> None:
        self._committed_tokens.extend(resolution.confirmed_tokens)
        self._pending_tokens = resolution.next_pending_tokens

    def _build_delta(
        self,
        *,
        confirmed_tokens: list[TimedToken],
        next_pending_tokens: list[TimedToken],
        is_revision: bool,
        committed_end_time: float,
        provisional_end_time: float,
        baseline_text: str,
        current_text: str,
    ) -> TranscriptDelta:
        committed_text = join_tokens(self._committed_tokens + confirmed_tokens)
        committed_increment = join_tokens(confirmed_tokens)
        unstable_text = join_tokens(next_pending_tokens)
        full_text = "\n".join(part for part in [committed_text, unstable_text] if part)
        return TranscriptDelta(
            full_text=full_text,
            committed_text=committed_text,
            committed_increment=committed_increment,
            unstable_text=unstable_text,
            is_revision=is_revision,
            committed_end_time=committed_end_time,
            provisional_end_time=provisional_end_time,
            baseline_text=baseline_text,
            current_text=current_text,
        )
