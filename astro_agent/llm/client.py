"""Ollama HTTP client for generation."""

import argparse
import json
import os
import time

import requests

from astro_agent.chart.engine import build_chart_features
from astro_agent.llm import config as llm_cfg
from astro_agent.llm.prompts.builder import build_career_prompt
from astro_agent.rag.inject import _strip_unknown_refs, build_rag_enriched_prompt
from astro_agent.utils.cities import CityResolutionError
from astro_agent.utils.tracer import estimate_prompt_tokens, trace_llm_call

# Re-exports for callers/tests that import these names from client.
OLLAMA_URL = llm_cfg.OLLAMA_GENERATE_URL
MODEL_NAME = llm_cfg.MODEL_NAME
DEEP_MODEL_NAME = llm_cfg.DEEP_MODEL_NAME
DEFAULT_TIMEOUT_S = llm_cfg.DEFAULT_TIMEOUT_S
DEFAULT_NUM_CTX = llm_cfg.DEFAULT_NUM_CTX


def resolve_ollama_config(model_name=None, timeout_s=None, num_ctx=None, deep=False):
    """Resolve model, timeout, and context window from args/env/defaults."""
    env_deep = (os.getenv("ASTRO_DEEP_MODEL") or "").strip().lower()
    use_deep = bool(deep) or env_deep in ("1", "true", "yes")
    default_model = llm_cfg.DEEP_MODEL_NAME if use_deep else llm_cfg.MODEL_NAME
    env_model = os.getenv("ASTRO_MODEL_NAME")
    env_timeout = os.getenv("ASTRO_OLLAMA_TIMEOUT_S")
    env_num_ctx = os.getenv("ASTRO_NUM_CTX")

    resolved_model = model_name or env_model or default_model
    resolved_timeout = timeout_s
    if resolved_timeout is None:
        if env_timeout and env_timeout.isdigit():
            resolved_timeout = int(env_timeout)
        else:
            resolved_timeout = llm_cfg.DEFAULT_TIMEOUT_S

    resolved_num_ctx = num_ctx
    if resolved_num_ctx is None:
        if env_num_ctx and env_num_ctx.isdigit():
            resolved_num_ctx = int(env_num_ctx)
        else:
            resolved_num_ctx = llm_cfg.DEFAULT_NUM_CTX

    return (
        resolved_model,
        max(llm_cfg.MIN_TIMEOUT_S, int(resolved_timeout)),
        max(llm_cfg.MIN_NUM_CTX, int(resolved_num_ctx)),
    )


def _call_ollama(
    prompt,
    stream=False,
    temperature=None,
    timeout_s=None,
    model_name=None,
    num_ctx=None,
    response_format=None,
):
    if temperature is None:
        temperature = llm_cfg.DEFAULT_TEMPERATURE
    if timeout_s is None:
        timeout_s = llm_cfg.DEFAULT_TIMEOUT_S
    resolved_model, resolved_timeout, resolved_num_ctx = resolve_ollama_config(
        model_name=model_name, timeout_s=timeout_s, num_ctx=num_ctx
    )
    payload = {
        "model": resolved_model,
        "prompt": prompt,
        "stream": stream,
        "options": {"num_ctx": resolved_num_ctx, "temperature": temperature},
    }
    if response_format is not None:
        payload["format"] = response_format
    return requests.post(
        llm_cfg.OLLAMA_GENERATE_URL,
        json=payload,
        stream=stream,
        timeout=(llm_cfg.HTTP_CONNECT_TIMEOUT_S, resolved_timeout),
    ), resolved_model


def run_astro_query(prompt, model_name=None, timeout_s=None, allowed_refs=None, num_ctx=None):
    """Run a prompt against local Ollama and stream output."""
    try:
        print("\nAsking local model... (this can take time on first run)\n", flush=True)
        response, _resolved_model = _call_ollama(
            prompt,
            stream=True,
            temperature=llm_cfg.DEFAULT_TEMPERATURE,
            timeout_s=timeout_s,
            model_name=model_name,
            num_ctx=num_ctx,
        )
        response.raise_for_status()

        got_any_chunk = False
        streamed_parts = []
        for line in response.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            text = chunk.get("response", "")
            if text:
                got_any_chunk = True
                streamed_parts.append(text)
                print(text, end="", flush=True)
            if chunk.get("done"):
                break

        if not got_any_chunk:
            print("\nNo response tokens received from Ollama. Try a smaller model or restart Ollama.", flush=True)
        else:
            print("", flush=True)
            if allowed_refs is not None:
                raw_text = "".join(streamed_parts)
                _, dropped = _strip_unknown_refs(raw_text, allowed_refs)
                dropped_unique = sorted(set(dropped))
                dropped_str = ", ".join(dropped_unique) if dropped_unique else "none"
                print(
                    f"[rag] retrieved={len(set(allowed_refs))} refs, hallucinated={len(dropped_unique)} stripped: {dropped_str}",
                    flush=True,
                )
    except requests.exceptions.Timeout:
        print(
            "\nError: Ollama timed out before sending output. Model may be too heavy for current hardware.", flush=True
        )
    except requests.exceptions.RequestException as e:
        print(f"\nError calling Ollama API: {e}", flush=True)
    except json.JSONDecodeError as e:
        print(f"\nError decoding Ollama stream: {e}", flush=True)


def query_ollama_once(
    prompt,
    temperature=None,
    timeout_s=60,
    model_name=None,
    allowed_refs=None,
    num_ctx=None,
    response_format=None,
    *,
    intent=None,
    rag_active=False,
    ref_count=0,
):
    """Single non-streaming call, useful for evaluation harness."""
    if temperature is None:
        temperature = llm_cfg.DEFAULT_TEMPERATURE
    t0 = time.perf_counter()
    resolved_model = model_name
    try:
        response, resolved_model = _call_ollama(
            prompt,
            stream=False,
            temperature=temperature,
            timeout_s=timeout_s,
            model_name=model_name,
            num_ctx=num_ctx,
            response_format=response_format,
        )
        response.raise_for_status()
        data = response.json()
        text = data.get("response", "").strip()
        dropped_count = 0
        if allowed_refs is None:
            cleaned = text
        else:
            cleaned, dropped = _strip_unknown_refs(text, allowed_refs)
            dropped_count = len(set(d for d in dropped if d != "*"))
            cleaned = cleaned.strip()
        latency_ms = (time.perf_counter() - t0) * 1000
        trace_llm_call(
            model=resolved_model,
            latency_ms=latency_ms,
            intent=intent,
            prompt_tokens_est=estimate_prompt_tokens(prompt),
            rag_active=rag_active,
            ref_count=ref_count,
            hallucinated_refs=dropped_count,
        )
        return cleaned
    except requests.exceptions.RequestException:
        return ""
    except ValueError:
        return ""


def parse_args():
    parser = argparse.ArgumentParser(description="Generate chart features and run a career query on Ollama.")
    parser.add_argument("--year", type=int, default=1996)
    parser.add_argument("--month", type=int, default=12)
    parser.add_argument("--day", type=int, default=26)
    parser.add_argument("--hour", type=int, default=19)
    parser.add_argument("--minute", type=int, default=0)
    parser.add_argument("--city", type=str, default="delhi")
    parser.add_argument("--question", type=str, default="What is the professional outlook for this chart?")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--num-ctx", type=int, default=None)
    parser.add_argument(
        "--deep", action="store_true", help=f"Use {DEEP_MODEL_NAME} instead of the default {MODEL_NAME}."
    )
    parser.add_argument("--no-preview", action="store_true")
    rag_group = parser.add_mutually_exclusive_group()
    rag_group.add_argument("--rag-on", action="store_true", dest="rag_on")
    rag_group.add_argument("--rag-off", action="store_false", dest="rag_on")
    parser.set_defaults(rag_on=False)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    model_name, timeout_s, num_ctx = resolve_ollama_config(
        model_name=args.model,
        timeout_s=args.timeout,
        num_ctx=args.num_ctx,
        deep=args.deep,
    )
    print(
        f"Using model={model_name} timeout_s={timeout_s} num_ctx={num_ctx} "
        f"(ASTRO_MODEL_NAME={os.getenv('ASTRO_MODEL_NAME', '') or 'unset'}, "
        f"ASTRO_DEEP_MODEL={os.getenv('ASTRO_DEEP_MODEL', '') or 'unset'}, "
        f"ASTRO_OLLAMA_TIMEOUT_S={os.getenv('ASTRO_OLLAMA_TIMEOUT_S', '') or 'unset'}, "
        f"ASTRO_NUM_CTX={os.getenv('ASTRO_NUM_CTX', '') or 'unset'})",
        flush=True,
    )

    try:
        features = build_chart_features(args.year, args.month, args.day, args.hour, args.minute, args.city)
    except CityResolutionError as exc:
        print(f"Error: {exc}", flush=True)
        raise SystemExit(1) from exc
    if args.rag_on:
        from astro_agent.routing.intent_router import detect_intent

        detected_intent = detect_intent(question=args.question, timeout_s=min(45, timeout_s)).get("intent", "general")
        rag_bundle = build_rag_enriched_prompt(features, args.question, detected_intent)
        prompt = rag_bundle["prompt"]
        allowed_refs = rag_bundle["allowed_refs"]
        print(
            f"RAG mode: ON | intent={rag_bundle['intent']} | refs={len(allowed_refs)} | active={rag_bundle['rag_active']}",
            flush=True,
        )
    else:
        prompt = build_career_prompt(features, args.question)
        allowed_refs = None
        print("RAG mode: OFF", flush=True)

    if not args.no_preview:
        print("PROMPT DATA GENERATED:\n")
        print(prompt[: llm_cfg.PROMPT_PREVIEW_CHARS] + "\n...\n")
        if args.rag_on:
            print(f"[rag] prompt preview includes refs={len(allowed_refs)}\n", flush=True)

    run_astro_query(prompt, model_name=model_name, timeout_s=timeout_s, allowed_refs=allowed_refs, num_ctx=num_ctx)
