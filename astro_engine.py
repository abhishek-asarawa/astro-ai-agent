import swisseph as swe
import requests
import json
import os
import argparse
import re
from datetime import date, datetime
from mapper import get_vedic_details
from utils import CITY_COORDINATES, convert_ist_to_utc
from lords import RASHIS, get_house_lords
from yogas import apply_tags_to_chart
from dashas import calculate_dashas, format_dasha_timeline
import rag_config as cfg
import rag_search

# --- CONFIGURATION ---
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:7b-instruct"
DEEP_MODEL_NAME = "deepseek-r1:14b"
DEFAULT_TIMEOUT_S = 120
DEFAULT_NUM_CTX = 16384
REF_TAG_RE = re.compile(r"\[ref:([^\]]+)\]")


def resolve_ollama_config(model_name=None, timeout_s=None, num_ctx=None, deep=False):
    """Resolve model, timeout, and context window from args/env/defaults."""
    env_deep = (os.getenv("ASTRO_DEEP_MODEL") or "").strip().lower()
    use_deep = bool(deep) or env_deep in ("1", "true", "yes")
    default_model = DEEP_MODEL_NAME if use_deep else MODEL_NAME
    env_model = os.getenv("ASTRO_MODEL_NAME")
    env_timeout = os.getenv("ASTRO_OLLAMA_TIMEOUT_S")
    env_num_ctx = os.getenv("ASTRO_NUM_CTX")

    resolved_model = model_name or env_model or default_model
    resolved_timeout = timeout_s
    if resolved_timeout is None:
        if env_timeout and env_timeout.isdigit():
            resolved_timeout = int(env_timeout)
        else:
            resolved_timeout = DEFAULT_TIMEOUT_S

    resolved_num_ctx = num_ctx
    if resolved_num_ctx is None:
        if env_num_ctx and env_num_ctx.isdigit():
            resolved_num_ctx = int(env_num_ctx)
        else:
            resolved_num_ctx = DEFAULT_NUM_CTX

    return resolved_model, max(15, int(resolved_timeout)), max(1024, int(resolved_num_ctx))

def _setup_julian_day(year, month, day, hour_utc):
    """Prepare sidereal mode and Julian day."""
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)
    return swe.julday(year, month, day, hour_utc)


def _compute_chart_core(year, month, day, hour_utc, city_name="bengaluru"):
    """Compute lagna and planetary placements in a structured format."""
    jd = _setup_julian_day(year, month, day, hour_utc)
    geo = CITY_COORDINATES.get(city_name.lower(), CITY_COORDINATES["bengaluru"])

    res = swe.houses_ex(jd, geo['lat'], geo['lon'], b'P', swe.FLG_SIDEREAL)
    ascendant_long = res[1][0]
    lagna_details = get_vedic_details(ascendant_long)

    planets = {
        "Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, "Mercury": swe.MERCURY,
        "Jupiter": swe.JUPITER, "Venus": swe.VENUS, "Saturn": swe.SATURN, "Rahu": swe.MEAN_NODE
    }

    placements = {}
    rahu_long = 0
    for name, id in planets.items():
        res, _ = swe.calc_ut(jd, id, swe.FLG_SIDEREAL)
        long = res[0]
        if name == "Rahu":
            rahu_long = long
        details = get_vedic_details(long)
        placements[name] = {
            "longitude": round(long, 4),
            "rashi": details["rashi"],
            "degrees": details["degrees"],
            "nakshatra": details["nakshatra"],
        }

    ketu_details = get_vedic_details((rahu_long + 180) % 360)
    placements["Ketu"] = {
        "longitude": round((rahu_long + 180) % 360, 4),
        "rashi": ketu_details["rashi"],
        "degrees": ketu_details["degrees"],
        "nakshatra": ketu_details["nakshatra"],
    }

    return {
        "lagna": {
            "longitude": round(ascendant_long, 4),
            "rashi": lagna_details["rashi"],
            "degrees": lagna_details["degrees"],
            "nakshatra": lagna_details["nakshatra"],
        },
        "planets": placements,
        "coordinates": geo,
        "julian_day": jd,
    }


def _get_current_and_next_dasha(timeline, on_date):
    """Return the active and next Mahadasha for a date."""
    current = None
    upcoming = None
    for idx, d in enumerate(timeline):
        start = datetime.strptime(d["start"], "%Y-%m-%d").date()
        end = datetime.strptime(d["end"], "%Y-%m-%d").date()
        if start <= on_date <= end:
            current = d
            if idx + 1 < len(timeline):
                upcoming = timeline[idx + 1]
            break
    if current is None and timeline:
        current = timeline[0]
        upcoming = timeline[1] if len(timeline) > 1 else None
    return current, upcoming


def build_chart_features(year, month, day, hour, minute, city_name="bengaluru"):
    """Build unified chart features using all local rule modules."""
    time_data = convert_ist_to_utc(year, month, day, hour, minute)
    core = _compute_chart_core(
        time_data["year"], time_data["month"], time_data["day"], time_data["hour_utc"], city_name
    )

    lagna_rashi = core["lagna"]["rashi"]
    house_lords = get_house_lords(lagna_rashi)

    planet_rashis = {planet: data["rashi"] for planet, data in core["planets"].items()}
    dignity_tags = apply_tags_to_chart(planet_rashis)

    moon_longitude = core["planets"]["Moon"]["longitude"]
    timeline = calculate_dashas(moon_longitude, year, month, day)
    current_dasha, next_dasha = _get_current_and_next_dasha(timeline, date.today())

    return {
        "birth_input_ist": {
            "year": year,
            "month": month,
            "day": day,
            "hour": hour,
            "minute": minute,
            "city_name": city_name,
        },
        "birth_time_utc": time_data,
        "lagna": core["lagna"],
        "planets": core["planets"],
        "house_lordships": house_lords,
        "planetary_dignities": dignity_tags,
        "dasha_timeline": timeline,
        "active_dasha": current_dasha,
        "next_dasha": next_dasha,
        "coordinates": core["coordinates"],
    }


def generate_full_chart(year, month, day, hour, minute, city_name="bengaluru"):
    """Backward-compatible text formatter over structured chart features."""
    features = build_chart_features(year, month, day, hour, minute, city_name)
    lines = [
        f"Lagna (Ascendant): {features['lagna']['rashi']} at {features['lagna']['degrees']}°",
    ]
    for name, details in features["planets"].items():
        lines.append(f"{name}: {details['rashi']} ({details['degrees']}°) - {details['nakshatra']}")
    return "\n".join(lines)


def generate_chart_facts(year, month, day, hour_utc):
    """Legacy baseline facts from ephemeris (used for eval comparison)."""
    core = _compute_chart_core(year, month, day, hour_utc)
    lines = []
    for name, details in core["planets"].items():
        lines.append(
            f"{name}: {details['rashi']} ({details['degrees']}°) - Nakshatra: {details['nakshatra']}"
        )
    return "\n".join(lines)


def _get_house_lord_for_house(features, house_number):
    return next(
        (planet for planet, houses in features["house_lordships"].items() if house_number in houses),
        "Unknown",
    )


def _render_planet_strengths(features):
    lines = []
    for planet, data in features["planets"].items():
        dignity = features["planetary_dignities"].get(planet, "[NEUTRAL]")
        lines.append(
            f"- {planet}: {data['rashi']} ({data['degrees']}°), Nakshatra {data['nakshatra']}, Dignity {dignity}"
        )
    return "\n".join(lines)


def _render_functional_lords(features):
    lines = []
    for planet, houses in features["house_lordships"].items():
        if houses:
            lines.append(f"- {planet}: houses {houses}")
    return "\n".join(lines)


def _render_dasha_section(features):
    active_dasha = features["active_dasha"] or {}
    next_dasha = features["next_dasha"] or {}
    lines = [
        f"- Active Mahadasha: {active_dasha.get('dasha', 'Unknown')} ({active_dasha.get('start', '?')} to {active_dasha.get('end', '?')})",
        f"- Next Mahadasha: {next_dasha.get('dasha', 'Unknown')} ({next_dasha.get('start', '?')} to {next_dasha.get('end', '?')})",
    ]
    return "\n".join(lines)


def _render_domain_signals(features, label_to_house):
    lines = []
    for label, house_num in label_to_house:
        lines.append(f"- {label}: {_get_house_lord_for_house(features, house_num)}")
    return "\n".join(lines)


def _build_domain_prompt(
    features,
    user_question,
    domain_name,
    summary_label,
    risk_label,
    opportunity_label,
    signal_header,
    signal_house_map,
    prior_context=None,
):
    return (
        f"You are an expert Vedic astrologer focused on {domain_name} prediction.\n"
        "Use only the provided computed data and avoid unsupported claims.\n"
        "Return output in this exact format:\n"
        f"{summary_label}: <3-5 lines>\n"
        "Evidence:\n"
        "- <signal 1>\n"
        "- <signal 2>\n"
        "- <signal 3>\n"
        f"{risk_label}: <short line>\n"
        f"{opportunity_label}: <short line>\n"
        "Confidence: <0-100 integer>\n\n"
        f"{signal_header}:\n"
        + _render_domain_signals(features, signal_house_map)
        + "\n\nPlanetStrengths:\n"
        + _render_planet_strengths(features)
        + "\n\nFunctionalLords:\n"
        + _render_functional_lords(features)
        + "\n\nCurrentDashas:\n"
        + _render_dasha_section(features)
        + "\n\n"
        + format_dasha_timeline(features["dasha_timeline"])
        + (f"\n\nPriorContext:\n{prior_context}" if prior_context else "")
        + f"\n\nQuestion: {user_question}"
    )


def _house_number_from_lagna_and_sign(lagna_rashi, planet_rashi):
    try:
        lagna_idx = RASHIS.index(lagna_rashi)
        planet_idx = RASHIS.index(planet_rashi)
    except ValueError:
        return None
    return ((planet_idx - lagna_idx) % 12) + 1


def _features_to_chart_facts(features):
    chart_facts = {"lagna": features.get("lagna", {}).get("rashi")}
    lagna_rashi = chart_facts.get("lagna")
    dignities = features.get("planetary_dignities", {})
    for planet, data in features.get("planets", {}).items():
        sign = data.get("rashi")
        house = _house_number_from_lagna_and_sign(lagna_rashi, sign) if lagna_rashi and sign else None
        chart_facts[planet] = {
            "dignity": dignities.get(planet, "[NEUTRAL]"),
            "house": house,
            "sign": sign,
        }
    return chart_facts


def _rag_citation_template_labels(intent):
    """Section labels matching build_*_prompt (for CitationRules). Default career if intent is None."""
    if intent is None:
        key = "career"
    else:
        key = (intent or "general").strip().lower() or "general"
    labels = {
        "career": ("CareerSummary", "CareerRisk", "CareerOpportunity"),
        "health": ("HealthSummary", "HealthRisk", "HealthOpportunity"),
        "wealth": ("WealthSummary", "WealthRisk", "WealthOpportunity"),
        "family": ("FamilySummary", "FamilyRisk", "FamilyOpportunity"),
        "general": ("OverallSummary", "OverallRisk", "OverallOpportunity"),
    }
    return labels.get(key, labels["general"])


def _render_rag_block(chunks, max_tokens, intent=None):
    used_tokens = 0
    lines = ["ClassicalReferences:"]
    allowed_refs = set()
    included = []
    for chunk in chunks:
        text = (chunk.text or "").strip()
        if not text:
            continue
        token_count = cfg.estimate_tokens(text)
        if included and used_tokens + token_count > max_tokens:
            break
        used_tokens += token_count
        included.append(chunk)
        allowed_refs.add(chunk.ref_id)
        lines.append(f"[ref:{chunk.ref_id}]: {text}")

    summary_l, risk_l, opp_l = _rag_citation_template_labels(intent)
    template_hint = f"{summary_l}/Evidence/{risk_l}/{opp_l}/Confidence"
    allowed_list = ", ".join(f"[ref:{ref_id}]" for ref_id in sorted(allowed_refs))
    lines.extend(
        [
            "",
            "CitationRules:",
            f"- Keep the exact response template unchanged ({template_hint}).",
            "- Every Evidence bullet MUST end with at least one [ref:...] tag from ClassicalReferences.",
            "- Include at least 2 Evidence bullets that each cite a reference.",
            "- Use ONLY the [ref:...] tags listed above. Do NOT invent any [ref:...] tag or verse.",
            "- If a claim cannot be supported by the listed refs, omit that claim.",
            "- Citation format example: - Saturn in the 10th may delay rise but supports perseverance [ref:bphs-ch23-v11]",
            f"- AllowedRefTags: {allowed_list}",
        ]
    )
    return "\n".join(lines), allowed_refs, included


def append_classical_references_block(base_prompt, chunks, intent):
    """Insert ClassicalReferences + CitationRules before the final ``Question:`` (same as PR1 RAG splice).

    Returns ``(enriched_prompt, allowed_refs, included_chunks, rag_active)``.
    If ``chunks`` is empty or token packing yields no refs, returns
    ``(base_prompt, set(), [], False)``.
    """
    resolved_intent = (intent or "general").strip().lower() or "general"
    if not chunks:
        return base_prompt, set(), [], False
    rag_block, allowed_refs, included = _render_rag_block(
        chunks,
        max_tokens=cfg.MAX_CONTEXT_TOKENS_TOTAL,
        intent=resolved_intent,
    )
    if not allowed_refs:
        return base_prompt, set(), [], False
    marker = "\n\nQuestion:"
    if marker in base_prompt:
        prefix, suffix = base_prompt.rsplit(marker, 1)
        enriched_prompt = f"{prefix}\n\n{rag_block}{marker}{suffix}"
    else:
        enriched_prompt = f"{base_prompt}\n\n{rag_block}"
    return enriched_prompt, allowed_refs, included, True


def _strip_unknown_refs(text, allowed_refs):
    allowed = set(allowed_refs or [])
    dropped = []

    if not text:
        return text, dropped
    if not allowed:
        stripped, dropped = REF_TAG_RE.subn("", text)
        return stripped, ["*"] * dropped if dropped else []

    def _replace(match):
        tag = match.group(1)
        if tag in allowed:
            return match.group(0)
        dropped.append(tag)
        return ""

    cleaned = REF_TAG_RE.sub(_replace, text)
    return cleaned, dropped


def build_rag_enriched_prompt(features, user_question, intent, prior_context=None):
    resolved_intent = (intent or "general").strip().lower() or "general"
    base_prompt = build_prompt_for_intent(
        features, user_question, resolved_intent, prior_context=prior_context
    )
    chart_facts = _features_to_chart_facts(features)

    try:
        retrieved = rag_search.search(
            question=user_question,
            intent=resolved_intent,
            chart_facts=chart_facts,
            top_k=cfg.RERANK_TOP_K,
        )
    except Exception as exc:
        print(f"[rag] retrieval failed: {exc}", flush=True)
        return {
            "prompt": base_prompt,
            "retrieved": [],
            "allowed_refs": set(),
            "intent": resolved_intent,
            "rag_active": False,
        }

    if not retrieved:
        return {
            "prompt": base_prompt,
            "retrieved": [],
            "allowed_refs": set(),
            "intent": resolved_intent,
            "rag_active": False,
        }

    rag_block, allowed_refs, included = _render_rag_block(
        retrieved,
        max_tokens=cfg.MAX_CONTEXT_TOKENS_TOTAL,
        intent=resolved_intent,
    )
    if not allowed_refs:
        return {
            "prompt": base_prompt,
            "retrieved": [],
            "allowed_refs": set(),
            "intent": resolved_intent,
            "rag_active": False,
        }

    marker = "\n\nQuestion:"
    if marker in base_prompt:
        prefix, suffix = base_prompt.rsplit(marker, 1)
        enriched_prompt = f"{prefix}\n\n{rag_block}{marker}{suffix}"
    else:
        enriched_prompt = f"{base_prompt}\n\n{rag_block}"

    return {
        "prompt": enriched_prompt,
        "retrieved": included,
        "allowed_refs": allowed_refs,
        "intent": resolved_intent,
        "rag_active": True,
    }


def build_career_prompt(features, user_question, prior_context=None):
    """Assemble deterministic, career-focused prompt sections."""
    return _build_domain_prompt(
        features=features,
        user_question=user_question,
        domain_name="CAREER",
        summary_label="CareerSummary",
        risk_label="CareerRisk",
        opportunity_label="CareerOpportunity",
        signal_header="CareerSignals",
        signal_house_map=[
            ("10th house lord", 10),
            ("6th house lord", 6),
            ("2nd house lord", 2),
            ("11th house lord", 11),
        ],
        prior_context=prior_context,
    )


def build_health_prompt(features, user_question, prior_context=None):
    return _build_domain_prompt(
        features=features,
        user_question=user_question,
        domain_name="HEALTH",
        summary_label="HealthSummary",
        risk_label="HealthRisk",
        opportunity_label="HealthOpportunity",
        signal_header="HealthSignals",
        signal_house_map=[
            ("1st house lord", 1),
            ("6th house lord", 6),
            ("8th house lord", 8),
            ("12th house lord", 12),
        ],
        prior_context=prior_context,
    )


def build_wealth_prompt(features, user_question, prior_context=None):
    return _build_domain_prompt(
        features=features,
        user_question=user_question,
        domain_name="WEALTH",
        summary_label="WealthSummary",
        risk_label="WealthRisk",
        opportunity_label="WealthOpportunity",
        signal_header="WealthSignals",
        signal_house_map=[
            ("2nd house lord", 2),
            ("11th house lord", 11),
            ("5th house lord", 5),
            ("9th house lord", 9),
        ],
        prior_context=prior_context,
    )


def build_family_prompt(features, user_question, prior_context=None):
    return _build_domain_prompt(
        features=features,
        user_question=user_question,
        domain_name="FAMILY",
        summary_label="FamilySummary",
        risk_label="FamilyRisk",
        opportunity_label="FamilyOpportunity",
        signal_header="FamilySignals",
        signal_house_map=[
            ("4th house lord", 4),
            ("7th house lord", 7),
            ("2nd house lord", 2),
            ("5th house lord", 5),
        ],
        prior_context=prior_context,
    )


def build_general_prompt(features, user_question, prior_context=None):
    return _build_domain_prompt(
        features=features,
        user_question=user_question,
        domain_name="GENERAL LIFE",
        summary_label="OverallSummary",
        risk_label="OverallRisk",
        opportunity_label="OverallOpportunity",
        signal_header="GeneralSignals",
        signal_house_map=[
            ("1st house lord", 1),
            ("4th house lord", 4),
            ("7th house lord", 7),
            ("10th house lord", 10),
        ],
        prior_context=prior_context,
    )


def build_prompt_for_intent(features, user_question, intent, prior_context=None):
    intent_map = {
        "career": build_career_prompt,
        "health": build_health_prompt,
        "wealth": build_wealth_prompt,
        "family": build_family_prompt,
        "general": build_general_prompt,
    }
    builder = intent_map.get((intent or "").strip().lower(), build_general_prompt)
    return builder(features, user_question, prior_context=prior_context)


def _call_ollama(prompt, stream=False, temperature=0.2, timeout_s=120, model_name=None, num_ctx=None):
    resolved_model, resolved_timeout, resolved_num_ctx = resolve_ollama_config(
        model_name=model_name, timeout_s=timeout_s, num_ctx=num_ctx
    )
    payload = {
        "model": resolved_model,
        "prompt": prompt,
        "stream": stream,
        "options": {"num_ctx": resolved_num_ctx, "temperature": temperature}
    }
    return requests.post(
        OLLAMA_URL,
        json=payload,
        stream=stream,
        timeout=(10, resolved_timeout),
    )


def run_astro_query(prompt, model_name=None, timeout_s=None, allowed_refs=None, num_ctx=None):
    """Run a prompt against local Ollama and stream output."""
    try:
        print("\nAsking local model... (this can take time on first run)\n", flush=True)
        response = _call_ollama(
            prompt,
            stream=True,
            temperature=0.2,
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
            print(
                "\nNo response tokens received from Ollama. "
                "Try a smaller model or restart Ollama.",
                flush=True,
            )
        else:
            print("", flush=True)
            if allowed_refs is not None:
                raw_text = "".join(streamed_parts)
                _, dropped = _strip_unknown_refs(raw_text, allowed_refs)
                dropped_unique = sorted(set(dropped))
                dropped_str = ", ".join(dropped_unique) if dropped_unique else "none"
                print(
                    f"[rag] retrieved={len(set(allowed_refs))} refs, "
                    f"hallucinated={len(dropped_unique)} stripped: {dropped_str}",
                    flush=True,
                )
    except requests.exceptions.Timeout:
        print(
            "\nError: Ollama timed out before sending output. "
            "Model may be too heavy for current hardware.",
            flush=True,
        )
    except requests.exceptions.RequestException as e:
        print(f"\nError calling Ollama API: {e}", flush=True)
    except json.JSONDecodeError as e:
        print(f"\nError decoding Ollama stream: {e}", flush=True)


def query_ollama_once(
    prompt, temperature=0.2, timeout_s=60, model_name=None, allowed_refs=None, num_ctx=None
):
    """Single non-streaming call, useful for evaluation harness."""
    try:
        response = _call_ollama(
            prompt,
            stream=False,
            temperature=temperature,
            timeout_s=timeout_s,
            model_name=model_name,
            num_ctx=num_ctx,
        )
        response.raise_for_status()
        data = response.json()
        text = data.get("response", "").strip()
        if allowed_refs is None:
            return text
        cleaned, _ = _strip_unknown_refs(text, allowed_refs)
        return cleaned.strip()
    except requests.exceptions.RequestException:
        return ""
    except ValueError:
        return ""


def parse_args():
    parser = argparse.ArgumentParser(description="Generate chart features and run a career query on Ollama.")
    parser.add_argument("--year", type=int, default=1996, help="Birth year in IST.")
    parser.add_argument("--month", type=int, default=12, help="Birth month in IST.")
    parser.add_argument("--day", type=int, default=26, help="Birth day in IST.")
    parser.add_argument("--hour", type=int, default=19, help="Birth hour in IST (0-23).")
    parser.add_argument("--minute", type=int, default=0, help="Birth minute in IST (0-59).")
    parser.add_argument("--city", type=str, default="delhi", help="City key from CITY_COORDINATES.")
    parser.add_argument(
        "--question",
        type=str,
        default="What is the professional outlook for this chart?",
        help="Career question for the model.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Ollama model name. Defaults to ASTRO_MODEL_NAME env or engine default.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Read timeout in seconds. Defaults to ASTRO_OLLAMA_TIMEOUT_S env or engine default.",
    )
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=None,
        help="Ollama context window. Defaults to ASTRO_NUM_CTX env or engine default (16384).",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help=f"Use {DEEP_MODEL_NAME} instead of the default {MODEL_NAME}.",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Skip prompt preview before model call.",
    )
    rag_group = parser.add_mutually_exclusive_group()
    rag_group.add_argument(
        "--rag-on",
        action="store_true",
        dest="rag_on",
        help="Enable RAG retrieval and citation-grounded prompt enrichment.",
    )
    rag_group.add_argument(
        "--rag-off",
        action="store_false",
        dest="rag_on",
        help="Disable RAG retrieval and use legacy prompt path.",
    )
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

    features = build_chart_features(
        args.year,
        args.month,
        args.day,
        args.hour,
        args.minute,
        args.city,
    )
    if args.rag_on:
        from intent_router import detect_intent

        detected_intent = detect_intent(
            question=args.question,
            timeout_s=min(45, timeout_s),
        ).get("intent", "general")
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
        print(prompt[:1200] + "\n...\n")
        if args.rag_on:
            print(f"[rag] prompt preview includes refs={len(allowed_refs)}\n", flush=True)

    run_astro_query(
        prompt,
        model_name=model_name,
        timeout_s=timeout_s,
        allowed_refs=allowed_refs,
        num_ctx=num_ctx,
    )