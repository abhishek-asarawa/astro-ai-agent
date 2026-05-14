"""
agent_loop.py — Agentic ReAct loop using Ollama native tool-calling (>= 0.3).

Exposes four tools to the model: build_chart, rag_search, get_dasha, detect_intent.
Runs at most MAX_AGENT_TURNS tool-call rounds before falling back to the current
linear prompt-and-generate path.
"""

from __future__ import annotations

import json
import requests

import rag_search
import rag_config as cfg
from astro_engine import (
    _features_to_chart_facts,
    _strip_unknown_refs,
    build_rag_enriched_prompt,
    build_prompt_for_intent,
    query_ollama_once,
    resolve_ollama_config,
)
from dashas import format_dasha_timeline
from intent_router import detect_intent as _detect_intent
from text_utils import strip_reasoning_blocks

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
MAX_AGENT_TURNS = 2

# ---------------------------------------------------------------------------
# Tool schemas (Ollama native tools format)
# ---------------------------------------------------------------------------

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
                    "query": {
                        "type": "string",
                        "description": "The search query describing what classical guidance to find",
                    },
                    "intent": {
                        "type": "string",
                        "enum": ["career", "health", "wealth", "family", "general"],
                        "description": "Domain intent to bias retrieval toward",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of chunks to return (default 5, max 8)",
                    },
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
                "Return the active Mahadasha, active Antardasha, next Mahadasha, next Antardasha, "
                "and full Vimshottari Mahadasha timeline for the native."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_intent",
            "description": (
                "Classify the user question into one astrological domain: "
                "career, health, wealth, family, or general."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The user question to classify",
                    }
                },
                "required": ["question"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Tool implementations (closures over pre-computed features)
# ---------------------------------------------------------------------------


def _tool_build_chart(features: dict) -> str:
    lagna = features.get("lagna", {})
    planets = features.get("planets", {})
    dignities = features.get("planetary_dignities", {})
    house_lords = features.get("house_lordships", {})

    lines = [f"Lagna: {lagna.get('rashi', '?')} ({lagna.get('degrees', '?')}°)"]
    for name, data in planets.items():
        d = dignities.get(name, "[NEUTRAL]")
        lines.append(
            f"  {name}: {data['rashi']} ({data['degrees']}°) "
            f"{data['nakshatra']} {d}"
        )
    lines.append("\nHouse Lordships:")
    for planet, houses in house_lords.items():
        if houses:
            lines.append(f"  {planet}: houses {houses}")
    return "\n".join(lines)


def _tool_rag_search(features: dict, query: str, intent: str, top_k: int = 5) -> str:
    chart_facts = _features_to_chart_facts(features)
    top_k = min(int(top_k), 8)
    try:
        chunks = rag_search.search(
            question=query,
            intent=intent,
            chart_facts=chart_facts,
            top_k=top_k,
        )
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
        f"Active Mahadasha: {active.get('dasha', '?')} "
        f"({active.get('start', '?')} to {active.get('end', '?')})",
        f"Active Antardasha: {active_ant.get('dasha', '?')} "
        f"({active_ant.get('start', '?')} to {active_ant.get('end', '?')})",
        f"Next Mahadasha: {nxt.get('dasha', '?')} "
        f"({nxt.get('start', '?')} to {nxt.get('end', '?')})",
        f"Next Antardasha: {next_ant.get('dasha', '?')} "
        f"({next_ant.get('start', '?')} to {next_ant.get('end', '?')})",
        "",
        format_dasha_timeline(timeline),
    ]
    return "\n".join(lines)


def _tool_detect_intent(question: str, timeout_s: int = 30) -> str:
    result = _detect_intent(question=question, timeout_s=timeout_s)
    return json.dumps(result)


def _dispatch_tool(
    tool_name: str,
    tool_args: dict,
    features: dict,
    timeout_s: int,
) -> str:
    """Execute a named tool and return its string result."""
    if tool_name == "build_chart":
        return _tool_build_chart(features)
    if tool_name == "rag_search":
        return _tool_rag_search(
            features,
            query=tool_args.get("query", ""),
            intent=tool_args.get("intent", "general"),
            top_k=int(tool_args.get("top_k", 5)),
        )
    if tool_name == "get_dasha":
        return _tool_get_dasha(features)
    if tool_name == "detect_intent":
        return _tool_detect_intent(
            question=tool_args.get("question", ""),
            timeout_s=min(30, timeout_s),
        )
    return f"[Unknown tool: {tool_name}]"


# ---------------------------------------------------------------------------
# Ollama /api/chat wrapper
# ---------------------------------------------------------------------------


def _call_ollama_chat(
    messages: list[dict],
    model_name: str,
    timeout_s: int,
    num_ctx: int,
    tools: list[dict] | None = None,
) -> dict | None:
    """POST to /api/chat. Returns parsed response dict or None on error."""
    payload: dict = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": num_ctx, "temperature": 0.2},
    }
    if tools:
        payload["tools"] = tools
    try:
        resp = requests.post(
            OLLAMA_CHAT_URL,
            json=payload,
            timeout=(10, timeout_s),
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        print("[agent_loop] chat call timed out", flush=True)
        return None
    except requests.exceptions.RequestException as exc:
        print(f"[agent_loop] chat call failed: {exc}", flush=True)
        return None
    except ValueError as exc:
        print(f"[agent_loop] chat response decode failed: {exc}", flush=True)
        return None


# ---------------------------------------------------------------------------
# Linear fallback
# ---------------------------------------------------------------------------


def _linear_fallback(
    user_question: str,
    features: dict,
    intent: str,
    model_name: str,
    timeout_s: int,
    num_ctx: int,
    rag_enabled: bool,
    prior_context: str | None,
) -> str:
    """Non-streaming linear path: build prompt → query_ollama_once."""
    if rag_enabled:
        bundle = build_rag_enriched_prompt(
            features, user_question, intent, prior_context=prior_context
        )
        prompt = bundle["prompt"]
        allowed_refs = bundle.get("allowed_refs")
    else:
        prompt = build_prompt_for_intent(
            features, user_question, intent, prior_context=prior_context
        )
        allowed_refs = None

    answer = query_ollama_once(
        prompt,
        temperature=0.2,
        timeout_s=timeout_s,
        model_name=model_name,
        allowed_refs=allowed_refs,
        num_ctx=num_ctx,
    )
    return answer or ""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


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
    """
    ReAct agentic loop using Ollama native tool-calling.

    Sends the user question to Ollama with TOOLS available.  If the model
    issues tool calls, executes them and feeds results back — up to
    MAX_AGENT_TURNS rounds.  If no final answer is produced, falls back to the
    current linear path (build_rag_enriched_prompt + query_ollama_once).

    Returns:
        {
            "answer": str,
            "method": "agent" | "linear_fallback",
            "tool_calls_made": list[str],
            "error": str | None,
        }
    """
    resolved_model, resolved_timeout, resolved_num_ctx = resolve_ollama_config(
        model_name=model_name, timeout_s=timeout_s, num_ctx=num_ctx
    )

    system_content = (
        "You are an expert Vedic astrologer. "
        "Use the available tools to gather chart data, classical references, and dasha "
        "information before answering the user's question. "
        "After gathering what you need, provide a complete structured analysis with: "
        "Summary, Evidence (cite classical refs with [ref:...] tags), Risk, Opportunity, "
        "and a Confidence score (0-100)."
    )
    if prior_context:
        system_content += f"\n\nPriorContext:\n{prior_context}"

    messages: list[dict] = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_question},
    ]

    tool_calls_made: list[str] = []
    turns_taken = 0

    while turns_taken < MAX_AGENT_TURNS:
        data = _call_ollama_chat(
            messages=messages,
            model_name=resolved_model,
            timeout_s=resolved_timeout,
            num_ctx=resolved_num_ctx,
            tools=TOOLS,
        )
        if data is None:
            break

        msg = data.get("message", {})
        content: str = msg.get("content", "") or ""
        tool_calls: list = msg.get("tool_calls") or []

        if not tool_calls:
            # Model produced a direct answer — done.
            if content.strip():
                return {
                    "answer": strip_reasoning_blocks(content.strip()),
                    "method": "agent",
                    "tool_calls_made": tool_calls_made,
                    "error": None,
                }
            # Empty content with no tool calls — break and fall back.
            break

        # Append the assistant message (with tool_calls) to conversation.
        messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})

        # Execute each tool and append its result.
        for tc in tool_calls:
            fn = tc.get("function", {})
            tool_name: str = fn.get("name", "")
            raw_args = fn.get("arguments", {})
            tool_args: dict = raw_args if isinstance(raw_args, dict) else {}

            print(f"[agent_loop] tool_call: {tool_name}({tool_args})", flush=True)
            tool_calls_made.append(tool_name)

            result = _dispatch_tool(tool_name, tool_args, features, resolved_timeout)
            messages.append({"role": "tool", "content": result})

        turns_taken += 1

    # Exhausted turns or chat failed — fall back to linear path.
    print(
        f"[agent_loop] falling back to linear path after {turns_taken} tool turn(s)",
        flush=True,
    )
    answer = _linear_fallback(
        user_question=user_question,
        features=features,
        intent=intent,
        model_name=resolved_model,
        timeout_s=resolved_timeout,
        num_ctx=resolved_num_ctx,
        rag_enabled=rag_enabled,
        prior_context=prior_context,
    )
    return {
        "answer": strip_reasoning_blocks(answer),
        "method": "linear_fallback",
        "tool_calls_made": tool_calls_made,
        "error": None,
    }
