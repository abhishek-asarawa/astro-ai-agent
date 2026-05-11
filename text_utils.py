"""Shared text cleanup helpers for model output."""

import re

_REASONING_BLOCK_RE = re.compile(
    r"(?:<think>.*?</think>|<redacted_reasoning>.*?</redacted_reasoning>)",
    re.IGNORECASE | re.DOTALL,
)

# Citation tags the model is instructed to use (customers usually should not see raw IDs).
_REF_TAG_RE = re.compile(r"\s*\[ref:[^\]]+\]", re.IGNORECASE)


def strip_ref_tags(text: str) -> str:
    """Remove [ref:...] citation markers from visible copy."""
    if not text:
        return ""
    return _REF_TAG_RE.sub("", text).strip()


def extract_ref_ids(text: str) -> list[str]:
    """Return ref ids in order of appearance (for optional practitioner expander)."""
    if not text:
        return []
    return re.findall(r"(?i)\[ref:([^\]]+)\]", text)


def format_consumer_text(text: str) -> str:
    """Strip refs and tighten whitespace for end-user display."""
    s = strip_ref_tags(text or "")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def strip_reasoning_blocks(text: str) -> str:
    """Remove <think> and <redacted_reasoning> blocks from model output."""
    if not text:
        return ""
    return _REASONING_BLOCK_RE.sub("", text).strip()
