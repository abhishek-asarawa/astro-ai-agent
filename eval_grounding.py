"""Shared RAG faithfulness helpers for evaluation harnesses.

Used by evaluate_career.py and evaluate_rag.py: embedding grounding vs chunks
and small-LLM JSON judge over model answers vs retrieved sources.
"""

import json
import math
import re

import rag_search
from astro_engine import query_ollama_once

_REASONING_BLOCK_RE = re.compile(
    r"(?:<think>.*?</think>|<redacted_reasoning>.*?</redacted_reasoning>)",
    re.IGNORECASE | re.DOTALL,
)


def text_for_scoring(raw_response: str) -> str:
    """Drop common reasoning wrappers so embedding/judge see the final answer."""
    if not raw_response:
        return ""
    text = _REASONING_BLOCK_RE.sub("", raw_response)
    return text.strip()


def _cosine_similarity(vec_a, vec_b) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(x * y for x, y in zip(vec_a, vec_b))
    na = math.sqrt(sum(x * x for x in vec_a))
    nb = math.sqrt(sum(y * y for y in vec_b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def chunk_text(chunk) -> str:
    if chunk is None:
        return ""
    if isinstance(chunk, dict):
        return (chunk.get("text") or "").strip()
    return (getattr(chunk, "text", None) or "").strip()


def score_grounding_embedding(response: str, retrieved_chunks, max_chars: int = 7500) -> dict:
    """Max/mean cosine similarity between answer embedding and each retrieved chunk (same space as RAG)."""
    text = text_for_scoring(response)
    if not text or not retrieved_chunks:
        return {"grounding_max_sim": 0.0, "grounding_mean_sim": 0.0, "grounding_error": None}

    try:
        truncated_answer = text[:max_chars]
        answer_emb = rag_search.embed_query(truncated_answer)
        if not answer_emb:
            return {
                "grounding_max_sim": 0.0,
                "grounding_mean_sim": 0.0,
                "grounding_error": "empty_answer_embedding",
            }
        sims = []
        for chunk in retrieved_chunks:
            ct = chunk_text(chunk)[:max_chars]
            if not ct:
                continue
            emb = rag_search.embed_query(ct)
            if not emb:
                continue
            sims.append(_cosine_similarity(answer_emb, emb))
        if not sims:
            return {
                "grounding_max_sim": 0.0,
                "grounding_mean_sim": 0.0,
                "grounding_error": "no_chunk_embeddings",
            }
        return {
            "grounding_max_sim": round(max(sims), 4),
            "grounding_mean_sim": round(sum(sims) / len(sims), 4),
            "grounding_error": None,
        }
    except Exception as exc:
        return {
            "grounding_max_sim": 0.0,
            "grounding_mean_sim": 0.0,
            "grounding_error": str(exc),
        }


def parse_judge_json(text: str) -> dict:
    if not text:
        return {}
    cleaned = text.strip()
    if "```" in cleaned:
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


def run_grounding_judge(
    model_answer: str,
    retrieved_chunks,
    judge_model: str,
    timeout_s: int = 90,
    num_ctx: int = 8192,
    max_sources_chars: int = 12000,
    max_answer_chars: int = 6000,
) -> dict:
    """Small LLM scores how well the answer is supported by retrieved sources."""
    answer = text_for_scoring(model_answer)[:max_answer_chars]
    parts = []
    for ch in retrieved_chunks or []:
        ref = getattr(ch, "ref_id", None) if not isinstance(ch, dict) else ch.get("ref_id")
        body = chunk_text(ch)
        if not body:
            continue
        parts.append(f"[{ref}]: {body}")
    sources = "\n\n".join(parts)[:max_sources_chars]
    if not answer.strip() or not sources.strip():
        return {
            "judge_grounding": None,
            "judge_supported_ratio": None,
            "judge_note": "",
            "judge_raw": "",
            "judge_error": "missing_answer_or_sources",
        }

    prompt = (
        "You evaluate whether an astrologer's answer stays grounded in the given classical SOURCES.\n\n"
        "SOURCES (excerpts only):\n"
        f"{sources}\n\n"
        "MODEL ANSWER:\n"
        f"{answer}\n\n"
        "Score ONLY classical / rule claims in the answer against SOURCES. Ignore chart-specific facts.\n"
        "Reply with ONLY valid JSON on one line, no markdown:\n"
        '{"grounding": <integer 1-5>, "supported_ratio": <number 0-1>, "note": "<short string>"}\n'
        "1 = unsupported or contradicts sources; 3 = partly supported; 5 = well supported where it cites classical rules.\n"
    )
    raw = query_ollama_once(
        prompt,
        temperature=0.0,
        timeout_s=timeout_s,
        model_name=judge_model,
        num_ctx=num_ctx,
    )
    parsed = parse_judge_json(raw)
    grounding = parsed.get("grounding")
    ratio = parsed.get("supported_ratio")
    note = parsed.get("note", "")
    try:
        grounding = int(grounding) if grounding is not None else None
    except (TypeError, ValueError):
        grounding = None
    try:
        ratio = float(ratio) if ratio is not None else None
    except (TypeError, ValueError):
        ratio = None
    err = None
    if grounding is None:
        err = "judge_parse_failed"
    return {
        "judge_grounding": grounding,
        "judge_supported_ratio": ratio,
        "judge_note": note if isinstance(note, str) else str(note),
        "judge_raw": (raw or "")[:2000],
        "judge_error": err,
    }
