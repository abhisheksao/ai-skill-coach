"""Materially-similar-plan detector (research R6; FR-011 fallback path).

A rare safety net: a reasoned regeneration is expected to differ from the
plan it replaces already. Deliberately lightweight — stdlib difflib, no
embedding model, no new dependency — since this only needs to catch the
occasional case where the LLM barely changed anything.
"""

import difflib

_SIMILARITY_THRESHOLD = 0.85


def _normalize(description: str) -> str:
    return " ".join(description.lower().split())


def is_materially_similar(old_steps: list, new_steps: list) -> bool:
    """Order-insensitive: same step count and closely matching descriptions."""
    if len(old_steps) != len(new_steps):
        return False

    old_text = "\n".join(sorted(_normalize(s.description) for s in old_steps))
    new_text = "\n".join(sorted(_normalize(s.description) for s in new_steps))

    ratio = difflib.SequenceMatcher(None, old_text, new_text).ratio()
    return ratio >= _SIMILARITY_THRESHOLD
