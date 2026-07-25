"""Agent tool registry: schemas + handlers for the ReAct loop."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from astro_agent.chart.dashas import format_dasha_timeline
from astro_agent.chart.timing import build_timing_report
from astro_agent.intents import SUPPORTED_INTENTS
from astro_agent.rag import search as rag_search
from astro_agent.rag.inject import _features_to_chart_facts
from astro_agent.routing.intent_router import detect_intent as _detect_intent

# Cap how many chunks a single rag_search tool call may return.
RAG_SEARCH_TOP_K_MAX = 8
RAG_SEARCH_TOP_K_DEFAULT = 5
DETECT_INTENT_TIMEOUT_CAP_S = 30


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., str]

    def ollama_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _tool_build_chart(features: dict, **_kwargs) -> str:
    """Return a compact Vedic chart summary for the native."""
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


def _tool_rag_search(
    features: dict, *, query: str = "", intent: str = "general", top_k: int = RAG_SEARCH_TOP_K_DEFAULT, **_kwargs
) -> str:
    """Search the classical corpus; cite returned [ref:...] ids in Evidence."""
    chart_facts = _features_to_chart_facts(features)
    top_k = min(int(top_k), RAG_SEARCH_TOP_K_MAX)
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


def _tool_get_dasha(features: dict, **_kwargs) -> str:
    """Return active/next dasha snapshot and full Vimshottari timeline."""
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


def _tool_get_timing_window(features: dict, tool_args: dict | None = None, **_kwargs) -> str:
    """Resolve a timing window and return JSON timing facts."""
    tool_args = tool_args or {}
    report = build_timing_report(
        features,
        window_text=tool_args.get("window_text"),
        as_of_date=tool_args.get("as_of_date"),
        start_date=tool_args.get("start_date"),
        end_date=tool_args.get("end_date"),
    )
    return json.dumps(report)


def _tool_detect_intent(
    features: dict, *, question: str = "", timeout_s: int = DETECT_INTENT_TIMEOUT_CAP_S, **_kwargs
) -> str:
    """Classify the user question into one domain intent."""
    result = _detect_intent(question=question, timeout_s=timeout_s)
    return json.dumps(result)


_INTENT_ENUM = list(SUPPORTED_INTENTS)

TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="build_chart",
        description=(
            "Return a compact Vedic chart summary for the native: lagna, "
            "planet placements with dignities, and house lordships."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        handler=_tool_build_chart,
    ),
    ToolSpec(
        name="rag_search",
        description=(
            "Search the BPHS classical reference corpus for verses relevant to a query. "
            "Returns ref-tagged chunk texts you can cite in Evidence bullets."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query describing what classical guidance to find",
                },
                "intent": {
                    "type": "string",
                    "enum": _INTENT_ENUM,
                    "description": "Domain intent to bias retrieval toward",
                },
                "top_k": {"type": "integer", "description": "Number of chunks to return (default 5, max 8)"},
            },
            "required": ["query", "intent"],
        },
        handler=_tool_rag_search,
    ),
    ToolSpec(
        name="get_dasha",
        description=(
            "Return the current Mahadasha/Antardasha snapshot and full Vimshottari Mahadasha timeline. "
            "Use for present-period facts only; for date windows, countdowns, or upcoming changes use get_timing_window."
        ),
        parameters={"type": "object", "properties": {}, "required": []},
        handler=_tool_get_dasha,
    ),
    ToolSpec(
        name="get_timing_window",
        description=(
            "Resolve a timing window (e.g. next 6 months, coming 6 days) and return JSON with active periods, "
            "days until sub-period ends, dasha transitions inside the window, and a near-term 6-day checkpoint."
        ),
        parameters={
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
        handler=_tool_get_timing_window,
    ),
    ToolSpec(
        name="detect_intent",
        description="Classify the user question into one astrological domain: career, health, wealth, family, or general.",
        parameters={
            "type": "object",
            "properties": {"question": {"type": "string", "description": "The user question to classify"}},
            "required": ["question"],
        },
        handler=_tool_detect_intent,
    ),
]

TOOLS_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_SPECS}


def ollama_tools_payload() -> list[dict]:
    """JSON tool schemas for Ollama /api/chat."""
    return [spec.ollama_schema() for spec in TOOL_SPECS]


def dispatch_tool(tool_name: str, tool_args: dict, features: dict, timeout_s: int) -> str:
    """Dispatch a tool call by name; unknown tools return an error string."""
    spec = TOOLS_BY_NAME.get(tool_name)
    if spec is None:
        return f"[Unknown tool: {tool_name}]"
    args = dict(tool_args or {})
    if tool_name == "get_timing_window":
        return spec.handler(features, tool_args=args)
    if tool_name == "detect_intent":
        return spec.handler(
            features,
            question=args.get("question", ""),
            timeout_s=min(DETECT_INTENT_TIMEOUT_CAP_S, timeout_s),
        )
    if tool_name == "rag_search":
        return spec.handler(
            features,
            query=args.get("query", ""),
            intent=args.get("intent", "general"),
            top_k=int(args.get("top_k", RAG_SEARCH_TOP_K_DEFAULT)),
        )
    return spec.handler(features)
