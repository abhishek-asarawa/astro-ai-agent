"""Consultation service: chart → intent → agent/RAG/linear → structured answer.

Streamlit (and future HTTP APIs) should call ``run_consultation`` rather than
re-implementing orchestration in the UI layer.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from astro_agent.agent.loop import run_agent_loop
from astro_agent.chart.engine import build_chart_features
from astro_agent.llm import config as llm_cfg
from astro_agent.llm.client import query_ollama_once, resolve_ollama_config
from astro_agent.llm.conversation import ConversationBuffer, make_summarize_fn
from astro_agent.llm.humanizer import humanize_answer
from astro_agent.llm.prompts.builder import build_prompt_for_intent
from astro_agent.llm.prompts.schema import domain_response_json_schema
from astro_agent.rag import config as cfg
from astro_agent.rag.inject import _strip_unknown_refs, build_rag_enriched_prompt
from astro_agent.routing.intent_router import detect_intent
from astro_agent.utils.cities import CityResolutionError
from astro_agent.utils.confidence import calibrate_confidence
from astro_agent.utils.response_sections import parse_structured_answer
from astro_agent.utils.text_utils import extract_ref_ids, strip_reasoning_blocks
from astro_agent.utils.tracer import trace_interaction


@dataclass
class ConsultationRequest:
    year: int
    month: int
    day: int
    hour: int
    minute: int
    city_name: str
    question: str
    rag_enabled: bool = True
    agent_loop_enabled: bool = False
    model_name: str | None = None
    timeout_s: int | None = None
    num_ctx: int | None = None
    session_id: str | None = None
    prior_context: str | None = None
    conversation_buffer: ConversationBuffer | None = None
    birth_date_iso: str | None = None
    birth_time_iso: str | None = None


@dataclass
class ConsultationResult:
    ok: bool
    error: str | None = None
    error_code: str | None = None
    features: dict | None = None
    intent_info: dict = field(default_factory=dict)
    prompt: str = ""
    raw_answer: str = ""
    displayed_answer: str = ""
    method: str = "linear"
    rag_bundle: dict | None = None
    retrieved_rows: list = field(default_factory=list)
    interaction_id: str | None = None
    calibrated_confidence: int | None = None
    ref_ids: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    model: str | None = None


def _chunks_to_serializable(retrieved) -> list[dict]:
    rows = []
    for idx, chunk in enumerate(retrieved or [], start=1):
        if hasattr(chunk, "ref_id"):
            ref_id = getattr(chunk, "ref_id", f"ref_{idx}")
            similarity = getattr(chunk, "similarity", None)
            matched_entities = getattr(chunk, "matched_entities", []) or []
            chunk_text = (getattr(chunk, "text", "") or "").strip()
        elif isinstance(chunk, dict):
            ref_id = chunk.get("ref_id", f"ref_{idx}")
            similarity = chunk.get("similarity")
            matched_entities = chunk.get("matched_entities", []) or []
            chunk_text = (chunk.get("text", "") or "").strip()
        else:
            continue
        rows.append(
            {
                "ref_id": ref_id,
                "similarity": float(similarity) if similarity is not None else None,
                "matched_entities": list(matched_entities),
                "text": chunk_text,
            }
        )
    return rows


def run_consultation(
    request: ConsultationRequest,
    *,
    stream_generate: Callable[[str, str | None, int | None], Iterator[tuple[str, str | None]]] | None = None,
) -> ConsultationResult:
    """Run one consultation end-to-end.

    If ``stream_generate`` is provided and structured output / agent loop are off,
    it is used to stream the linear generate path. The callable must yield
    ``(text_chunk, error_code_or_None)``.
    """
    started = time.perf_counter()
    resolved_model, resolved_timeout, resolved_num_ctx = resolve_ollama_config(
        model_name=request.model_name,
        timeout_s=request.timeout_s,
        num_ctx=request.num_ctx,
    )

    prior_context = request.prior_context
    if prior_context is None and request.conversation_buffer is not None:
        summarize_fn = make_summarize_fn(timeout_s=min(30, resolved_timeout))
        prior_context = request.conversation_buffer.get_prior_context(summarize_fn=summarize_fn) or None

    try:
        features = build_chart_features(
            request.year,
            request.month,
            request.day,
            request.hour,
            request.minute,
            request.city_name,
        )
    except CityResolutionError as exc:
        return ConsultationResult(ok=False, error=str(exc), error_code="city", model=resolved_model)

    try:
        intent_info = detect_intent(
            question=request.question,
            timeout_s=min(llm_cfg.INTENT_CLASSIFIER_TIMEOUT_S, resolved_timeout),
        )
    except Exception as exc:
        print(f"[intent] detection failed ({exc}), falling back to general", flush=True)
        intent_info = {
            "intent": "general",
            "method": "rules_fallback",
            "confidence": 0.0,
            "rule_scores": {},
        }

    chosen_intent = intent_info.get("intent", "general")
    rag_bundle = None
    prompt = ""
    final_answer = ""
    error_code = None
    method = "linear"
    agent_result = None

    if request.agent_loop_enabled:
        agent_result = run_agent_loop(
            user_question=request.question,
            features=features,
            intent=chosen_intent,
            model_name=resolved_model,
            timeout_s=resolved_timeout,
            num_ctx=resolved_num_ctx,
            rag_enabled=request.rag_enabled,
            prior_context=prior_context,
        )
        final_answer = agent_result.get("answer", "") or ""
        method = agent_result.get("method") or "agent"
    elif request.rag_enabled:
        rag_bundle = build_rag_enriched_prompt(
            features,
            request.question,
            chosen_intent,
            prior_context=prior_context,
        )
        prompt = rag_bundle["prompt"]
    else:
        prompt = build_prompt_for_intent(
            features,
            request.question,
            chosen_intent,
            prior_context=prior_context,
        )

    if not request.agent_loop_enabled:
        if cfg.STRUCTURED_OUTPUT_ENABLED:
            raw = query_ollama_once(
                prompt,
                temperature=llm_cfg.DEFAULT_TEMPERATURE,
                timeout_s=resolved_timeout,
                model_name=resolved_model,
                allowed_refs=rag_bundle.get("allowed_refs") if rag_bundle else None,
                num_ctx=resolved_num_ctx,
                response_format=domain_response_json_schema(),
            )
            if not raw:
                error_code = "request"
            else:
                final_answer = strip_reasoning_blocks(raw)
        elif stream_generate is not None:
            for text_chunk, possible_error in stream_generate(prompt, resolved_model, resolved_timeout):
                if possible_error:
                    error_code = possible_error
                    break
                final_answer += text_chunk
            final_answer = strip_reasoning_blocks(final_answer)
        else:
            raw = query_ollama_once(
                prompt,
                temperature=llm_cfg.DEFAULT_TEMPERATURE,
                timeout_s=resolved_timeout,
                model_name=resolved_model,
                allowed_refs=rag_bundle.get("allowed_refs") if rag_bundle else None,
                num_ctx=resolved_num_ctx,
            )
            if not raw:
                error_code = "request"
            else:
                final_answer = strip_reasoning_blocks(raw)

        if (
            not error_code
            and request.rag_enabled
            and rag_bundle
            and rag_bundle.get("allowed_refs")
            and not cfg.STRUCTURED_OUTPUT_ENABLED
        ):
            final_answer, _ = _strip_unknown_refs(final_answer, rag_bundle.get("allowed_refs"))

    if error_code:
        return ConsultationResult(
            ok=False,
            error_code=error_code,
            error={
                "connection": "Could not connect to Ollama.",
                "timeout": f"Timed out after {resolved_timeout}s.",
                "request": "Model call failed unexpectedly.",
            }.get(error_code, "Request failed."),
            features=features,
            intent_info=intent_info,
            prompt=prompt,
            model=resolved_model,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )

    if not final_answer.strip():
        return ConsultationResult(
            ok=False,
            error_code="empty",
            error="No response text was returned by Ollama.",
            features=features,
            intent_info=intent_info,
            prompt=prompt,
            model=resolved_model,
            latency_ms=(time.perf_counter() - started) * 1000.0,
        )

    parsed = parse_structured_answer(final_answer)
    ref_ids = extract_ref_ids(final_answer)
    calibrated_confidence = calibrate_confidence(
        parsed.get("confidence_int"),
        parsed.get("evidence"),
        ref_ids,
    )
    displayed_answer = humanize_answer(
        final_answer,
        request.question,
        model_name=resolved_model,
        num_ctx=resolved_num_ctx,
        parsed=parsed,
    )
    interaction_id = uuid.uuid4().hex
    latency_ms = (time.perf_counter() - started) * 1000.0
    retrieved_rows = _chunks_to_serializable((rag_bundle or {}).get("retrieved", []))

    if request.session_id:
        trace_interaction(
            interaction_id=interaction_id,
            session_id=request.session_id,
            question=request.question,
            raw_answer=final_answer,
            displayed_answer=displayed_answer,
            intent=intent_info.get("intent"),
            model=resolved_model,
            latency_ms=latency_ms,
            rag_enabled=request.rag_enabled,
            agent_loop=request.agent_loop_enabled,
            ref_ids=ref_ids,
            confidence_int=calibrated_confidence,
            parsed_ok=bool(parsed.get("parsed_ok")),
            birth_date_iso=request.birth_date_iso,
            birth_time_iso=request.birth_time_iso,
            city_name=request.city_name,
            intent_method=intent_info.get("method"),
        )

    if request.conversation_buffer is not None:
        request.conversation_buffer.add(request.question, final_answer)

    return ConsultationResult(
        ok=True,
        features=features,
        intent_info=intent_info,
        prompt=prompt,
        raw_answer=final_answer,
        displayed_answer=displayed_answer,
        method=method,
        rag_bundle=rag_bundle,
        retrieved_rows=retrieved_rows,
        interaction_id=interaction_id,
        calibrated_confidence=calibrated_confidence,
        ref_ids=ref_ids,
        latency_ms=latency_ms,
        model=resolved_model,
    )
