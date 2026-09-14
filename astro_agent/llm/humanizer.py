"""Second-pass LLM rewrite: structured reading -> natural chat prose."""

from __future__ import annotations

from astro_agent.llm import config as llm_cfg
from astro_agent.llm.client import query_ollama_once
from astro_agent.utils.response_sections import format_chat_answer_fallback, parse_structured_answer
from astro_agent.utils.text_utils import format_consumer_text

HUMANIZE_TIMEOUT_S = 25
_MIN_HUMANIZED_CHARS = 20


def humanize_answer(
    raw_answer: str,
    user_question: str,
    *,
    model_name: str | None = None,
    timeout_s: int = HUMANIZE_TIMEOUT_S,
    num_ctx: int | None = None,
    parsed: dict | None = None,
    grounded: bool = False,
) -> str:
    """Rewrite a structured reading, or preserve validated RAG output."""
    resolved = parsed if parsed is not None else parse_structured_answer(raw_answer)
    if grounded:
        # A second free-form model call cannot be checked against the retrieved
        # chunks here. Keep the already validated structured answer instead of
        # exposing an ungrounded rewrite to RAG users.
        return format_chat_answer_fallback(resolved, raw_answer)

    cleaned = format_consumer_text(raw_answer or "")
    prompt = (
        "Rewrite the following astrology reading as one warm, direct chat reply to the user's question. "
        "Do not use section headers or labels (no 'Summary', 'Evidence', 'Risk', 'Opportunity', 'Remedies', 'Confidence'). "
        "Blend the reasoning and any practical suggestions into flowing paragraphs. "
        "Do not invent facts. Do not state a numeric confidence score.\n\n"
        f"User question: {user_question}\n\nReading:\n{cleaned}"
    )
    text = query_ollama_once(
        prompt,
        temperature=llm_cfg.HUMANIZER_TEMPERATURE,
        timeout_s=timeout_s,
        model_name=model_name,
        num_ctx=num_ctx,
    )
    if not text or len(text.strip()) < _MIN_HUMANIZED_CHARS:
        resolved = parsed if parsed is not None else parse_structured_answer(raw_answer)
        return format_chat_answer_fallback(resolved, raw_answer)
    return text.strip()
