"""Shared text cleanup helpers for model output."""

import re

_REASONING_BLOCK_RE = re.compile(
    r"(?:<think>.*?</think>|<redacted_reasoning>.*?</redacted_reasoning>)",
    re.IGNORECASE | re.DOTALL,
)


def strip_reasoning_blocks(text: str) -> str:
    """Remove <think> and <redacted_reasoning> blocks from model output."""
    if not text:
        return ""
    return _REASONING_BLOCK_RE.sub("", text).strip()
