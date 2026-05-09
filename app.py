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
from intent_router import detect_intent
from utils import CITY_COORDINATES


def run_ollama_ui_query_stream(prompt, model_name=None, timeout_s=None):
    """Yield streaming text chunks and return final error code."""
    try:
        # Lightweight preflight so we can show a clear connection error.
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


def main():
    st.set_page_config(page_title="Astro AI Agent", page_icon="🔭", layout="wide")
    st.title("Astro AI Agent")
    st.caption("Interactive Vedic astrology analysis powered by your local Ollama model.")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "is_processing" not in st.session_state:
        st.session_state.is_processing = False
    if "pending_request" not in st.session_state:
        st.session_state.pending_request = None

    with st.form("astro_form"):
        col1, col2, col3 = st.columns(3)

        with col1:
            birth_date = st.date_input(
                "Birth Date (IST)",
                value=dt.date(1998, 9, 27),
                disabled=st.session_state.is_processing,
            )
        with col2:
            birth_time = st.time_input(
                "Birth Time (IST)",
                value=dt.time(13, 0),
                disabled=st.session_state.is_processing,
            )
        with col3:
            city_name = st.selectbox(
                "Birth City",
                options=_city_options(),
                index=1,
                disabled=st.session_state.is_processing,
            )

        question = st.text_area(
            "What are you looking for?",
            value="What is the professional outlook for this chart?",
            help="Describe the domain and what kind of guidance you want.",
            height=100,
            disabled=st.session_state.is_processing,
        )
        rag_enabled = st.checkbox(
            "Enable RAG retrieval for this query",
            value=True,
            help="When enabled, the prompt includes classical references and citation rules.",
            disabled=st.session_state.is_processing,
        )

        st.subheader("Model Settings")
        model_col, timeout_col = st.columns(2)
        with model_col:
            model_input = st.text_input(
                "Model name override (optional)",
                value="",
                placeholder="e.g. deepseek-r1:7b",
                disabled=st.session_state.is_processing,
            )
        with timeout_col:
            timeout_input = st.number_input(
                "Timeout (seconds)",
                min_value=15,
                max_value=1800,
                value=120,
                step=15,
                disabled=st.session_state.is_processing,
            )

        submitted = st.form_submit_button(
            "Generate Analysis",
            type="primary",
            disabled=st.session_state.is_processing,
        )

    if submitted and not st.session_state.is_processing:
        cleaned_question = question.strip()
        if not cleaned_question:
            st.error("Please enter what you are looking for before generating analysis.")
            return

        st.session_state.pending_request = {
            "birth_date": birth_date.isoformat(),
            "birth_time": birth_time.strftime("%H:%M"),
            "city_name": city_name,
            "question": cleaned_question,
            "rag_enabled": bool(rag_enabled),
            "model_input": model_input.strip(),
            "timeout_input": int(timeout_input),
        }
        st.session_state.is_processing = True
        st.rerun()

    if not st.session_state.pending_request:
        return

    request_data = st.session_state.pending_request
    birth_date = dt.date.fromisoformat(request_data["birth_date"])
    birth_time = dt.time.fromisoformat(request_data["birth_time"])
    city_name = request_data["city_name"]
    cleaned_question = request_data["question"]
    rag_enabled = bool(request_data.get("rag_enabled", True))
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
    try:
        rag_bundle = None
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
                    model_name=resolved_model,
                    timeout_s=min(45, resolved_timeout),
                    num_ctx=resolved_num_ctx,
                )
            except Exception:
                intent_info = {
                    "intent": "general",
                    "method": "rules_fallback",
                    "confidence": 0.0,
                    "rule_scores": {},
                }
            chosen_intent = intent_info.get("intent", "general")
            if rag_enabled:
                rag_bundle = build_rag_enriched_prompt(features, cleaned_question, chosen_intent)
                prompt = rag_bundle["prompt"]
            else:
                prompt = build_prompt_for_intent(features, cleaned_question, chosen_intent)
        st.session_state.chat_history.append({"role": "user", "content": cleaned_question})

        st.subheader("Conversation")
        for msg in st.session_state.chat_history[:-1]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        with st.chat_message("user"):
            st.markdown(cleaned_question)

        final_answer = ""
        error_code = None
        with st.chat_message("assistant"):
            stream_placeholder = st.empty()
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
                    stream_placeholder.markdown(final_answer + "▌")
            if final_answer:
                stream_placeholder.markdown(final_answer)

        if error_code == "connection":
            st.error("Could not connect to Ollama at `http://localhost:11434`. Start Ollama and retry.")
            return
        if error_code == "timeout":
            st.error(f"The request timed out after {resolved_timeout}s. Try increasing timeout or using a smaller model.")
            return
        if error_code:
            st.error("Model call failed unexpectedly. Please retry.")
            return
        if not final_answer:
            st.warning("No response text was returned by Ollama. Try a smaller model, higher timeout, or restart Ollama.")
            return

        if rag_enabled and rag_bundle and rag_bundle.get("allowed_refs"):
            final_answer, _ = _strip_unknown_refs(final_answer, rag_bundle.get("allowed_refs"))

        st.session_state.chat_history.append({"role": "assistant", "content": final_answer})
        st.success("Analysis generated successfully.")
        info1, info2, info3, info4 = st.columns(4)
        info1.metric("Model", resolved_model)
        info2.metric("Active Mahadasha", features["active_dasha"]["dasha"] if features["active_dasha"] else "Unknown")
        info3.metric("Next Mahadasha", features["next_dasha"]["dasha"] if features["next_dasha"] else "Unknown")
        info4.metric("Detected Intent", intent_info.get("intent", "general"))
        st.caption(
            f"RAG: {'ON' if rag_enabled else 'OFF'}"
            + (
                f" | Retrieved refs: {len(rag_bundle.get('allowed_refs', []))}"
                if rag_enabled and rag_bundle
                else ""
            )
        )

        with st.expander("Input Summary", expanded=False):
            st.json(
                {
                    "birth_date_ist": birth_date.isoformat(),
                    "birth_time_ist": birth_time.strftime("%H:%M"),
                    "city_name": city_name,
                    "question": cleaned_question,
                    "rag_enabled": rag_enabled,
                    "resolved_model": resolved_model,
                    "resolved_timeout_s": resolved_timeout,
                    "detected_intent": intent_info.get("intent", "general"),
                    "intent_detection_method": intent_info.get("method", "rules_fallback"),
                    "intent_confidence": intent_info.get("confidence", 0.0),
                    "intent_rule_scores": intent_info.get("rule_scores", {}),
                }
            )

        if rag_enabled:
            retrieved_chunks = (rag_bundle or {}).get("retrieved", [])
            with st.expander("Sources", expanded=False):
                if not retrieved_chunks:
                    st.info("No RAG sources were retrieved for this query.")
                else:
                    for idx, chunk in enumerate(retrieved_chunks, start=1):
                        ref_id = _chunk_value(chunk, "ref_id", f"ref_{idx}")
                        similarity = _chunk_value(chunk, "similarity", None)
                        matched_entities = _chunk_value(chunk, "matched_entities", []) or []
                        chunk_text = (_chunk_value(chunk, "text", "") or "").strip()

                        header = f"{idx}. {ref_id}"
                        if similarity is not None:
                            header += f" (sim={float(similarity):.3f})"
                        with st.expander(header, expanded=False):
                            if matched_entities:
                                st.caption("Matched entities: " + ", ".join(str(entity) for entity in matched_entities))
                            st.write(chunk_text or "_No chunk text available._")

        with st.expander("Dasha Snapshot", expanded=False):
            st.write(f"Active: {_format_dasha(features.get('active_dasha'))}")
            st.write(f"Next: {_format_dasha(features.get('next_dasha'))}")

        with st.expander("Planetary Placements", expanded=False):
            st.json(features.get("planets", {}))

        with st.expander("House Lordships and Dignities", expanded=False):
            st.json(
                {
                    "house_lordships": features.get("house_lordships", {}),
                    "planetary_dignities": features.get("planetary_dignities", {}),
                }
            )

        with st.expander("Prompt Preview", expanded=False):
            st.code(prompt[:3000], language="text")
            if len(prompt) > 3000:
                st.caption("Prompt preview truncated for readability.")
    finally:
        st.session_state.is_processing = False
        st.session_state.pending_request = None


if __name__ == "__main__":
    main()
