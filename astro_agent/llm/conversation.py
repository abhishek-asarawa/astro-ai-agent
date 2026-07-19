"""ConversationBuffer for multi-turn memory (Phase 2b).

Keeps a rolling window of the last N turns (user + assistant messages).
Total injected context is capped at TOKEN_CAP tokens. When the raw history
exceeds the cap, a one-shot llama3.2:3b summarisation call compresses it.
"""

from __future__ import annotations

from typing import Callable

from astro_agent.rag import config as cfg

MAX_TURNS: int = 3
TOKEN_CAP: int = 300
SUMMARIZE_MODEL: str = "llama3.2:3b"
ASSISTANT_SNIPPET_CHARS: int = 400


class ConversationBuffer:
    """Rolling turn buffer with token-capped prior-context injection."""

    def __init__(self, max_turns: int = MAX_TURNS, token_cap: int = TOKEN_CAP) -> None:
        self._turns: list[tuple[str, str]] = []
        self.max_turns = max_turns
        self.token_cap = token_cap

    def add(self, user_msg: str, assistant_msg: str) -> None:
        self._turns.append((user_msg, assistant_msg.strip()))
        if len(self._turns) > self.max_turns:
            self._turns = self._turns[-self.max_turns:]

    def clear(self) -> None:
        self._turns.clear()

    def is_empty(self) -> bool:
        return len(self._turns) == 0

    def _build_raw_context(self) -> str:
        lines: list[str] = []
        for user_msg, asst_msg in self._turns:
            lines.append(f"User: {user_msg}")
            snippet = asst_msg[:ASSISTANT_SNIPPET_CHARS]
            if len(asst_msg) > ASSISTANT_SNIPPET_CHARS:
                snippet += "…"
            lines.append(f"Assistant: {snippet}")
        return "\n".join(lines)

    def get_prior_context(self, summarize_fn: Callable[[str], str] | None = None) -> str:
        """Return a ``PriorContext``-ready string, or empty string if no history."""
        if not self._turns:
            return ""
        raw = self._build_raw_context()
        if cfg.estimate_tokens(raw) <= self.token_cap:
            return raw
        if summarize_fn is not None:
            try:
                summary = summarize_fn(raw)
                if summary and summary.strip():
                    return summary.strip()
            except Exception:
                pass
        return raw[: self.token_cap * 4]


def make_summarize_fn(
    model_name: str = SUMMARIZE_MODEL,
    timeout_s: int = 30,
) -> Callable[[str], str]:
    """Return a one-shot summariser backed by ``query_ollama_once``."""

    def _summarize(context_text: str) -> str:
        from astro_agent.llm.client import query_ollama_once  # lazy: avoid circular import

        from astro_agent.llm import config as llm_cfg

        prompt = (
            f"Summarise the following Vedic astrology conversation in under {llm_cfg.SUMMARY_MAX_WORDS} words, "
            "keeping key astrological insights and follow-up questions:\n\n"
            f"{context_text}"
        )
        return query_ollama_once(
            prompt,
            temperature=llm_cfg.SUMMARIZE_TEMPERATURE,
            timeout_s=timeout_s,
            model_name=model_name,
            num_ctx=llm_cfg.SUMMARIZE_NUM_CTX,
        )

    return _summarize
