"""Central configuration for the RAG pipeline (Phase 4 v0).

Single source of truth for embedding endpoint, Chroma settings, chunking
targets, reranker weights, and the entity/intent regex banks used at
ingest time. Everything tunable lives here so evaluate_rag.py can sweep
weights without touching pipeline code.
"""

import re

OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
KEEP_ALIVE = 0
EMBED_TIMEOUT_S = 60

CHROMA_PATH = "chroma_db"
CHROMA_COLLECTION = "vedic_corpus"

CHUNK_TARGET_TOKENS = 400
CHUNK_OVERLAP_TOKENS = 50
CHUNK_MAX_TOKENS = 600
# Verse (or chapter) bodies over this token estimate are split at ingest into
# multiple Chroma rows sharing the same ref_id (see knowledge_builder).
MAX_CONTEXT_TOKENS_TOTAL = 1200

ENTITY_WEIGHT = 0.12
ENTITY_MATCH_CAP = 3
# Small bonus for entity overlaps beyond ENTITY_MATCH_CAP (capped), so chunks
# that match more query entities can edge out similar-density neighbors.
ENTITY_TAIL_WEIGHT = 0.03
ENTITY_TAIL_MAX = 3
INTENT_WEIGHT = 0.08
# Favor dense+RRF ordering after ref_id dedupe so full-book noise (e.g. broad
# "effects" chapters) does not swamp the correct house-specific verse.
PRE_RERANK_WEIGHT = 0.18
LENGTH_PENALTY_PER_100 = 0.10
LENGTH_PENALTY_THRESHOLD = 500

DENSE_TOP_K = 10
RERANK_TOP_K = 3
SILVER_TOP_K = 5

# Hybrid dense + BM25 (RRF). Corpus is small; BM25 runs over filtered `get()`.
HYBRID_BM25_ENABLED = True
RRF_K = 60.0
# High dense weight keeps pre-rerank order near pure dense (good heuristic_delta) while
# BM25 still nudges scores for lexical gaps and surfaces extra ids at the tail.
RRF_WEIGHT_DENSE = 12.0
RRF_WEIGHT_SPARSE = 1.0
# Minimum cosine-like similarity for BM25-only hits before rerank (dense is ~0–1).
BM25_SIMILARITY_FLOOR = 0.05

SUPPORTED_INTENTS = ("career", "health", "wealth", "family", "general")

# Sharma English Vol.1: "Effects of the Nth House" chapter numbers in metadata.
# Used at rerank to prefer the house-specific chapter when the question or chart
# references that house (reduces cross-chapter competition after full-book ingest).
HOUSE_EFFECTS_CHAPTER = {
    1: 14,
    2: 15,
    3: 16,
    4: 17,
    5: 18,
    6: 19,
    7: 20,
    8: 21,
    9: 22,
    10: 23,
    11: 24,
    12: 25,
}
CHAPTER_HINT_WEIGHT = 0.14
# BM25-only rows use score/max(score) as a pseudo-similarity; without a cap it
# can hit 1.0 and dominate rerank over real cosine matches.
BM25_SIMILARITY_CAP = 0.88
# Question mentions Navamsa/Navamsha and chunk text aligns (exact gold for some Ch.23 cases).
NAVAMSA_ALIGN_WEIGHT = 0.16


def estimate_tokens(text):
    """Cheap token estimate without tiktoken: ~4 chars per token."""
    if not text:
        return 0
    return max(1, len(text) // 4)


_PLANET_TERMS = [
    "Sun", "Moon", "Mars", "Mercury", "Jupiter",
    "Venus", "Saturn", "Rahu", "Ketu",
]

_SIGN_TERMS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

_DIGNITY_TERMS = [
    "exalted", "exaltation", "debilitated", "debilitation",
    "own sign", "own house", "own navamsa", "own navamamsha",
    "combust", "combustion", "retrograde",
    "friendly", "enemy", "neutral",
]

_ASPECT_TERMS = ["aspect", "aspected", "conjunct", "conjunction", "conjoined"]


def _house_pattern():
    ords = "1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th|11th|12th"
    return re.compile(rf"\b({ords})\s+(?:House|house|Bhava|bhava)\b")


def _lord_pattern():
    ords = "1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th|11th|12th"
    return re.compile(rf"\b({ords})\s+Lord\b", re.IGNORECASE)


def _ascendant_lord_pattern():
    return re.compile(r"\bAscendant\s+Lord\b", re.IGNORECASE)


def _lagna_pattern():
    return re.compile(r"\b(Lagna|Ascendant)\b")


_HOUSE_RE = _house_pattern()
_LORD_RE = _lord_pattern()
_ASC_LORD_RE = _ascendant_lord_pattern()
_LAGNA_RE = _lagna_pattern()

_PLANET_RE = re.compile(
    r"\b(" + "|".join(_PLANET_TERMS) + r")\b"
)
_SIGN_RE = re.compile(
    r"\b(" + "|".join(_SIGN_TERMS) + r")\b"
)
_DIGNITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in _DIGNITY_TERMS) + r")\b",
    re.IGNORECASE,
)
_ASPECT_RE = re.compile(
    r"\b(" + "|".join(_ASPECT_TERMS) + r")\b",
    re.IGNORECASE,
)


def extract_entities(text):
    """Return canonical, deduped entity tokens for a chunk.

    Output uses underscores so the |...| delimiter scheme in Chroma
    metadata stays unambiguous (no whitespace inside tokens).
    """
    if not text:
        return []
    found = set()

    for m in _PLANET_RE.finditer(text):
        found.add(m.group(1))

    for m in _SIGN_RE.finditer(text):
        found.add(m.group(1))

    for m in _HOUSE_RE.finditer(text):
        found.add(f"{m.group(1)}_house")

    for m in _LORD_RE.finditer(text):
        found.add(f"{m.group(1).lower()}_lord")

    if _ASC_LORD_RE.search(text):
        found.add("ascendant_lord")

    if _LAGNA_RE.search(text):
        found.add("lagna")

    for m in _DIGNITY_RE.finditer(text):
        token = m.group(1).lower().replace(" ", "_")
        found.add(token)

    for m in _ASPECT_RE.finditer(text):
        found.add(m.group(1).lower())

    return sorted(found)


INTENT_KEYWORDS = {
    "career": [
        "career", "profession", "professional", "work", "works", "employment",
        "occupation", "livelihood", "deed", "deeds", "duties", "duty",
        "karma", "rajya", "authority", "position", "office",
        "business", "trade", "governmental", "royal patronage",
        "actions", "action",
    ],
    "wealth": [
        "wealth", "wealthy", "money", "finance", "financial", "income",
        "gain", "gains", "robes", "ornaments", "precious", "prosperity",
        "affluence", "dhana", "fortune", "fortunes", "rich",
    ],
    "health": [
        "health", "disease", "diseases", "illness", "ulcer", "bruises",
        "leprosy", "longevity", "long life", "lifespan", "ayur", "fear",
        "ailment", "ailments", "sick", "8th lord", "8th house", "eighth house",
        "kendra", "afflicted",
    ],
    "family": [
        "family", "marriage", "spouse", "wife", "husband", "children",
        "child", "putra", "parent", "father", "mother", "brother",
        "sister", "kin", "kindred", "domestic",
    ],
    "general": [
        "fame", "famous", "name", "honour", "honor", "happiness",
        "nature", "character", "personality", "life", "outlook",
    ],
}


def _compile_intent_regex(words):
    parts = sorted({re.escape(w) for w in words}, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(parts) + r")\b", re.IGNORECASE)


_INTENT_RE = {
    intent: _compile_intent_regex(words)
    for intent, words in INTENT_KEYWORDS.items()
}


def detect_intent_tags(text):
    """Boolean fan-out: which intents apply to this chunk.

    Returns a dict with `intent_<name>` keys (one per supported intent).
    Multiple intents can be true. `intent_general` is a permissive
    catch-all that is also marked true if any other intent fires, so
    queries with intent='general' can retrieve from the full corpus.
    """
    flags = {f"intent_{name}": False for name in SUPPORTED_INTENTS}
    if not text:
        return flags

    any_specific = False
    for intent, regex in _INTENT_RE.items():
        if intent == "general":
            continue
        if regex.search(text):
            flags[f"intent_{intent}"] = True
            any_specific = True

    general_regex = _INTENT_RE["general"]
    if general_regex.search(text) or any_specific:
        flags["intent_general"] = True

    return flags
