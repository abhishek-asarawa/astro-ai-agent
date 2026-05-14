from __future__ import annotations

import datetime as dt
import json
import requests
import streamlit as st

from astro_engine import (
    _call_ollama,
    _strip_unknown_refs,
    build_rag_enriched_prompt,
    build_prompt_for_intent,
    build_chart_features,
    resolve_ollama_config,
)
from agent_loop import run_agent_loop
from conversation import ConversationBuffer, make_summarize_fn
from intent_router import detect_intent
from response_sections import parse_structured_answer
from text_utils import extract_ref_ids, format_consumer_text, strip_reasoning_blocks
from utils import CITY_COORDINATES


def run_ollama_ui_query_stream(prompt, model_name=None, timeout_s=None):
    """Yield streaming text chunks and return final error code."""
    try:
        requests.get("http://localhost:11434/api/tags", timeout=(2, 3))
        response = _call_ollama(
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


def _city_options():
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


def _render_assistant_in_chat(content: str, *, is_latest: bool):
    if is_latest:
        parsed = parse_structured_answer(content)
        body = ""
        if parsed.get("parsed_ok") and parsed.get("summary"):
            body = format_consumer_text(parsed["summary"])
        if not body:
            body = format_consumer_text(content or "")[:600]
        if body.strip():
            short = body.strip()
            if len(short) > 380:
                short = short[:380].rstrip() + "…"
            st.markdown(short)
            st.caption("Use **Your reading** below for the full breakdown (key points, cautions, and confidence).")
        else:
            st.info("Your reading is ready below — overview, key points, and practical notes.")
    else:
        preview = format_consumer_text(content or "").strip()
        if len(preview) > 200:
            preview = preview[:200].rstrip() + "…"
        with st.expander("Earlier answer (short excerpt)", expanded=False):
            st.markdown(preview or "_Empty_")


def _render_structured_reading(parsed: dict, raw_fallback: str, *, last_question: str | None):
    show_technical = bool(st.session_state.get("show_technical_details"))
    st.subheader("Your reading")
    st.caption(
        "Plain-language breakdown. Technical codes and citation ids stay hidden unless you turn on "
        "**Show technical details** in the sidebar."
    )
    if last_question:
        st.markdown(f"**You asked:** {last_question}")

    if parsed.get("parsed_ok"):
        t_overview, t_points, t_balance, t_conf = st.tabs(
            ("Overview", "Key points", "Cautions & upside", "Confidence"),
        )
        with t_overview:
            st.markdown(format_consumer_text(parsed.get("summary")) or "_We could not isolate an overview._")
        with t_points:
            st.markdown(format_consumer_text(parsed.get("evidence")) or "_No supporting points were extracted._")
        with t_balance:
            st.markdown("**What to watch**")
            st.markdown(format_consumer_text(parsed.get("risk")) or "—")
            st.markdown("**What helps**")
            st.markdown(format_consumer_text(parsed.get("opportunity")) or "—")
        with t_conf:
            st.markdown(
                "This score reflects how decisive the model sounded given your chart data—not a promise "
                "about real-world outcomes."
            )
            ci = parsed.get("confidence_int")
            if ci is not None and 0 <= ci <= 100:
                st.progress(ci / 100.0)
                st.markdown(f"**{ci}** out of 100")
            elif parsed.get("confidence"):
                st.markdown(f"**{format_consumer_text(str(parsed['confidence']))}**")
            else:
                st.info("No confidence line was found in this answer.")
    else:
        st.warning("We could not split this answer into sections automatically. Here is the cleaned text:")
        st.markdown(format_consumer_text(raw_fallback) or "")

    if not show_technical and extract_ref_ids(raw_fallback or ""):
        with st.expander("How this answer was grounded", expanded=False):
            st.write(
                "When retrieval (RAG) is on, the model is steered by short excerpts from classical Vedic "
                "texts. In the default view we remove internal citation codes so the reading reads naturally."
            )

    if show_technical:
        with st.expander("Technical / raw model output", expanded=False):
            st.code(raw_fallback or "", language="markdown")


def _init_session_defaults():
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
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
        help="Shows raw model formatting and [ref:…] citation ids. Leave off for a client-friendly view.",
    )
    st.sidebar.divider()
    if st.sidebar.button("Reset conversation", help="Clears chat, memory buffer, and last chart snapshot in the UI."):
        st.session_state.chat_history = []
        st.session_state.conversation_buffer = ConversationBuffer()
        st.session_state.last_features = None
        st.session_state.last_retrieved_rows = []
        st.session_state.last_prompt_preview = ""
        st.session_state.last_question = ""
        st.rerun()


def main():
    st.set_page_config(page_title="Astro AI Agent", page_icon="🔭", layout="wide")
    _init_session_defaults()
    _render_sidebar()

    st.title("Astro AI Agent")
    st.caption("Interactive Vedic astrology analysis powered by your local Ollama model.")

    sb = st.session_state.saved_birth
    cities = _city_options()
    city_index = cities.index(sb["city_name"]) if sb["city_name"] in cities else 0

    birth_expanded = not bool(st.session_state.chat_history)
    with st.expander("Birth details (IST)", expanded=birth_expanded):
        col1, col2, col3 = st.columns(3)
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
        with col3:
            st.selectbox(
                "Birth city",
                options=cities,
                index=city_index,
                disabled=st.session_state.is_processing,
                key="birth_city_input",
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

        if city_name.lower() not in CITY_COORDINATES:
            st.warning("Selected city was not recognized. Falling back to bengaluru.")
            city_name = "bengaluru"

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
                features = build_chart_features(
                    birth_date.year,
                    birth_date.month,
                    birth_date.day,
                    birth_time.hour,
                    birth_time.minute,
                    city_name,
                )
                try:
                    intent_info = detect_intent(
                        question=cleaned_question,
                        timeout_s=min(45, resolved_timeout),
                    )
                except Exception:
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
                else:
                    if rag_enabled:
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

            stream_ph = st.empty()
            if agent_loop_enabled and agent_result is not None:
                final_answer = agent_result.get("answer", "") or ""
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
                        stream_ph.markdown(strip_reasoning_blocks(final_answer) + "▌")
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
                if not agent_loop_enabled and rag_enabled and rag_bundle and rag_bundle.get("allowed_refs"):
                    final_answer, _ = _strip_unknown_refs(final_answer, rag_bundle.get("allowed_refs"))

                st.session_state.chat_history.append({"role": "assistant", "content": final_answer})
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
                st.success("Analysis generated successfully.")

                st.divider()
                st.subheader("Run summary")
                r1c1, r1c2, r1c3 = st.columns(3)
                r1c1.metric("Model", resolved_model)
                r1c2.metric(
                    "Active Mahadasha",
                    features["active_dasha"]["dasha"] if features["active_dasha"] else "Unknown",
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
                    features["next_dasha"]["dasha"] if features["next_dasha"] else "Unknown",
                )
                r2c2.metric(
                    "Next Antardasha",
                    features["next_antardasha"]["dasha"]
                    if features.get("next_antardasha")
                    else "Unknown",
                )
                r2c3.metric("Detected intent", intent_info.get("intent", "general"))

                rag_caption = f"RAG: {'ON' if rag_enabled else 'OFF'}"
                if rag_enabled and rag_bundle:
                    rag_caption += f" | Retrieved refs: {len(rag_bundle.get('allowed_refs', []))}"
                if agent_loop_enabled and agent_result:
                    method = agent_result.get("method", "?")
                    tools_used = agent_result.get("tool_calls_made", [])
                    rag_caption += (
                        f" | Agent: {method}"
                        + (f" | Tools: {', '.join(tools_used)}" if tools_used else "")
                    )
                st.caption(rag_caption)

        finally:
            st.session_state.is_processing = False
            st.session_state.pending_request = None

    st.divider()
    st.subheader("Conversation")
    if not st.session_state.chat_history:
        st.info("Ask a question using the chat box at the bottom. Birth details stay until you change them.")
    else:
        n = len(st.session_state.chat_history)
        for i, msg in enumerate(st.session_state.chat_history):
            with st.chat_message(msg["role"]):
                if msg["role"] == "user":
                    st.markdown(msg["content"])
                else:
                    is_latest = i == n - 1
                    _render_assistant_in_chat(msg["content"], is_latest=is_latest)

        if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "assistant":
            parsed = parse_structured_answer(st.session_state.chat_history[-1]["content"])
            _render_structured_reading(
                parsed,
                st.session_state.chat_history[-1]["content"],
                last_question=st.session_state.last_question or None,
            )

    features = st.session_state.last_features
    if features:
        st.divider()
        with st.expander("Input summary", expanded=False):
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
        if st.session_state.agent_rag_enabled:
            with st.expander("Sources", expanded=False):
                if not rows:
                    st.info("No RAG sources for the last linear run (agent-only or RAG off for that run).")
                else:
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

        with st.expander("Dasha snapshot", expanded=False):
            st.write(f"Active Mahadasha: {_format_dasha(features.get('active_dasha'))}")
            st.write(f"Active Antardasha: {_format_dasha(features.get('active_antardasha'))}")
            st.write(f"Next Mahadasha: {_format_dasha(features.get('next_dasha'))}")
            st.write(f"Next Antardasha: {_format_dasha(features.get('next_antardasha'))}")

        with st.expander("Planetary placements", expanded=False):
            st.json(features.get("planets", {}))

        with st.expander("House lordships and dignities", expanded=False):
            st.json(
                {
                    "house_lordships": features.get("house_lordships", {}),
                    "planetary_dignities": features.get("planetary_dignities", {}),
                }
            )

        if st.session_state.last_prompt_preview:
            with st.expander("Prompt preview (last linear run)", expanded=False):
                prev = st.session_state.last_prompt_preview
                st.code(prev[:3000], language="text")
                if len(prev) > 3000:
                    st.caption("Truncated for readability.")

    # Always visible chat composer (feels like real chat).
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
