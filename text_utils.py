"""Shared text cleanup helpers for model output."""

import re

_REASONING_BLOCK_RE = re.compile(
    r"(?:<think>.*?</think>|<redacted_reasoning>.*?</redacted_reasoning>)",
    re.IGNORECASE | re.DOTALL,
)

# Citation tags the model is instructed to use (customers usually should not see raw IDs).
_REF_TAG_RE = re.compile(r"\s*\[ref:[^\]]+\]", re.IGNORECASE)

# Light glossary: explain common jargon when it slips through the model.
_JARGON_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bVimshottari\s+Dasha\b", re.I), "life-period cycle"),
    (re.compile(r"\bMahadasha\b", re.I), "main life chapter"),
    (re.compile(r"\bAntardasha\b", re.I), "sub-period"),
    (re.compile(r"\bdebilitated\b", re.I), "weakened in the chart"),
    (re.compile(r"\bexalted\b", re.I), "strong in the chart"),
    (re.compile(r"\btrik\s+house(?:s)?\b", re.I), "challenging house area"),
    (re.compile(r"\b(\d+)(?:st|nd|rd|th)\s+lord\b", re.I), r"planet linked to life area \1"),
    (re.compile(r"\bnative\b", re.I), "you"),
    (re.compile(r"\bthe\s+native\b", re.I), "you"),
]


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


def soften_jargon(text: str) -> str:
    """Apply small safe replacements for common astrology terms."""
    if not text:
        return ""
    out = text
    for pattern, replacement in _JARGON_REPLACEMENTS:
        out = pattern.sub(replacement, out)
    return out


def format_consumer_text(text: str) -> str:
    """Strip refs, soften jargon, and tighten whitespace for end-user display."""
    s = strip_ref_tags(text or "")
    s = soften_jargon(s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def strip_reasoning_blocks(text: str) -> str:
    """Remove <think> and <redacted_reasoning> blocks from model output."""
    if not text:
        return ""
    return _REASONING_BLOCK_RE.sub("", text).strip()
