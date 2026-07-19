"""RAG prompt injection and citation stripping."""
import re

from astro_agent.rag import config as cfg
from astro_agent.rag import search as rag_search
from astro_agent.chart.engine import _house_number_from_lagna_and_sign
from astro_agent.llm.prompts.builder import build_prompt_for_intent

REF_TAG_RE = re.compile(r"\[ref:([^\]]+)\]")


def _features_to_chart_facts(features):
    chart_facts = {"lagna": features.get("lagna", {}).get("rashi")}
    lagna_rashi = chart_facts.get("lagna")
    dignities = features.get("planetary_dignities", {})
    use_bhava = getattr(cfg, "USE_BHAVA_FOR_RAG", False)
    bhava_map = features.get("bhava_positions") or {}
    for planet, data in features.get("planets", {}).items():
        sign = data.get("rashi")
        if use_bhava and planet in bhava_map:
            house = bhava_map[planet]
        else:
            house = _house_number_from_lagna_and_sign(lagna_rashi, sign) if lagna_rashi and sign else None
        chart_facts[planet] = {
            "dignity": dignities.get(planet, "[NEUTRAL]"),
            "house": house,
            "sign": sign,
        }
    active_ant = features.get("active_antardasha") or {}
    ant_lord = active_ant.get("dasha")
    if isinstance(ant_lord, str) and ant_lord.strip():
        chart_facts["_antardasha_lord"] = ant_lord.strip()
    return chart_facts


def _rag_citation_template_labels(intent):
    if intent is None:
        key = "career"
    else:
        key = (intent or "general").strip().lower() or "general"
    labels = {
        "career": ("CareerSummary", "CareerRisk", "CareerOpportunity", "CareerRemedies"),
        "health": ("HealthSummary", "HealthRisk", "HealthOpportunity", "HealthRemedies"),
        "wealth": ("WealthSummary", "WealthRisk", "WealthOpportunity", "WealthRemedies"),
        "family": ("FamilySummary", "FamilyRisk", "FamilyOpportunity", "FamilyRemedies"),
        "general": ("OverallSummary", "OverallRisk", "OverallOpportunity", "OverallRemedies"),
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

    summary_l, risk_l, opp_l, remedies_l = _rag_citation_template_labels(intent)
    template_hint = f"{summary_l}/Evidence/{risk_l}/{opp_l}/{remedies_l}/Confidence"
    allowed_list = ", ".join(f"[ref:{ref_id}]" for ref_id in sorted(allowed_refs))
    lines.extend([
        "",
        "CitationRules:",
        f"- Keep the exact response template unchanged ({template_hint}).",
        "- Every Evidence bullet MUST end with at least one [ref:...] tag from ClassicalReferences.",
        "- Include at least 2 Evidence bullets that each cite a reference.",
        "- Use ONLY the [ref:...] tags listed above. Do NOT invent any [ref:...] tag or verse.",
        "- If a claim cannot be supported by the listed refs, omit that claim.",
        "- Citation format example: - Saturn in the 10th may delay rise but supports perseverance [ref:bphs-ch23-v11]",
        f"- AllowedRefTags: {allowed_list}",
    ])
    return "\n".join(lines), allowed_refs, included


def append_classical_references_block(base_prompt, chunks, intent):
    """Insert ClassicalReferences + CitationRules before the final ``Question:``."""
    resolved_intent = (intent or "general").strip().lower() or "general"
    if not chunks:
        return base_prompt, set(), [], False
    rag_block, allowed_refs, included = _render_rag_block(
        chunks, max_tokens=cfg.MAX_CONTEXT_TOKENS_TOTAL, intent=resolved_intent,
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
        retrieved, max_tokens=cfg.MAX_CONTEXT_TOKENS_TOTAL, intent=resolved_intent,
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
