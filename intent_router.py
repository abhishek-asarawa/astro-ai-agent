import json

from astro_engine import query_ollama_once

SUPPORTED_INTENTS = ("career", "health", "wealth", "family", "general")

# Small model for JSON intent only — never use the main generation model here.
INTENT_CLASSIFIER_MODEL = "llama3.2:3b"

INTENT_KEYWORDS = {
    "career": [
        "career",
        "job",
        "profession",
        "work",
        "promotion",
        "growth",
        "role",
        "employment",
        # BPHS-style / 10th-house wording (Ch. 23 etc.); substring matches e.g. "10th Lord"
        "10th lord",
        "tenth lord",
        "10th house",
        "tenth house",
        "10th",
        "tenth",
        "karma yogi",
        "livelihood",
        "fame",
        "occupation",
        "business",
        "vocation",
    ],
    "health": [
        "health",
        "disease",
        "diseases",
        "illness",
        "ailment",
        "ailments",
        "medical",
        "fitness",
        "injury",
        "wellness",
        "recovery",
        "longevity",
        "long life",
        "lifespan",
        "8th lord",
        "8th house",
        "eighth house",
        "kendra",
        "afflicted",
    ],
    "wealth": [
        "wealth", "money", "finance", "income", "salary", "investment", "savings", "property",
    ],
    "family": [
        "family",
        "marriage",
        "spouse",
        "relationship",
        "parents",
        "father",
        "mother",
        "children",
        "home",
        "domestic",
        # BPHS Ch. 22 / 9th-house wording (fortune, dharma, parent from 9th)
        "9th lord",
        "ninth lord",
        "9th house",
        "ninth house",
        "fortunes",
        "pilgrimage",
    ],
    "general": [
        "overall", "general", "life", "future", "outlook", "summary", "holistic",
    ],
}


def _rule_scores(question):
    text = (question or "").lower().strip()
    scores = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in text:
                score += 1
        scores[intent] = score
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

    # Try to parse first JSON object if extra tokens were returned.
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
        if f"\"{intent}\"" in lowered or f"intent: {intent}" in lowered or lowered == intent:
            return intent
    return None


def _classify_intent_with_llm(question, timeout_s=45, num_ctx=None):
    classifier_prompt = (
        "You classify user astrology questions into one intent.\n"
        "Allowed intents: career, health, wealth, family, general.\n"
        "Rules:\n"
        "- Return ONLY strict JSON.\n"
        "- Format: {\"intent\":\"<one_of_allowed>\"}\n"
        "- Pick one best intent even if question touches multiple topics.\n\n"
        f"Question: {question}"
    )
    text = query_ollama_once(
        classifier_prompt,
        temperature=0.0,
        timeout_s=timeout_s,
        model_name=INTENT_CLASSIFIER_MODEL,
        num_ctx=num_ctx or 4096,
    )
    return _extract_intent_from_text(text)


def detect_intent(question, model_name=None, timeout_s=45, num_ctx=None):
    """Hybrid intent detection: rules first, LLM fallback on ambiguity."""
    scores = _rule_scores(question)
    best = _best_rule_intent(scores)
    if best["clear_winner"]:
        return {
            "intent": best["intent"],
            "method": "rules",
            "confidence": best["confidence"],
            "rule_scores": scores,
        }

    llm_intent = _classify_intent_with_llm(
        question=question,
        timeout_s=timeout_s,
        num_ctx=num_ctx,
    )
    if llm_intent in SUPPORTED_INTENTS:
        return {
            "intent": llm_intent,
            "method": "llm_fallback",
            "confidence": best["confidence"],
            "rule_scores": scores,
        }

    # Final fallback guard.
    fallback_intent = best["intent"] if best["intent"] in SUPPORTED_INTENTS else "general"
    return {
        "intent": fallback_intent or "general",
        "method": "rules_fallback",
        "confidence": best["confidence"],
        "rule_scores": scores,
    }
