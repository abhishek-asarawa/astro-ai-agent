"""Agentic ReAct loop using Ollama native tool-calling (>= 0.3).

Exposes tools to the model: build_chart, rag_search, get_dasha, get_timing_window, detect_intent.
Runs at most MAX_AGENT_TURNS tool-call rounds before falling back to the current
linear prompt-and-generate path.
"""

from __future__ import annotations

import json
import os
import time
import requests

from astro_agent.rag import search as rag_search
from astro_agent.utils.tracer import estimate_prompt_tokens, trace_llm_call
from astro_agent.rag import config as cfg
from astro_agent.rag.inject import _features_to_chart_facts, _strip_unknown_refs, build_rag_enriched_prompt
from astro_agent.llm.prompts.builder import build_prompt_for_intent
from astro_agent.llm.client import query_ollama_once, resolve_ollama_config
from astro_agent.utils.text_utils import extract_ref_ids, strip_reasoning_blocks
from astro_agent.chart.dashas import format_dasha_timeline
from astro_agent.chart.timing import build_timing_report
from astro_agent.routing.intent_router import detect_intent as _detect_intent

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
MAX_AGENT_TURNS = int(os.environ.get("ASTRO_MAX_AGENT_TURNS", "4"))

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "build_chart",
            "description": (
                "Return a compact Vedic chart summary for the native: lagna, "
                "planet placements with dignities, and house lordships."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": (
                "Search the BPHS classical reference corpus for verses relevant to a query. "
                "Returns ref-tagged chunk texts you can cite in Evidence bullets."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query describing what classical guidance to find"},
                    "intent": {"type": "string", "enum": ["career", "health", "wealth", "family", "general"], "description": "Domain intent to bias retrieval toward"},
                    "top_k": {"type": "integer", "description": "Number of chunks to return (default 5, max 8)"},
                },
                "required": ["query", "intent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dasha",
            "description": (
                "Return the current Mahadasha/Antardasha snapshot and full Vimshottari Mahadasha timeline. "
                "Use for present-period facts only; for date windows, countdowns, or upcoming changes use get_timing_window."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_timing_window",
            "description": (
                "Resolve a timing window (e.g. next 6 months, coming 6 days) and return JSON with active periods, "
                "days until sub-period ends, dasha transitions inside the window, and a near-term 6-day checkpoint."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "window_text": {
                        "type": "string",
                        "description": "Natural-language horizon from the question, e.g. 'next 6 months' or 'coming 6 days'",
                    },
                    "as_of_date": {
                        "type": "string",
                        "description": "Optional ISO date (YYYY-MM-DD) for today; defaults to current session date",
                    },
                    "start_date": {
                        "type": "string",
                        "description": "Optional explicit window start (YYYY-MM-DD) when parsing fails",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "Optional explicit window end (YYYY-MM-DD) when parsing fails",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_intent",
            "description": "Classify the user question into one astrological domain: career, health, wealth, family, or general.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The user question to classify"}
                },
                "required": ["question"],
            },
        },
    },
]


def _tool_build_chart(features: dict) -> str:
    lagna = features.get("lagna", {})
    planets = features.get("planets", {})
    dignities = features.get("planetary_dignities", {})
    house_lords = features.get("house_lordships", {})

    lines = [f"Lagna: {lagna.get('rashi', '?')} ({lagna.get('degrees', '?')}°)"]
    for name, data in planets.items():
        d = dignities.get(name, "[NEUTRAL]")
        lines.append(f"  {name}: {data['rashi']} ({data['degrees']}°) {data['nakshatra']} {d}")
    lines.append("\nHouse Lordships:")
    for planet, houses in house_lords.items():
        if houses:
            lines.append(f"  {planet}: houses {houses}")
    return "\n".join(lines)


def _tool_rag_search(features: dict, query: str, intent: str, top_k: int = 5) -> str:
    chart_facts = _features_to_chart_facts(features)
    top_k = min(int(top_k), 8)
    try:
        chunks = rag_search.search(question=query, intent=intent, chart_facts=chart_facts, top_k=top_k)
    except Exception as exc:
        return f"[rag_search error: {exc}]"
    if not chunks:
        return "[No classical references found for this query]"
    lines = []
    for chunk in chunks:
        ref_id = getattr(chunk, "ref_id", "?")
        text = (getattr(chunk, "text", "") or "").strip()
        lines.append(f"[ref:{ref_id}]: {text}")
    return "\n".join(lines)


def _tool_get_dasha(features: dict) -> str:
    active = features.get("active_dasha") or {}
    nxt = features.get("next_dasha") or {}
    active_ant = features.get("active_antardasha") or {}
    next_ant = features.get("next_antardasha") or {}
    timeline = features.get("dasha_timeline", [])
    lines = [
        f"Active Mahadasha: {active.get('dasha', '?')} ({active.get('start', '?')} to {active.get('end', '?')})",
        f"Active Antardasha: {active_ant.get('dasha', '?')} ({active_ant.get('start', '?')} to {active_ant.get('end', '?')})",
        f"Next Mahadasha: {nxt.get('dasha', '?')} ({nxt.get('start', '?')} to {nxt.get('end', '?')})",
        f"Next Antardasha: {next_ant.get('dasha', '?')} ({next_ant.get('start', '?')} to {next_ant.get('end', '?')})",
        "",
        format_dasha_timeline(timeline),
    ]
    return "\n".join(lines)


def _tool_get_timing_window(features: dict, tool_args: dict) -> str:
    report = build_timing_report(
        features,
        window_text=tool_args.get("window_text"),
        as_of_date=tool_args.get("as_of_date"),
        start_date=tool_args.get("start_date"),
        end_date=tool_args.get("end_date"),
    )
    return json.dumps(report)


def _tool_detect_intent(question: str, timeout_s: int = 30) -> str:
    result = _detect_intent(question=question, timeout_s=timeout_s)
    return json.dumps(result)


def _dispatch_tool(tool_name: str, tool_args: dict, features: dict, timeout_s: int) -> str:
    if tool_name == "build_chart":
        return _tool_build_chart(features)
    if tool_name == "rag_search":
        return _tool_rag_search(features, query=tool_args.get("query", ""), intent=tool_args.get("intent", "general"), top_k=int(tool_args.get("top_k", 5)))
    if tool_name == "get_dasha":
        return _tool_get_dasha(features)
    if tool_name == "get_timing_window":
        return _tool_get_timing_window(features, tool_args)
    if tool_name == "detect_intent":
        return _tool_detect_intent(question=tool_args.get("question", ""), timeout_s=min(30, timeout_s))
    return f"[Unknown tool: {tool_name}]"


def _call_ollama_chat(messages: list[dict], model_name: str, timeout_s: int, num_ctx: int, tools: list[dict] | None = None) -> dict | None:
    payload: dict = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": num_ctx, "temperature": 0.2},
    }
    if tools:
        payload["tools"] = tools
    t0 = time.perf_counter()
    try:
        resp = requests.post(OLLAMA_CHAT_URL, json=payload, timeout=(10, timeout_s))
        resp.raise_for_status()
        data = resp.json()
        trace_llm_call(
            model=model_name,
            latency_ms=(time.perf_counter() - t0) * 1000,
            prompt_tokens_est=estimate_prompt_tokens(str(messages)),
            stage="agent_chat",
        )
        return data
    except requests.exceptions.Timeout:
        print("[agent_loop] chat call timed out", flush=True)
        return None
    except requests.exceptions.RequestException as exc:
        print(f"[agent_loop] chat call failed: {exc}", flush=True)
        return None
    except ValueError as exc:
        print(f"[agent_loop] chat response decode failed: {exc}", flush=True)
        return None


def _linear_fallback(user_question, features, intent, model_name, timeout_s, num_ctx, rag_enabled, prior_context):
    if rag_enabled:
        bundle = build_rag_enriched_prompt(features, user_question, intent, prior_context=prior_context)
        prompt = bundle["prompt"]
        allowed_refs = bundle.get("allowed_refs")
    else:
        prompt = build_prompt_for_intent(features, user_question, intent, prior_context=prior_context)
        allowed_refs = None

    answer = query_ollama_once(
        prompt, temperature=0.2, timeout_s=timeout_s, model_name=model_name, allowed_refs=allowed_refs, num_ctx=num_ctx,
    )
    return answer or ""


def run_agent_loop(
    user_question: str,
    features: dict,
    intent: str = "general",
    model_name: str | None = None,
    timeout_s: int | None = None,
    num_ctx: int | None = None,
    rag_enabled: bool = True,
    prior_context: str | None = None,
) -> dict:
    """ReAct agentic loop using Ollama native tool-calling."""
    resolved_model, resolved_timeout, resolved_num_ctx = resolve_ollama_config(
        model_name=model_name, timeout_s=timeout_s, num_ctx=num_ctx
    )

    system_content = (
        "You are a thoughtful Vedic astrologer helping a non-expert client. "
        "Use the available tools to gather chart data, classical references, and life-period information before answering. "
        "For any question with a time horizon (next N months/days/years, this year, coming week), call get_timing_window "
        "before writing your final answer so you know when dasha periods change. "
        "Write in warm, clear English. Avoid unexplained jargon (no bare '5th lord', 'debilitated', 'trik house', 'Vimshottari', 'Mahadasha', or 'Antardasha' without a short plain-language explanation). "
        "After gathering what you need, provide a complete structured analysis with: "
        "Summary, Evidence (cite classical refs with [ref:...] tags when you use them), Risk, Opportunity, and a Confidence score (0-100). "
        "Evidence bullets must be understandable to someone new to astrology."
    )
    if prior_context:
        system_content += f"\n\nPriorContext:\n{prior_context}"

    messages: list[dict] = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_question},
    ]

    tool_calls_made: list[str] = []
    seen_rag_refs: list[str] = []
    turns_taken = 0

    while turns_taken < MAX_AGENT_TURNS:
        data = _call_ollama_chat(
            messages=messages, model_name=resolved_model, timeout_s=resolved_timeout,
            num_ctx=resolved_num_ctx, tools=TOOLS,
        )
        if data is None:
            break

        msg = data.get("message", {})
        content: str = msg.get("content", "") or ""
        tool_calls: list = msg.get("tool_calls") or []

        if not tool_calls:
            if content.strip():
                answer = strip_reasoning_blocks(content.strip())
                if seen_rag_refs:
                    answer, _ = _strip_unknown_refs(answer, seen_rag_refs)
                return {"answer": answer, "method": "agent", "tool_calls_made": tool_calls_made, "error": None}
            break

        messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})

        for tc in tool_calls:
            fn = tc.get("function", {})
            tool_name: str = fn.get("name", "")
            raw_args = fn.get("arguments", {})
            if isinstance(raw_args, dict):
                tool_args: dict = raw_args
            elif isinstance(raw_args, str):
                try:
                    tool_args = json.loads(raw_args) if raw_args.strip() else {}
                except (json.JSONDecodeError, ValueError):
                    tool_args = {}
            else:
                tool_args = {}

            print(f"[agent_loop] tool_call: {tool_name}({tool_args})", flush=True)
            tool_calls_made.append(tool_name)

            result = _dispatch_tool(tool_name, tool_args, features, resolved_timeout)
            if tool_name == "rag_search":
                seen_rag_refs.extend(extract_ref_ids(result))
            messages.append({"role": "tool", "content": result})

        turns_taken += 1

    print(f"[agent_loop] falling back to linear path after {turns_taken} tool turn(s)", flush=True)
    answer = _linear_fallback(
        user_question=user_question, features=features, intent=intent,
        model_name=resolved_model, timeout_s=resolved_timeout, num_ctx=resolved_num_ctx,
        rag_enabled=rag_enabled, prior_context=prior_context,
    )
    return {"answer": strip_reasoning_blocks(answer), "method": "linear_fallback", "tool_calls_made": tool_calls_made, "error": None}
