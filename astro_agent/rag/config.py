"""Central configuration for the RAG pipeline (Phase 4 v0).

Single source of truth for embedding endpoint, Chroma settings, chunking
targets, reranker weights, and the entity/intent regex banks used at
ingest time. Everything tunable lives here so evaluate_rag.py can sweep
weights without touching pipeline code.
"""

import os
import re

from astro_agent.intents import RAG_INTENT_KEYWORDS, SUPPORTED_INTENTS
from astro_agent.llm.config import OLLAMA_EMBED_URL as _LLM_EMBED_URL


def _env_bool(key, default=False):
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


OLLAMA_EMBED_URL = _LLM_EMBED_URL
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
KEEP_ALIVE = 0
EMBED_TIMEOUT_S = 60

CHROMA_PATH = "chroma_db"
CHROMA_COLLECTION = "vedic_corpus"

# --- Qdrant (local/embedded mode) ---
# Added alongside CHROMA_PATH/CHROMA_COLLECTION during migration; the
# Chroma constants are removed once evaluate_rag.py confirms parity
# (see docs/superpowers/plans/2026-08-16-rag-qdrant-migration.md, Task 11).
QDRANT_PATH = "qdrant_db"
QDRANT_COLLECTION = "vedic_corpus"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"
SPARSE_MODEL_NAME = "Qdrant/bm25"

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

DENSE_TOP_K = 15
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
# Neutral mid-score when min-max normalizing a flat score list (avoids div-by-zero).
NEUTRAL_RERANK_SCORE = 0.5

# Re-exported from astro_agent.intents for backward compatibility.
# SUPPORTED_INTENTS imported above.

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
# Extra bonus when a health query asks about 8th lord in 6th house AND the chunk
# contains both 8th_lord and 6th_house entities (targets bphs-ch19-v20-22 specifically
# over adjacent ch19 verses that lack the 8th lord element).
HEALTH_8TH_6TH_COMBO_BONUS = 0.08

# Multi-book corpus support (Phase: corpus expansion). Each book id maps to a
# short citation prefix used in [ref:...] tags. Extend when ingesting new texts.
BOOK_CITATION_PREFIX = {
    "bphs": "bphs",
    "phaladeepika": "phaladeepika",
    "lal_kitab": "lalkitab",
    "muhurta_chintamani": "muhurta",
    "saravali": "saravali",
}

# Extra entity terms for dosha / remedy / matching (ingest + query expansion).
# Wired into extract_entities via _EXTRA_ENTITY_TERMS below.
DOSHA_REMEDY_ENTITY_TERMS = [
    "manglik",
    "mangal dosha",
    "kuja dosha",
    "sade sati",
    "shani dhaiya",
    "shani sade sati",
    "kaal sarp",
    "kaal sarp yog",
    "kaal sarp dosha",
    "pitru dosha",
    "pitra dosha",
    "guna milan",
    "ashtakoot",
    "nadi dosha",
    "bhakoot",
    "yellow sapphire",
    "pukhraj",
    "ruby",
    "manik",
    "emerald",
    "panna",
    "red coral",
    "moonga",
    "pearl",
    "moti",
    "diamond",
    "heera",
    "rudraksha",
    "puja",
    "havan",
    "yantra",
    "mantra",
    "chant",
    "fasting",
    "donation",
    "charity",
]

# HyDE-lite (Phase 3a) optional query rewrite for retrieval.
# Default is off to avoid extra LLM calls and any production behavior change.
QUERY_REWRITE_ENABLED = False

# Use cusp-based bhava houses in RAG chart_facts (default: whole-sign).
USE_BHAVA_FOR_RAG = _env_bool("ASTRO_USE_BHAVA_FOR_RAG", False)

# Structured JSON output from domain generation (Phase 5b).
STRUCTURED_OUTPUT_ENABLED = _env_bool("ASTRO_STRUCTURED_OUTPUT", False)
QUERY_REWRITE_MODEL = "llama3.2:3b"
QUERY_REWRITE_TIMEOUT_S = 45
QUERY_REWRITE_TEMPERATURE = 0.0
QUERY_REWRITE_NUM_CTX = 4096
# Keep the rewritten query short so it stays an embedding-friendly "query".
QUERY_REWRITE_MAX_CHARS = 220

# Phase 3b: cross-encoder rerank (opt-in). Heuristic rerank remains the fallback
# on load/import failure or empty question text.
CROSS_ENCODER_RERANK_ENABLED = False
if os.environ.get("ASTRO_CROSS_ENCODER_RERANK") is not None:
    CROSS_ENCODER_RERANK_ENABLED = _env_bool("ASTRO_CROSS_ENCODER_RERANK", False)
# Default: ms-marco MiniLM (~80MB class, CPU-friendly). Optional: BAAI/bge-reranker-v2-m3
CROSS_ENCODER_MODEL = os.environ.get(
    "ASTRO_CROSS_ENCODER_MODEL",
    "cross-encoder/ms-marco-MiniLM-L-6-v2",
)
CROSS_ENCODER_BATCH_SIZE = int(os.environ.get("ASTRO_CROSS_ENCODER_BATCH_SIZE", "16"))
CROSS_ENCODER_MAX_LENGTH = int(os.environ.get("ASTRO_CROSS_ENCODER_MAX_LENGTH", "512"))
# When CE is on: weight on min-max normalized CE vs heuristic (1 - weight on heuristic).
# Pure CE (1.0) regressed gold@3 with ms-marco-MiniLM; ~0.15 matches baseline gold/silver
# on local golden eval while still injecting CE signal.
CROSS_ENCODER_HEURISTIC_BLEND = float(os.environ.get("ASTRO_CROSS_ENCODER_HEURISTIC_BLEND", "0.15"))


def estimate_tokens(text):
    """Cheap token estimate without tiktoken: ~4 chars per token."""
    if not text:
        return 0
    return max(1, len(text) // 4)


_PLANET_TERMS = [
    "Sun",
    "Moon",
    "Mars",
    "Mercury",
    "Jupiter",
    "Venus",
    "Saturn",
    "Rahu",
    "Ketu",
]

_SIGN_TERMS = [
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
]

_DIGNITY_TERMS = [
    "exalted",
    "exaltation",
    "debilitated",
    "debilitation",
    "own sign",
    "own house",
    "own navamsa",
    "own navamamsha",
    "combust",
    "combustion",
    "retrograde",
    "friendly",
    "enemy",
    "neutral",
    "strong",
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

_PLANET_RE = re.compile(r"\b(" + "|".join(_PLANET_TERMS) + r")\b")
_SIGN_RE = re.compile(r"\b(" + "|".join(_SIGN_TERMS) + r")\b")
_DIGNITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in _DIGNITY_TERMS) + r")\b",
    re.IGNORECASE,
)
_ASPECT_RE = re.compile(
    r"\b(" + "|".join(_ASPECT_TERMS) + r")\b",
    re.IGNORECASE,
)
_DOSHA_REMEDY_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in sorted(DOSHA_REMEDY_ENTITY_TERMS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

_WORD_ORDINAL_TO_NUM = {
    "first": "1st",
    "second": "2nd",
    "third": "3rd",
    "fourth": "4th",
    "fifth": "5th",
    "sixth": "6th",
    "seventh": "7th",
    "eighth": "8th",
    "ninth": "9th",
    "tenth": "10th",
    "eleventh": "11th",
    "twelfth": "12th",
}
_WORD_ORD_HOUSE_RE = re.compile(
    r"\b(" + "|".join(_WORD_ORDINAL_TO_NUM) + r")\s+(?:House|house|Bhava|bhava)\b",
    re.IGNORECASE,
)
_WORD_ORD_LORD_RE = re.compile(
    r"\b(" + "|".join(_WORD_ORDINAL_TO_NUM) + r")\s+[Ll]ord\b",
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

    for m in _WORD_ORD_HOUSE_RE.finditer(text):
        num = _WORD_ORDINAL_TO_NUM[m.group(1).lower()]
        found.add(f"{num}_house")

    for m in _WORD_ORD_LORD_RE.finditer(text):
        num = _WORD_ORDINAL_TO_NUM[m.group(1).lower()]
        found.add(f"{num}_lord")

    if _ASC_LORD_RE.search(text):
        found.add("ascendant_lord")

    if _LAGNA_RE.search(text):
        found.add("lagna")

    for m in _DIGNITY_RE.finditer(text):
        token = m.group(1).lower().replace(" ", "_")
        found.add(token)

    for m in _ASPECT_RE.finditer(text):
        found.add(m.group(1).lower())

    for m in _DOSHA_REMEDY_RE.finditer(text):
        token = m.group(1).lower().replace(" ", "_")
        found.add(token)

    return sorted(found)


# Backward-compatible alias — prefer RAG_INTENT_KEYWORDS from astro_agent.intents.
INTENT_KEYWORDS = RAG_INTENT_KEYWORDS


def _compile_intent_regex(words):
    parts = sorted({re.escape(w) for w in words}, key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(parts) + r")\b", re.IGNORECASE)


_INTENT_RE = {intent: _compile_intent_regex(words) for intent, words in INTENT_KEYWORDS.items()}


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
