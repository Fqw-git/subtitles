from __future__ import annotations

from dataclasses import dataclass

from subtitles.asr import TranscriptSegment


@dataclass(frozen=True)
class TranscriptDelta:
    full_text: str
    committed_text: str
    committed_increment: str
    unstable_text: str
    is_revision: bool


class TranscriptDeltaTracker:
    def __init__(self) -> None:
        self._previous_committed_text = ""

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

        stable_cutoff = window_end - stability_seconds
        committed_parts: list[str] = []
        unstable_parts: list[str] = []

        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue

            absolute_end = window_start + segment.end
            if absolute_end <= stable_cutoff:
                committed_parts.append(text)
            else:
                unstable_parts.append(text)

        committed_text = "\n".join(committed_parts).strip()
        unstable_text = "\n".join(unstable_parts).strip()
        full_text = "\n".join(part for part in [committed_text, unstable_text] if part)

        previous = self._previous_committed_text.strip()
        if not committed_text:
            return TranscriptDelta(
                full_text=full_text,
                committed_text="",
                committed_increment="",
                unstable_text=unstable_text,
                is_revision=False,
            )

        if not previous:
            self._previous_committed_text = committed_text
            return TranscriptDelta(
                full_text=full_text,
                committed_text=committed_text,
                committed_increment=committed_text,
                unstable_text=unstable_text,
                is_revision=False,
            )

        prefix_length = self._common_prefix_length(previous, committed_text)
        committed_increment = committed_text[prefix_length:].strip()
        is_revision = prefix_length < len(previous)

        self._previous_committed_text = committed_text
        return TranscriptDelta(
            full_text=full_text,
            committed_text=committed_text,
            committed_increment=committed_increment,
            unstable_text=unstable_text,
            is_revision=is_revision,
        )

    def _common_prefix_length(self, left: str, right: str) -> int:
        limit = min(len(left), len(right))
        index = 0
        while index < limit and left[index] == right[index]:
            index += 1
        return index
