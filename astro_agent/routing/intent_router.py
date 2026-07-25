import json
import re

from astro_agent.intents import ROUTER_INTENT_KEYWORDS, SUPPORTED_INTENTS
from astro_agent.llm import config as llm_cfg

INTENT_CLASSIFIER_MODEL = "llama3.2:3b"

# Backward-compatible alias — prefer importing from astro_agent.intents.
INTENT_KEYWORDS = ROUTER_INTENT_KEYWORDS


def _rule_scores(question):
    text = (question or "").lower().strip()
    scores = {}
    for intent, keywords in ROUTER_INTENT_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in text:
                score += 1
        scores[intent] = score
    if ("wife" in text or "spouse" in text) and (
        "12th lord" in text or "twelfth lord" in text or re.search(r"\b12th\b", text)
    ):
        scores["family"] = scores.get("family", 0) + 2
    if "father" in text or "mother" in text or "parents" in text:
        scores["family"] = scores.get("family", 0) + 1
    if "get married" in text or re.search(r"\bmarried\b", text):
        scores["family"] = scores.get("family", 0) + 2
    if "spouse" in text:
        scores["family"] = scores.get("family", 0) + 2
    if "change" in text and "job" in text:
        scores["career"] = scores.get("career", 0) + 2
    if "health" in text and ("concern" in text or "concerns" in text):
        scores["health"] = scores.get("health", 0) + 2
    if "financial" in text:
        scores["wealth"] = scores.get("wealth", 0) + 2
    if "settle abroad" in text or ("abroad" in text and "settle" in text):
        scores["career"] = scores.get("career", 0) + 2
    if "ancestral property" in text or "inherit" in text:
        scores["wealth"] = scores.get("wealth", 0) + 2
    if "business" in text or "own business" in text:
        scores["career"] = scores.get("career", 0) + 2
    if "promotion" in text:
        scores["career"] = scores.get("career", 0) + 2
    if "career" in text and "suit" in text:
        scores["career"] = scores.get("career", 0) + 2
    if "partner" in text and "compatible" in text:
        scores["family"] = scores.get("family", 0) + 2
    if "marriage" in text and "delay" in text:
        scores["family"] = scores.get("family", 0) + 2
    if "recover" in text or "illness" in text:
        scores["health"] = scores.get("health", 0) + 2
    if "stress" in text or "anxiety" in text:
        scores["health"] = scores.get("health", 0) + 2
    if "health" in text and "risk" in text:
        scores["health"] = scores.get("health", 0) + 2
    if "invest" in text and "property" in text:
        scores["wealth"] = scores.get("wealth", 0) + 2
    if "favorable" in text and "period" in text:
        scores["general"] = scores.get("general", 0) + 2
    return scores


def _best_rule_intent(scores):
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_intent, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    total = sum(scores.values())
    confidence = (float(top_score) / float(total)) if total > 0 else 0.0
    clear_winner = top_score >= 2 and (top_score - second_score) >= 1
    return {
        "intent": top_intent if top_score > 0 else "general",
        "score": top_score,
        "confidence": round(confidence, 3),
        "clear_winner": clear_winner,
    }


def _extract_intent_from_text(text):
    if not text:
        return None
    stripped = text.strip()
    try:
        data = json.loads(stripped)
        intent = data.get("intent", "").strip().lower()
        if intent in SUPPORTED_INTENTS:
            return intent
    except (ValueError, TypeError, AttributeError):
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(stripped[start : end + 1])
            intent = data.get("intent", "").strip().lower()
            if intent in SUPPORTED_INTENTS:
                return intent
        except (ValueError, TypeError, AttributeError):
            pass

    lowered = stripped.lower()
    for intent in SUPPORTED_INTENTS:
        if f'"{intent}"' in lowered or f"intent: {intent}" in lowered or lowered == intent:
            return intent
    return None


def _classify_intent_with_llm(question, timeout_s=None, num_ctx=None):
    from astro_agent.llm.client import query_ollama_once  # lazy to avoid circular import

    if timeout_s is None:
        timeout_s = llm_cfg.INTENT_CLASSIFIER_TIMEOUT_S
    classifier_prompt = (
        "You classify user astrology questions into one intent.\n"
        "Allowed intents: career, health, wealth, family, general.\n"
        "Rules:\n"
        "- Return ONLY strict JSON.\n"
        '- Format: {"intent":"<one_of_allowed>"}\n'
        "- Pick one best intent even if question touches multiple topics.\n\n"
        f"Question: {question}"
    )
    text = query_ollama_once(
        classifier_prompt,
        temperature=llm_cfg.INTENT_CLASSIFIER_TEMPERATURE,
        timeout_s=timeout_s,
        model_name=INTENT_CLASSIFIER_MODEL,
        num_ctx=num_ctx or llm_cfg.INTENT_CLASSIFIER_NUM_CTX,
    )
    return _extract_intent_from_text(text)


def detect_intent(question, model_name=None, timeout_s=None, num_ctx=None):
    """Hybrid intent detection: rules first, LLM fallback on ambiguity."""
    if timeout_s is None:
        timeout_s = llm_cfg.INTENT_CLASSIFIER_TIMEOUT_S
    scores = _rule_scores(question)
    best = _best_rule_intent(scores)
    if best["clear_winner"]:
        return {
            "intent": best["intent"],
            "method": "rules",
            "confidence": best["confidence"],
            "rule_scores": scores,
        }

    llm_intent = _classify_intent_with_llm(question=question, timeout_s=timeout_s, num_ctx=num_ctx)
    if llm_intent in SUPPORTED_INTENTS:
        return {
            "intent": llm_intent,
            "method": "llm_fallback",
            "confidence": best["confidence"],
            "rule_scores": scores,
        }

    fallback_intent = best["intent"] if best["intent"] in SUPPORTED_INTENTS else "general"
    return {
        "intent": fallback_intent or "general",
        "method": "rules_fallback",
        "confidence": best["confidence"],
        "rule_scores": scores,
    }
