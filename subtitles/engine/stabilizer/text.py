from __future__ import annotations

import re

from subtitles.engine.stabilizer.tokens import TimedToken


def join_tokens(tokens: list[TimedToken]) -> str:
    if not tokens:
        return ""

    text = ""
    punctuation = {".", ",", "!", "?", ":", ";", "%", ")", "]", "}", "'s", "n't", "'re", "'ve", "'ll", "'d", "'m"}
    opening = {"(", "[", "{", '"', "'"}

    for token in tokens:
        word = token.text.strip()
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


def normalize_word(word: str) -> str:
    normalized = word.strip().lower()
    normalized = normalized.replace("\u2019", "'")
    normalized = re.sub(r"^[^\w']+|[^\w']+$", "", normalized)
    return normalized
