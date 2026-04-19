from __future__ import annotations

from dataclasses import dataclass

from subtitles.asr import TranscriptSegment, TranscriptWord


@dataclass(frozen=True)
class TimedToken:
    text: str
    start: float
    end: float


def flatten_tokens(
    segments: list[TranscriptSegment],
    *,
    window_start: float,
) -> list[TimedToken]:
    tokens = _flatten_word_tokens(segments, window_start=window_start)
    if tokens:
        return tokens
    return _flatten_segment_tokens(segments, window_start=window_start)


def stable_prefix_length(
    tokens: list[TimedToken],
    *,
    stable_cutoff: float,
) -> int:
    stable_length = 0
    for token in tokens:
        if token.end > stable_cutoff:
            break
        stable_length += 1
    return stable_length


def build_committed_tail(
    committed_tokens: list[TimedToken],
    *,
    snapshot_start_time: float,
    committed_end_time: float,
    alignment_tail_max_words: int,
) -> list[TimedToken]:
    if not committed_tokens:
        return []

    overlap_start_time = snapshot_start_time
    overlap_end_time = committed_end_time
    if overlap_start_time >= overlap_end_time:
        return []

    tail_tokens = [
        token
        for token in committed_tokens
        if token.end > overlap_start_time and token.start < overlap_end_time
    ]
    if len(tail_tokens) > alignment_tail_max_words:
        return tail_tokens[-alignment_tail_max_words:]
    return tail_tokens


def _flatten_word_tokens(
    segments: list[TranscriptSegment],
    *,
    window_start: float,
) -> list[TimedToken]:
    tokens: list[TimedToken] = []
    for segment in segments:
        for word in segment.words:
            token = _build_word_token(word, window_start=window_start)
            if token is not None:
                tokens.append(token)
    return tokens


def _build_word_token(
    word: TranscriptWord,
    *,
    window_start: float,
) -> TimedToken | None:
    text = word.word.strip()
    if not text:
        return None
    return TimedToken(
        text=text,
        start=window_start + word.start,
        end=window_start + word.end,
    )


def _flatten_segment_tokens(
    segments: list[TranscriptSegment],
    *,
    window_start: float,
) -> list[TimedToken]:
    tokens: list[TimedToken] = []
    for segment in segments:
        raw_tokens = _tokenize_text(segment.text.strip())
        if not raw_tokens:
            continue
        absolute_start = window_start + segment.start
        absolute_end = window_start + segment.end
        segment_duration = max(absolute_end - absolute_start, 0.0)
        token_duration = segment_duration / len(raw_tokens) if raw_tokens else 0.0
        for index, raw_token in enumerate(raw_tokens):
            token_start = absolute_start + (index * token_duration)
            token_end = (
                absolute_end
                if index == len(raw_tokens) - 1
                else token_start + token_duration
            )
            tokens.append(
                TimedToken(
                    text=raw_token,
                    start=token_start,
                    end=token_end,
                )
            )
    return tokens


def _tokenize_text(text: str) -> list[str]:
    return [token for token in text.split() if token]
