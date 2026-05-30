"""Validation for golden evaluation case JSON files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from astro_agent.routing.intent_router import SUPPORTED_INTENTS
except ImportError:
    from intent_router import SUPPORTED_INTENTS  # backward compat

_BIRTH_FIELDS = ("year", "month", "day", "hour", "minute", "city_name")


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    source: str
    question: str
    expected_intent: str
    birth: dict[str, Any]
    expected_keywords: list[str]
    tags: list[str]
    bphs_chapter_hint: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "GoldenCase":
        case_id = (raw.get("case_id") or "").strip()
        if not case_id:
            raise ValueError("GoldenCase missing case_id")

        question = (raw.get("question") or "").strip()
        if not question:
            raise ValueError(f"GoldenCase {case_id!r} missing question")

        expected_intent = (raw.get("expected_intent") or "").strip().lower()
        if expected_intent not in SUPPORTED_INTENTS:
            raise ValueError(
                f"GoldenCase {case_id!r} has invalid expected_intent {expected_intent!r}; "
                f"expected one of {SUPPORTED_INTENTS}"
            )

        birth = raw.get("birth")
        if not isinstance(birth, dict):
            raise ValueError(f"GoldenCase {case_id!r} birth must be an object")
        missing = [f for f in _BIRTH_FIELDS if f not in birth]
        if missing:
            raise ValueError(f"GoldenCase {case_id!r} birth missing fields: {missing}")

        keywords = raw.get("expected_keywords")
        if not isinstance(keywords, list) or not keywords:
            raise ValueError(f"GoldenCase {case_id!r} expected_keywords must be a non-empty list")

        tags_raw = raw.get("tags") or []
        if not isinstance(tags_raw, list):
            raise ValueError(f"GoldenCase {case_id!r} tags must be a list")
        tags = [str(t).strip() for t in tags_raw if str(t).strip()]

        source = (raw.get("source") or "").strip()
        hint = raw.get("bphs_chapter_hint")
        bphs_chapter_hint = str(hint).strip() if hint else None

        return cls(
            case_id=case_id,
            source=source,
            question=question,
            expected_intent=expected_intent,
            birth=dict(birth),
            expected_keywords=[str(k).strip() for k in keywords if str(k).strip()],
            tags=tags,
            bphs_chapter_hint=bphs_chapter_hint,
        )


def load_golden_cases(path: str) -> list[GoldenCase]:
    import json
    from pathlib import Path

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Golden file {path} must be a JSON array")
    return [GoldenCase.from_dict(item) for item in data]
