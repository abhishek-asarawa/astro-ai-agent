"""Shared scoring helpers for evaluation harnesses."""


def score_keyword_coverage(response: str, expected_keywords: list[str]) -> float:
    if not (response or "").strip():
        return 0.0
    text = response.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in text)
    return hits / max(1, len(expected_keywords))
