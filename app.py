from __future__ import annotations

import datetime as dt
import json
import time
import uuid

import requests
import streamlit as st

from astro_agent.llm.client import (
    _call_ollama,
    build_chart_features,
    query_ollama_once,
    resolve_ollama_config,
)
from astro_agent.rag.inject import _strip_unknown_refs, build_rag_enriched_prompt
from astro_agent.llm.prompts.builder import build_prompt_for_intent
from astro_agent.agent.loop import run_agent_loop
from astro_agent.llm.conversation import ConversationBuffer, make_summarize_fn
from astro_agent.routing.intent_router import detect_intent
from astro_agent.rag import config as cfg
from astro_agent.llm.prompts.schema import domain_response_json_schema
from astro_agent.utils.response_sections import format_chat_answer_markdown, parse_structured_answer
from astro_agent.utils.text_utils import extract_ref_ids, format_consumer_text, strip_reasoning_blocks
from astro_agent.utils.cities import CITY_COORDINATES, CityResolutionError
from astro_agent.utils.tracer import trace_feedback, trace_interaction


def run_ollama_ui_query_stream(prompt, model_name=None, timeout_s=None):
    """Yield streaming text chunks and return final error code."""
    try:
        requests.get("http://localhost:11434/api/tags", timeout=(2, 3))
        response, _ = _call_ollama(
            prompt,
            stream=True,
            temperature=0.2,
            timeout_s=timeout_s,
            model_name=model_name,
        )
        response.raise_for_status()
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            try:
                chunk = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            text = chunk.get("response", "")
            if text:
                yield text, None
            if chunk.get("done"):
                break
        return
    except requests.exceptions.Timeout:
        yield "", "timeout"
    except requests.exceptions.ConnectionError:
        yield "", "connection"
    except requests.exceptions.RequestException:
        yield "", "request"


def _city_quick_picks():
    return sorted(CITY_COORDINATES.keys())


def _format_dasha(dasha):
    if not dasha:
        return "Unknown"
    return f"{dasha.get('dasha', 'Unknown')} ({dasha.get('start', '?')} to {dasha.get('end', '?')})"


def _chunk_value(chunk, key, default=None):
    if hasattr(chunk, key):
        return getattr(chunk, key)
    if isinstance(chunk, dict):
        return chunk.get(key, default)
    return default


def _chunks_to_serializable(retrieved):
    rows = []
    for idx, chunk in enumerate(retrieved or [], start=1):
        ref_id = _chunk_value(chunk, "ref_id", f"ref_{idx}")
        similarity = _chunk_value(chunk, "similarity", None)
        matched_entities = _chunk_value(chunk, "matched_entities", []) or []
        chunk_text = (_chunk_value(chunk, "text", "") or "").strip()
        rows.append(
            {
                "ref_id": ref_id,
                "similarity": float(similarity) if similarity is not None else None,
                "matched_entities": list(matched_entities),
                "text": chunk_text,
            }
        )
    return rows


def _display_body_for_message(msg: dict) -> str:
    if msg.get("displayed_answer"):
        return msg["displayed_answer"]
    parsed = parse_structured_answer(msg.get("content") or "")
    return format_chat_answer_markdown(parsed, msg.get("content") or "")


def _render_assistant_in_chat(msg: dict, *, show_feedback: bool):
    body = _display_body_for_message(msg)
    if body.strip():
        st.markdown(body)
    else:
        st.info("_No answer text._")

    interaction_id = msg.get("interaction_id")
    if show_feedback and interaction_id:
        _render_answer_feedback(interaction_id)


def _render_answer_feedback(interaction_id: str):
    submitted_key = f"feedback_submitted_{interaction_id}"
    if st.session_state.get(submitted_key):
        st.caption("Thanks for your feedback.")
        return

    st.caption("Was this helpful?")
    col_up, col_down, _ = st.columns([1, 1, 4])
    with col_up:
        if st.button("Helpful", key=f"fb_up_{interaction_id}", use_container_width=True):
            trace_feedback(
                interaction_id=interaction_id,
                session_id=st.session_state.session_id,
                helpful=True,
            )
            st.session_state[submitted_key] = True
            st.rerun()
    with col_down:
        if st.button("Not helpful", key=f"fb_down_{interaction_id}", use_container_width=True):
            trace_feedback(
                interaction_id=interaction_id,
                session_id=st.session_state.session_id,
                helpful=False,
            )
            st.session_state[submitted_key] = True
            st.rerun()

    note_key = f"fb_note_{interaction_id}"
    note = st.text_input(
        "Optional note (press Enter after typing, then click again if needed)",
        key=note_key,
        placeholder="What was unclear or missing?",
        label_visibility="collapsed",
    )
    if note.strip() and st.button("Send note", key=f"fb_note_btn_{interaction_id}"):
        trace_feedback(
            interaction_id=interaction_id,
            session_id=st.session_state.session_id,
            helpful=False,
            note=note.strip(),
        )
        st.session_state[submitted_key] = True
        st.rerun()


def _render_sources_compact(rows: list[dict]):
    if not rows:
        return
    with st.expander("Sources used", expanded=False):
        st.caption("Short excerpts from classical texts that informed this answer.")
        for idx, row in enumerate(rows, start=1):
            ref_id = row.get("ref_id", f"ref_{idx}")
            chunk_text = (row.get("text") or "").strip()
            st.markdown(f"**{idx}. {ref_id}**")
            st.write(chunk_text[:500] + ("…" if len(chunk_text) > 500 else "") if chunk_text else "_No text._")


def _render_technical_practitioner_view(features: dict):
    """All debug/chart panels — only when sidebar toggle is on."""
    st.divider()
    with st.expander("Practitioner / debug view", expanded=False):
        st.subheader("Run summary")
        r1c1, r1c2, r1c3 = st.columns(3)
        r1c1.metric("Model", st.session_state.get("last_model", "—"))
        r1c2.metric(
            "Active Mahadasha",
            features["active_dasha"]["dasha"] if features.get("active_dasha") else "Unknown",
        )
        r1c3.metric(
            "Active Antardasha",
            features["active_antardasha"]["dasha"]
            if features.get("active_antardasha")
            else "Unknown",
        )
        r2c1, r2c2, r2c3 = st.columns(3)
        r2c1.metric(
            "Next Mahadasha",
            features["next_dasha"]["dasha"] if features.get("next_dasha") else "Unknown",
        )
        r2c2.metric(
            "Next Antardasha",
            features["next_antardasha"]["dasha"]
            if features.get("next_antardasha")
            else "Unknown",
        )
        r2c3.metric("Detected intent", st.session_state.get("last_intent", "general"))

        st.markdown("**Input summary**")
        st.json(
            {
                "birth_date_ist": st.session_state.saved_birth["birth_date"].isoformat(),
                "birth_time_ist": st.session_state.saved_birth["birth_time"].strftime("%H:%M"),
                "city_name": st.session_state.saved_birth["city_name"],
                "last_question": st.session_state.last_question,
                "rag_enabled": bool(st.session_state.agent_rag_enabled),
                "agent_loop": bool(st.session_state.agent_loop_enabled),
            }
        )

        rows = st.session_state.last_retrieved_rows or []
        if rows:
            st.markdown("**Sources (full)**")
            for idx, row in enumerate(rows, start=1):
                ref_id = row.get("ref_id", f"ref_{idx}")
                similarity = row.get("similarity")
                matched_entities = row.get("matched_entities") or []
                chunk_text = (row.get("text") or "").strip()
                header = f"{idx}. {ref_id}"
                if similarity is not None:
                    header += f" (sim={similarity:.3f})"
                with st.expander(header, expanded=False):
                    if matched_entities:
                        st.caption("Matched entities: " + ", ".join(str(e) for e in matched_entities))
                    st.write(chunk_text or "_No chunk text._")

        st.markdown("**Dasha snapshot**")
        st.write(f"Active Mahadasha: {_format_dasha(features.get('active_dasha'))}")
        st.write(f"Active Antardasha: {_format_dasha(features.get('active_antardasha'))}")
        st.write(f"Next Mahadasha: {_format_dasha(features.get('next_dasha'))}")
        st.write(f"Next Antardasha: {_format_dasha(features.get('next_antardasha'))}")

        st.markdown("**Planetary placements**")
        st.json(features.get("planets", {}))

        st.markdown("**House lordships and dignities**")
        st.json(
            {
                "house_lordships": features.get("house_lordships", {}),
                "planetary_dignities": features.get("planetary_dignities", {}),
            }
        )

        if st.session_state.last_prompt_preview:
            st.markdown("**Prompt preview (last linear run)**")
            prev = st.session_state.last_prompt_preview
            st.code(prev[:3000], language="text")
            if len(prev) > 3000:
                st.caption("Truncated for readability.")

        if st.session_state.chat_history:
            last_asst = next(
                (m for m in reversed(st.session_state.chat_history) if m.get("role") == "assistant"),
                None,
            )
            if last_asst and last_asst.get("content"):
                st.markdown("**Raw model output (last answer)**")
                st.code(last_asst["content"], language="markdown")


def _init_session_defaults():
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "session_id" not in st.session_state:
        st.session_state.session_id = uuid.uuid4().hex
    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False
    if "pending_request" not in st.session_state:
        st.session_state.pending_request = None
    if "conversation_buffer" not in st.session_state:
        st.session_state.conversation_buffer = ConversationBuffer()
    if "saved_birth" not in st.session_state:
        st.session_state.saved_birth = {
            "birth_date": dt.date(1998, 9, 27),
            "birth_time": dt.time(13, 0),
            "city_name": "delhi",
        }
    if "last_features" not in st.session_state:
        st.session_state.last_features = None
    if "last_retrieved_rows" not in st.session_state:
        st.session_state.last_retrieved_rows = []
    if "last_prompt_preview" not in st.session_state:
        st.session_state.last_prompt_preview = ""
    if "last_question" not in st.session_state:
        st.session_state.last_question = ""
    if "last_model" not in st.session_state:
        st.session_state.last_model = ""
    if "last_intent" not in st.session_state:
        st.session_state.last_intent = "general"
    if "agent_rag_enabled" not in st.session_state:
        st.session_state.agent_rag_enabled = True
    if "agent_loop_enabled" not in st.session_state:
        st.session_state.agent_loop_enabled = False
    if "agent_model_override" not in st.session_state:
        st.session_state.agent_model_override = ""
    if "agent_timeout_s" not in st.session_state:
        st.session_state.agent_timeout_s = 120
    if "show_technical_details" not in st.session_state:
        st.session_state.show_technical_details = False


def _render_sidebar():
    st.sidebar.header("Agent settings")
    st.sidebar.checkbox(
        "Enable RAG retrieval",
        key="agent_rag_enabled",
        help="Classical references and citation rules in the prompt.",
    )
    st.sidebar.checkbox(
        "Enable agent loop (ReAct tools)",
        key="agent_loop_enabled",
        help="Uses /api/chat with tools; non-streaming. Falls back to linear path if needed.",
    )
    st.sidebar.text_input(
        "Model override (optional)",
        key="agent_model_override",
        placeholder="e.g. qwen2.5:7b-instruct",
        help="Leave blank to use env / engine default.",
    )
    st.sidebar.number_input(
        "Timeout (seconds)",
        min_value=15,
        max_value=1800,
        step=15,
        key="agent_timeout_s",
    )
    st.sidebar.divider()
    st.sidebar.caption("Display")
    st.sidebar.checkbox(
        "Show technical details",
        key="show_technical_details",
        help="Chart data, sources, prompt preview, and raw model output.",
    )
    st.sidebar.divider()
    st.sidebar.caption(
        "Interaction logging is opt-in: set `ASTRO_TRACE_ENABLED=1` to record Q&A in "
        "`interactions.jsonl` for evaluation."
    )
    st.sidebar.divider()
    if st.sidebar.button("Reset conversation", help="Clears chat, memory buffer, and last chart snapshot in the UI."):
        st.session_state.chat_history = []
        st.session_state.conversation_buffer = ConversationBuffer()
        st.session_state.last_features = None
        st.session_state.last_retrieved_rows = []
        st.session_state.last_prompt_preview = ""
        st.session_state.last_question = ""
        st.session_state.session_id = uuid.uuid4().hex
        st.rerun()


def main():
    st.set_page_config(page_title="Astro AI Agent", page_icon="🔭", layout="wide")
    _init_session_defaults()
    _render_sidebar()

    st.title("Astro AI Agent")
    st.caption("Ask about your chart in plain language — powered by your local Ollama model.")

    sb = st.session_state.saved_birth
    quick_picks = _city_quick_picks()

    birth_expanded = not bool(st.session_state.chat_history)
    with st.expander("Birth details (IST)", expanded=birth_expanded):
        col1, col2 = st.columns(2)
        with col1:
            st.date_input(
                "Birth date",
                value=sb["birth_date"],
                disabled=st.session_state.is_processing,
                key="birth_date_input",
            )
        with col2:
            st.time_input(
                "Birth time",
                value=sb["birth_time"],
                disabled=st.session_state.is_processing,
                key="birth_time_input",
            )
        st.text_input(
            "Birth city",
            value=sb["city_name"],
            placeholder="e.g. Delhi, India or pune",
            disabled=st.session_state.is_processing,
            key="birth_city_input",
            help=f"Quick picks: {', '.join(quick_picks)}",
        )

    if st.session_state.pending_request:
        request_data = st.session_state.pending_request
        birth_date = dt.date.fromisoformat(request_data["birth_date"])
        birth_time = dt.time.fromisoformat(request_data["birth_time"])
        city_name = request_data["city_name"]
        cleaned_question = request_data["question"]
        rag_enabled = bool(request_data.get("rag_enabled", True))
        agent_loop_enabled = bool(request_data.get("agent_loop_enabled", False))
        model_input = request_data["model_input"]
        timeout_input = request_data["timeout_input"]
        request_started = time.perf_counter()

        model_override = model_input.strip() or None
        resolved_model, resolved_timeout, resolved_num_ctx = resolve_ollama_config(
            model_name=model_override,
            timeout_s=int(timeout_input),
        )

        intent_info = {
            "intent": "general",
            "method": "rules_fallback",
            "confidence": 0.0,
            "rule_scores": {},
        }
        prompt = ""
        rag_bundle = None
        agent_result = None
        features = None
        final_answer = ""
        error_code = None

        try:
            _summarize_fn = make_summarize_fn(timeout_s=min(30, resolved_timeout))
            prior_context = st.session_state.conversation_buffer.get_prior_context(
                summarize_fn=_summarize_fn
            )

            with st.spinner("Computing chart and querying model..."):
                try:
                    features = build_chart_features(
                        birth_date.year,
                        birth_date.month,
                        birth_date.day,
                        birth_time.hour,
                        birth_time.minute,
                        city_name,
                    )
                except CityResolutionError as exc:
                    st.error(str(exc))
                else:
                    try:
                        intent_info = detect_intent(
                            question=cleaned_question,
                            timeout_s=min(45, resolved_timeout),
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

                    if agent_loop_enabled:
                        agent_result = run_agent_loop(
                            user_question=cleaned_question,
                            features=features,
                            intent=chosen_intent,
                            model_name=resolved_model,
                            timeout_s=resolved_timeout,
                            num_ctx=resolved_num_ctx,
                            rag_enabled=rag_enabled,
                            prior_context=prior_context or None,
                        )
                    elif rag_enabled:
                        rag_bundle = build_rag_enriched_prompt(
                            features,
                            cleaned_question,
                            chosen_intent,
                            prior_context=prior_context or None,
                        )
                        prompt = rag_bundle["prompt"]
                    else:
                        prompt = build_prompt_for_intent(
                            features,
                            cleaned_question,
                            chosen_intent,
                            prior_context=prior_context or None,
                        )

            if features is not None:
                stream_ph = st.empty()
                if agent_loop_enabled and agent_result is not None:
                    final_answer = agent_result.get("answer", "") or ""
                elif cfg.STRUCTURED_OUTPUT_ENABLED:
                    with st.spinner("Generating structured response..."):
                        raw = query_ollama_once(
                            prompt,
                            temperature=0.2,
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
                    stream_ph.empty()
                else:
                    with st.spinner("Generating response..."):
                        for text_chunk, possible_error in run_ollama_ui_query_stream(
                            prompt,
                            model_name=resolved_model,
                            timeout_s=resolved_timeout,
                        ):
                            if possible_error:
                                error_code = possible_error
                                break
                            final_answer += text_chunk
                            parsed_preview = parse_structured_answer(
                                strip_reasoning_blocks(final_answer)
                            )
                            preview_md = format_chat_answer_markdown(
                                parsed_preview, strip_reasoning_blocks(final_answer)
                            )
                            stream_ph.markdown(preview_md + "▌")
                    final_answer = strip_reasoning_blocks(final_answer)
                    stream_ph.empty()

                if error_code == "connection":
                    st.error("Could not connect to Ollama at `http://localhost:11434`. Start Ollama and retry.")
                elif error_code == "timeout":
                    st.error(
                        f"The request timed out after {resolved_timeout}s. "
                        "Try increasing timeout in Agent settings or using a smaller model."
                    )
                elif error_code:
                    st.error("Model call failed unexpectedly. Please retry.")
                elif not final_answer.strip():
                    st.warning(
                        "No response text was returned by Ollama. Try a smaller model, higher timeout, or restart Ollama."
                    )
                else:
                    if (
                        not agent_loop_enabled
                        and not cfg.STRUCTURED_OUTPUT_ENABLED
                        and rag_enabled
                        and rag_bundle
                        and rag_bundle.get("allowed_refs")
                    ):
                        final_answer, _ = _strip_unknown_refs(
                            final_answer, rag_bundle.get("allowed_refs")
                        )

                    parsed = parse_structured_answer(final_answer)
                    displayed_answer = format_chat_answer_markdown(parsed, final_answer)
                    interaction_id = uuid.uuid4().hex
                    latency_ms = (time.perf_counter() - request_started) * 1000.0

                    st.session_state.chat_history.append(
                        {
                            "role": "assistant",
                            "content": final_answer,
                            "interaction_id": interaction_id,
                            "displayed_answer": displayed_answer,
                        }
                    )
                    st.session_state.conversation_buffer.add(cleaned_question, final_answer)
                    st.session_state.saved_birth = {
                        "birth_date": birth_date,
                        "birth_time": birth_time,
                        "city_name": city_name,
                    }
                    st.session_state.last_features = features
                    st.session_state.last_question = cleaned_question
                    st.session_state.last_prompt_preview = prompt or ""
                    st.session_state.last_retrieved_rows = _chunks_to_serializable(
                        (rag_bundle or {}).get("retrieved", [])
                    )
                    st.session_state.last_model = resolved_model
                    st.session_state.last_intent = intent_info.get("intent", "general")

                    ref_ids = extract_ref_ids(final_answer)
                    trace_interaction(
                        interaction_id=interaction_id,
                        session_id=st.session_state.session_id,
                        question=cleaned_question,
                        raw_answer=final_answer,
                        displayed_answer=displayed_answer,
                        intent=intent_info.get("intent"),
                        model=resolved_model,
                        latency_ms=latency_ms,
                        rag_enabled=rag_enabled,
                        agent_loop=agent_loop_enabled,
                        ref_ids=ref_ids,
                        confidence_int=parsed.get("confidence_int"),
                        parsed_ok=bool(parsed.get("parsed_ok")),
                        birth_date_iso=birth_date.isoformat(),
                        birth_time_iso=birth_time.strftime("%H:%M"),
                        city_name=city_name,
                        intent_method=intent_info.get("method"),
                    )

        finally:
            st.session_state.is_processing = False
            st.session_state.pending_request = None

    if not st.session_state.chat_history:
        st.info("Ask a question below. Your birth details stay until you change them.")
    else:
        n = len(st.session_state.chat_history)
        last_assistant_idx = None
        for i, msg in enumerate(st.session_state.chat_history):
            if msg.get("role") == "assistant":
                last_assistant_idx = i

        for i, msg in enumerate(st.session_state.chat_history):
            with st.chat_message(msg["role"]):
                if msg["role"] == "user":
                    st.markdown(msg["content"])
                else:
                    show_feedback = i == last_assistant_idx
                    _render_assistant_in_chat(msg, show_feedback=show_feedback)

        if (
            last_assistant_idx is not None
            and st.session_state.agent_rag_enabled
            and st.session_state.last_retrieved_rows
            and not st.session_state.get("show_technical_details")
        ):
            _render_sources_compact(st.session_state.last_retrieved_rows)

        if not st.session_state.get("show_technical_details") and st.session_state.chat_history:
            last_asst = st.session_state.chat_history[last_assistant_idx] if last_assistant_idx is not None else None
            raw = (last_asst or {}).get("content") or ""
            if raw and extract_ref_ids(raw):
                with st.expander("Why this answer", expanded=False):
                    st.write(
                        "This reading used classical Vedic references behind the scenes. "
                        "Citation codes are hidden in the chat view for readability."
                    )

    features = st.session_state.last_features
    if features and st.session_state.get("show_technical_details"):
        _render_technical_practitioner_view(features)

    user_prompt = st.chat_input("Ask a follow-up question about your chart")
    if user_prompt and not st.session_state.is_processing:
        cleaned_question = user_prompt.strip()
        if not cleaned_question:
            st.error("Please enter a question before sending.")
        else:
            birth_date_in = st.session_state.get("birth_date_input", sb["birth_date"])
            birth_time_in = st.session_state.get("birth_time_input", sb["birth_time"])
            city_name_in = st.session_state.get("birth_city_input", sb["city_name"])
            st.session_state.chat_history.append({"role": "user", "content": cleaned_question})
            st.session_state.pending_request = {
                "birth_date": birth_date_in.isoformat(),
                "birth_time": birth_time_in.strftime("%H:%M"),
                "city_name": city_name_in,
                "question": cleaned_question,
                "rag_enabled": bool(st.session_state.agent_rag_enabled),
                "agent_loop_enabled": bool(st.session_state.agent_loop_enabled),
                "model_input": (st.session_state.agent_model_override or "").strip(),
                "timeout_input": int(st.session_state.agent_timeout_s),
            }
            st.session_state.is_processing = True
            st.rerun()


if __name__ == "__main__":
    main()
