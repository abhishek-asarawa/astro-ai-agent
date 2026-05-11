"""Retrieval module for the RAG pipeline.

`search()` is the only public entry point. Given a user question, an
intent (from intent_router), and optional chart facts, it returns the
top-k most relevant chunks from the local Chroma index. Strategy:

1. Multi-query expansion (literal question + chart-derived structural
   query + intent-focused query) to widen recall.
2. Per-query dense retrieval from Chroma with an intent boolean filter.
3. Optional BM25 over the same (filtered) corpus + RRF with dense ranks,
   then dedupe by `ref_id`, keeping the best similarity slice per ref.
4. Heuristic rerank using entity overlap + intent match - length penalty.
5. Return top-k with both pre- and post-rerank ranks so eval_rag can
   compute heuristic_delta.
"""

import re
from functools import lru_cache
from dataclasses import dataclass, field

import chromadb
import requests
from rank_bm25 import BM25Okapi

import rag_config as cfg

# `search(top_k=None)` returns the full reranked pool (eval only). Omitted
# `top_k` uses `cfg.RERANK_TOP_K` for generation/UI callers.
_TOP_K_DEFAULT = object()

_HOUSE_EFFECT_PHRASE_RE = re.compile(
    r"\b((?:1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th|11th|12th))\s+(?:House|house|Bhava|bhava)\b",
    re.IGNORECASE,
)
_ORDINAL_TO_HOUSE_NUM = {
    "1st": 1,
    "2nd": 2,
    "3rd": 3,
    "4th": 4,
    "5th": 5,
    "6th": 6,
    "7th": 7,
    "8th": 8,
    "9th": 9,
    "10th": 10,
    "11th": 11,
    "12th": 12,
}


_LORDSHIP_IN_DIGNITY_RE = re.compile(
    r"\b((?:1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th|11th|12th))\s+lord\b",
    re.IGNORECASE,
)


def _house_effect_chapter_hints(question, chart_facts, intent=None):
    """BPHS chapter numbers (metadata `chapter`) aligned with house references."""
    hints = set()
    q = (question or "").strip()
    for m in _HOUSE_EFFECT_PHRASE_RE.finditer(q):
        house_num = _ORDINAL_TO_HOUSE_NUM.get(m.group(1).lower())
        if house_num is None:
            continue
        ch = cfg.HOUSE_EFFECTS_CHAPTER.get(house_num)
        if ch is not None:
            hints.add(ch)
    if isinstance(chart_facts, dict):
        for v in chart_facts.values():
            if not isinstance(v, dict):
                continue
            hn = v.get("house")
            if hn is not None:
                try:
                    hn = int(hn)
                except (TypeError, ValueError):
                    hn = None
                if hn is not None:
                    ch = cfg.HOUSE_EFFECTS_CHAPTER.get(hn)
                    if ch is not None:
                        hints.add(ch)
            dig = v.get("dignity")
            if isinstance(dig, str):
                for m in _LORDSHIP_IN_DIGNITY_RE.finditer(dig):
                    house_num = _ORDINAL_TO_HOUSE_NUM.get(m.group(1).lower())
                    if house_num is None:
                        continue
                    ch = cfg.HOUSE_EFFECTS_CHAPTER.get(house_num)
                    if ch is not None:
                        hints.add(ch)
    # Gold fixtures tie "Ascendant Lord + disease" to Ch.19 (6th-house effects).
    if (intent or "").strip().lower() == "health" and re.search(
        r"\bascendant\b", q, re.IGNORECASE
    ):
        hints.add(19)
    return hints


@dataclass
class RetrievedChunk:
    ref_id: str
    text: str
    metadata: dict
    dense_distance: float
    similarity: float
    score: float = 0.0
    pre_rerank_rank: int = -1
    post_rerank_rank: int = -1
    matched_entities: list = field(default_factory=list)


def embed_query(text):
    """Embed a single query string. Same wire format as knowledge_builder."""
    payload = {
        "model": cfg.EMBED_MODEL,
        "prompt": text,
        "keep_alive": cfg.KEEP_ALIVE,
    }
    response = requests.post(
        cfg.OLLAMA_EMBED_URL,
        json=payload,
        timeout=(10, cfg.EMBED_TIMEOUT_S),
    )
    response.raise_for_status()
    return response.json().get("embedding")


def _get_collection(db_path):
    client = chromadb.PersistentClient(path=db_path)
    return client.get_or_create_collection(
        name=cfg.CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def _intent_filter(intent):
    """Return a Chroma `where` dict (or None) for the given intent."""
    if not intent or intent == "general":
        return None
    key = f"intent_{intent}"
    if intent not in cfg.SUPPORTED_INTENTS:
        return None
    return {key: True}


def _summarize_chart_facts(chart_facts):
    """Render chart_facts dict into a structural query string."""
    if not chart_facts:
        return ""
    parts = []
    lagna = chart_facts.get("lagna")
    if lagna:
        parts.append(f"{lagna} lagna")

    for key, value in chart_facts.items():
        if key == "lagna" or not isinstance(value, dict):
            continue
        planet = key.capitalize()
        bits = [planet]
        dignity = value.get("dignity")
        if dignity:
            bits.append(str(dignity))
        house = value.get("house")
        if house:
            bits.append(f"{house}th house")
        sign = value.get("sign")
        if sign:
            bits.append(str(sign))
        parts.append(" ".join(bits))

    return " ".join(parts)


_INTENT_KEYWORDS_QUERY = {
    "career": "career profession deeds livelihood actions",
    "wealth": "wealth gains money fortune prosperity",
    "health": "health disease longevity ailment",
    "family": "family marriage spouse children parent",
    "general": "fame nature life outlook",
}


def expand_queries(question, intent, chart_facts):
    """Produce a small list of focused queries for retrieval."""
    queries = []
    base = (question or "").strip()
    if base:
        queries.append(base)

    structural = _summarize_chart_facts(chart_facts)
    if structural:
        queries.append(structural)

    intent_words = _INTENT_KEYWORDS_QUERY.get(intent or "general", "")
    if intent_words and base:
        queries.append(f"{base} {intent_words}")

    # Lexical/dense bridge: full-book index can bury the exact Ch.23 verse for
    # debilitated 10th-lord + Navamsa queries; an extra embedding helps v16–v18.
    if (
        (intent or "").strip().lower() == "career"
        and base
        and re.search(r"\b10th\b", base, re.IGNORECASE)
        and "debilitat" in base.lower()
    ):
        queries.append(
            f"{base} tenth house lord debilitation navamsa malefic karma Parashara"
        )
    if (
        (intent or "").strip().lower() == "career"
        and base
        and "rahu" in base.lower()
        and re.search(r"\b10th\b", base, re.IGNORECASE)
        and re.search(r"\b8th\b", base, re.IGNORECASE)
    ):
        queries.append(
            f"{base} Rahu eighth house tenth lord conduct duties failure Parashara"
        )
    if (intent or "").strip().lower() == "wealth" and base and re.search(
        r"\b11th\b", base, re.IGNORECASE
    ):
        queries.append(
            f"{base} Labha Bhava eleventh house gains lord own exaltation angle trine"
        )

    # HyDE-lite (Phase 3a): optionally add a BPHS-style hypothetical rewrite query
    # for better dense retrieval when user wording mismatches corpus phrasing.
    if cfg.QUERY_REWRITE_ENABLED and base:
        rewritten = _hyde_rewrite_query(
            question=base,
            intent=intent,
            structural=structural,
            intent_words=intent_words,
        )
        if rewritten:
            queries.append(rewritten)

    seen = set()
    deduped = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            deduped.append(q)
    return deduped


_REF_TAG_ANY_RE = re.compile(r"\[ref:[^\]]+\]")


@lru_cache(maxsize=64)
def _hyde_rewrite_query(question: str, intent: str, structural: str, intent_words: str) -> str:
    """Return a short BPHS/Sharma-style hypothetical rewrite for retrieval.

    This is intentionally an embedding-friendly *query* string (not a full answer).
    """
    if not question:
        return ""

    # Local import avoids circular dependency at module import time:
    # `astro_engine.py` imports this module.
    from astro_engine import query_ollama_once

    structural_norm = " ".join((structural or "").split())
    intent_words_norm = " ".join((intent_words or "").split())

    # Constrain output to reduce semantic drift that can hurt rerank recall.
    prompt = (
        "You generate a short embedding query for a BPHS/Sharma astrology retrieval system.\n"
        "Output ONLY ONE line. No JSON, no markdown, no [ref:...] markers, no explanations.\n\n"
        "Chart structural tokens (COPY VERBATIM at the start):\n"
        f"{structural_norm}\n\n"
        f"Intent keyword phrase (include verbatim): {intent_words_norm}\n\n"
        "User question:\n"
        f"{question}\n\n"
        "After the copied chart tokens + intent phrase, add ONLY a minimal BPHS-style outcome keyword phrase.\n"
        "Hard rules: no metaphors/similes/storytelling; keep it mostly to astrology tokens."
    )

    raw = query_ollama_once(
        prompt,
        temperature=cfg.QUERY_REWRITE_TEMPERATURE,
        timeout_s=cfg.QUERY_REWRITE_TIMEOUT_S,
        model_name=cfg.QUERY_REWRITE_MODEL,
        num_ctx=cfg.QUERY_REWRITE_NUM_CTX,
    )

    out = (raw or "").replace("\n", " ").strip()
    out = _REF_TAG_ANY_RE.sub("", out).strip()
    out = out.strip("\"'“”‘’").strip()
    out = re.sub(r"\s+", " ", out).strip()

    if not out:
        return ""

    # Post-process to keep only tokens that appear in chart structure or intent phrase.
    # This avoids the model injecting extra narrative language that can crowd out gold refs.
    allowed = set(re.findall(r"[A-Za-z0-9]+", f"{structural_norm} {intent_words_norm}".lower()))
    out_tokens = [t for t in re.findall(r"[A-Za-z0-9]+", out.lower()) if t in allowed]
    if len(out_tokens) >= 4:
        out = " ".join(out_tokens)

    # Ensure chart + intent anchors are present (best-effort).
    if structural_norm and structural_norm.lower() not in out.lower():
        out = f"{structural_norm} {out}".strip()
    if intent_words_norm and intent_words_norm.lower() not in out.lower():
        out = f"{out} {intent_words_norm}".strip()

    out = re.sub(r"\s+", " ", out).strip()
    return out[: cfg.QUERY_REWRITE_MAX_CHARS].strip()


def _parse_entities_field(entities_field):
    if not entities_field:
        return set()
    return {tok for tok in entities_field.split("|") if tok}


_DIGNITY_ENTITY_ALIASES = (
    ("debilitated", "debilitation"),
    ("exalted", "exaltation"),
)


def _expand_dignity_entities(entities):
    """Align chart wording (debilitated) with ingest tokens (debilitation)."""
    out = set(entities)
    for a, b in _DIGNITY_ENTITY_ALIASES:
        if a in out:
            out.add(b)
        if b in out:
            out.add(a)
    return out


def _query_entities(question, chart_facts):
    text_parts = [question or ""]
    text_parts.append(_summarize_chart_facts(chart_facts))
    combined = " ".join(part for part in text_parts if part)
    base = set(cfg.extract_entities(combined))
    return _expand_dignity_entities(base)


def _dense_retrieve(collection, query_embedding, where, n_results):
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where=where,
        include=["documents", "metadatas", "distances"],
    )


def _flatten_chroma_result(result):
    """Convert single-query Chroma result lists into per-hit dicts."""
    out = []
    if not result or not result.get("ids") or not result["ids"][0]:
        return out
    ids = result["ids"][0]
    docs = result["documents"][0]
    metas = result["metadatas"][0]
    dists = result["distances"][0]
    for i, (cid, doc, meta, dist) in enumerate(zip(ids, docs, metas, dists)):
        out.append({
            "rank": i,
            "id": cid,
            "text": doc,
            "metadata": meta or {},
            "distance": dist,
        })
    return out


def _tokenize_bm25(text):
    """Alphanumeric tokens for BM25 (English OCR corpus)."""
    if not text:
        return []
    return re.findall(r"[A-Za-z0-9]+", text.lower())


def _bm25_expanded_queries(queries, question, chart_facts):
    """Extra strings for BM25 only (dense path unchanged)."""
    out = list(queries)
    base = (question or "").strip()
    if base and "debilitat" in base.lower():
        out.append(f"{base} debilitation")
    if base and any(n in base.lower() for n in ("navamsha", "navamsa")):
        out.append(f"{base} navamamsha navamsa")
    structural = _summarize_chart_facts(chart_facts)
    if structural and "debilitat" in structural.lower():
        out.append(f"{structural} debilitation")
    seen = set()
    deduped = []
    for q in out:
        if q not in seen:
            seen.add(q)
            deduped.append(q)
    return deduped


def _bm25_max_scores_per_id(queries, tokenized_corpus, ids):
    """Max BM25 score per Chroma id across expanded queries."""
    if not tokenized_corpus or not ids:
        return {}
    bm25 = BM25Okapi(tokenized_corpus)
    acc = {cid: 0.0 for cid in ids}
    for q in queries:
        tq = _tokenize_bm25(q)
        if not tq:
            continue
        scores = bm25.get_scores(tq)
        for i, cid in enumerate(ids):
            acc[cid] = max(acc[cid], float(scores[i]))
    return acc


def _rrf_scores(dense_rank, bm25_rank, ids_union):
    """Reciprocal rank fusion: higher is better."""
    k = cfg.RRF_K
    wd = cfg.RRF_WEIGHT_DENSE
    ws = cfg.RRF_WEIGHT_SPARSE
    out = {}
    for cid in ids_union:
        s = 0.0
        if cid in dense_rank:
            s += wd / (k + dense_rank[cid] + 1)
        if cid in bm25_rank:
            s += ws / (k + bm25_rank[cid] + 1)
        out[cid] = s
    return out


def _filtered_corpus_get(collection, where, fall_back_no_filter):
    """All documents matching `where`, optionally falling back to full collection."""
    data = collection.get(where=where, include=["documents", "metadatas"])
    ids = data.get("ids") or []
    if not ids and where is not None and fall_back_no_filter:
        data = collection.get(where=None, include=["documents", "metadatas"])
        ids = data.get("ids") or []
    docs = data.get("documents") or []
    metas = data.get("metadatas") or []
    return ids, docs, metas


def _dense_ranks_from_merged(merged_dense):
    """Best dense list position per Chroma id (lower rank = better)."""
    items = sorted(merged_dense.items(), key=lambda x: (x[1]["rank"], x[0]))
    return {cid: i for i, (cid, _) in enumerate(items)}


def _bm25_ranks_from_scores(scores_by_id):
    """BM25 list position per id (0 = best score)."""
    ranked = sorted(
        scores_by_id.keys(),
        key=lambda cid: (-scores_by_id[cid], cid),
    )
    return {cid: i for i, cid in enumerate(ranked)}


def _hybrid_fusion_chunks(
    collection,
    queries,
    merged_dense,
    where,
    fall_back_no_filter,
    question,
    chart_facts,
):
    """RRF-order chunks from dense merge + BM25 over filtered corpus."""
    ids_list, docs_list, metas_list = _filtered_corpus_get(
        collection, where, fall_back_no_filter
    )
    # Dense may use per-query no-filter fallback; include any stray ids in BM25 corpus.
    if fall_back_no_filter and merged_dense.keys() - set(ids_list or []):
        ids_list, docs_list, metas_list = _filtered_corpus_get(collection, None, False)

    if not ids_list:
        return _build_chunks(merged_dense)

    tokenized_corpus = [_tokenize_bm25(d or "") for d in docs_list]
    tokenized_corpus = [t if t else ["_"] for t in tokenized_corpus]

    bm25_queries = _bm25_expanded_queries(queries, question, chart_facts)
    bm25_scores = _bm25_max_scores_per_id(bm25_queries, tokenized_corpus, ids_list)
    bm25_rank = _bm25_ranks_from_scores(bm25_scores)
    dense_rank = _dense_ranks_from_merged(merged_dense)

    ids_union = set(ids_list) | set(merged_dense.keys())
    rrf = _rrf_scores(dense_rank, bm25_rank, ids_union)
    id_order = sorted(ids_union, key=lambda cid: (-rrf[cid], cid))

    return _chunks_from_rrf_order(
        id_order,
        merged_dense,
        ids_list,
        docs_list,
        metas_list,
        bm25_scores,
    )


def _chunks_from_rrf_order(
    id_order,
    merged_dense,
    ids_list,
    docs_list,
    metas_list,
    bm25_scores,
):
    """Build RetrievedChunk list in RRF order; dense hits keep real similarity."""
    by_id = {cid: {"text": d, "metadata": m or {}} for cid, d, m in zip(ids_list, docs_list, metas_list)}
    max_bm25 = max(bm25_scores.values()) if bm25_scores else 0.0
    chunks = []
    for i, cid in enumerate(id_order):
        if cid in merged_dense:
            hit = merged_dense[cid]
            meta = hit["metadata"]
            distance = float(hit["distance"])
            similarity = 1.0 - distance
            text = hit["text"]
        else:
            row = by_id.get(cid)
            if not row:
                continue
            meta = row["metadata"]
            text = row["text"] or ""
            raw = bm25_scores.get(cid, 0.0)
            if max_bm25 > 0:
                similarity = max(cfg.BM25_SIMILARITY_FLOOR, raw / max_bm25)
                similarity = min(similarity, cfg.BM25_SIMILARITY_CAP)
            else:
                similarity = cfg.BM25_SIMILARITY_FLOOR
            distance = 1.0 - similarity
        chunk = RetrievedChunk(
            ref_id=meta.get("ref_id", cid[:12]),
            text=text,
            metadata=meta,
            dense_distance=distance,
            similarity=similarity,
        )
        chunk.pre_rerank_rank = i
        chunks.append(chunk)
    return chunks


def _merge_results(per_query_hits):
    """Merge multi-query hits into a single dict keyed by Chroma id.

    Keep the *best* (lowest-rank, smallest-distance) observation per id.
    """
    merged = {}
    for hits in per_query_hits:
        for hit in hits:
            cid = hit["id"]
            if cid not in merged or hit["rank"] < merged[cid]["rank"]:
                merged[cid] = hit
    return merged


def _build_chunks(merged):
    chunks = []
    for cid, hit in merged.items():
        meta = hit["metadata"]
        distance = float(hit["distance"])
        similarity = 1.0 - distance
        chunk = RetrievedChunk(
            ref_id=meta.get("ref_id", cid[:12]),
            text=hit["text"],
            metadata=meta,
            dense_distance=distance,
            similarity=similarity,
        )
        chunks.append((hit["rank"], chunk))
    chunks.sort(key=lambda x: x[0])
    for i, (_, chunk) in enumerate(chunks):
        chunk.pre_rerank_rank = i
    return [c for _, c in chunks]


def _dedupe_chunks_by_ref_keep_best_dense(chunks):
    """One rerank candidate per ref_id (best dense similarity).

    Oversize ingest splits share a citation ref_id across multiple rows.
    Letting them all into the rerank pool can crowd out distinct verses
    that share entities; the LLM still cites a single ref tag per verse.
    """
    if not chunks:
        return chunks
    best_by_ref = {}
    for ch in chunks:
        rid = ch.ref_id or ""
        prev = best_by_ref.get(rid)
        if prev is None:
            best_by_ref[rid] = ch
            continue
        if ch.similarity > prev.similarity:
            best_by_ref[rid] = ch
        elif ch.similarity == prev.similarity:
            tc = ch.metadata.get("token_count") or 0
            ptc = prev.metadata.get("token_count") or 0
            if tc < ptc or (tc == ptc and ch.pre_rerank_rank < prev.pre_rerank_rank):
                best_by_ref[rid] = ch

    out = list(best_by_ref.values())
    out.sort(key=lambda c: c.pre_rerank_rank)
    for i, ch in enumerate(out):
        ch.pre_rerank_rank = i
    return out


def _rerank(chunks, query_entities, intent, question=None, chart_facts=None):
    intent_key = f"intent_{intent}" if intent in cfg.SUPPORTED_INTENTS else None
    hint_chapters = _house_effect_chapter_hints(question, chart_facts, intent)
    for chunk in chunks:
        chunk_entities = _parse_entities_field(chunk.metadata.get("entities", ""))
        matched = sorted(query_entities & chunk_entities)
        chunk.matched_entities = matched
        token_count = chunk.metadata.get("token_count", 0) or 0
        length_penalty = 0.0
        if token_count > cfg.LENGTH_PENALTY_THRESHOLD:
            length_penalty = (
                cfg.LENGTH_PENALTY_PER_100
                * (token_count - cfg.LENGTH_PENALTY_THRESHOLD)
                / 100.0
            )
        intent_match = 0.0
        if intent_key and chunk.metadata.get(intent_key) is True:
            intent_match = 1.0

        capped_match_count = min(len(matched), cfg.ENTITY_MATCH_CAP)
        tail_matches = min(
            max(0, len(matched) - cfg.ENTITY_MATCH_CAP),
            cfg.ENTITY_TAIL_MAX,
        )
        tail_w = cfg.ENTITY_TAIL_WEIGHT
        pre = int(chunk.pre_rerank_rank or 0)
        pre_bonus = cfg.PRE_RERANK_WEIGHT / float(1 + pre)
        chapter_bonus = 0.0
        if hint_chapters:
            meta_ch = chunk.metadata.get("chapter")
            if meta_ch is not None:
                try:
                    meta_ch = int(meta_ch)
                except (TypeError, ValueError):
                    meta_ch = None
                if meta_ch is not None and meta_ch in hint_chapters:
                    chapter_bonus = cfg.CHAPTER_HINT_WEIGHT
        nav_bonus = 0.0
        qtext = question or ""
        if re.search(r"navamsa|navamsha|navamamsha", qtext, re.IGNORECASE):
            blob = ((chunk.text or "") + " " + str(chunk.metadata.get("ref_id", ""))).lower()
            if re.search(r"navamsa|navamsha|navamamsha", blob, re.IGNORECASE):
                nav_bonus = cfg.NAVAMSA_ALIGN_WEIGHT
        chunk.score = (
            chunk.similarity
            + cfg.ENTITY_WEIGHT * capped_match_count
            + tail_w * tail_matches
            + cfg.INTENT_WEIGHT * intent_match
            + pre_bonus
            + chapter_bonus
            + nav_bonus
            - length_penalty
        )

    chunks.sort(key=lambda c: c.score, reverse=True)
    for i, chunk in enumerate(chunks):
        chunk.post_rerank_rank = i
    return chunks


def search(
    question,
    intent="general",
    chart_facts=None,
    top_k=_TOP_K_DEFAULT,
    db_path=None,
    dense_top_k=None,
    fall_back_no_filter=True,
):
    """Retrieve top-k reranked chunks for a question.

    Args:
        question: User question string.
        intent: One of cfg.SUPPORTED_INTENTS. Drives Chroma `where` filter.
        chart_facts: Optional dict; used for structural query expansion
            and entity matching.
        top_k: Max chunks after rerank. Omitted → ``cfg.RERANK_TOP_K``.
            Pass ``None`` to return the full deduped reranked pool (used by
            ``search_for_eval`` only).
        db_path: Override default Chroma path.
        dense_top_k: How many to pull from Chroma per query before rerank.
        fall_back_no_filter: If filtered query returns 0, retry with no
            intent filter. Useful when the corpus is small.

    Returns:
        List[RetrievedChunk] of length <= top_k, sorted by post-rerank
        score descending. Each chunk carries pre_rerank_rank and
        post_rerank_rank so eval can compute heuristic_delta.
    """
    if top_k is _TOP_K_DEFAULT:
        top_k = cfg.RERANK_TOP_K
    if dense_top_k is None:
        dense_top_k = cfg.DENSE_TOP_K
    db_path = db_path or cfg.CHROMA_PATH

    queries = expand_queries(question, intent, chart_facts)
    if not queries:
        return []

    collection = _get_collection(db_path)
    where = _intent_filter(intent)

    per_query_hits = []
    for q in queries:
        embedding = embed_query(q)
        if embedding is None:
            continue
        result = _dense_retrieve(collection, embedding, where, dense_top_k)
        hits = _flatten_chroma_result(result)
        if not hits and where is not None and fall_back_no_filter:
            result = _dense_retrieve(collection, embedding, None, dense_top_k)
            hits = _flatten_chroma_result(result)
        per_query_hits.append(hits)

    merged = _merge_results(per_query_hits)
    if not merged:
        return []

    if cfg.HYBRID_BM25_ENABLED:
        chunks = _hybrid_fusion_chunks(
            collection,
            queries,
            merged,
            where,
            fall_back_no_filter,
            question,
            chart_facts,
        )
    else:
        chunks = _build_chunks(merged)

    chunks = _dedupe_chunks_by_ref_keep_best_dense(chunks)
    query_entities = _query_entities(question, chart_facts)
    chunks = _rerank(chunks, query_entities, intent, question, chart_facts)
    if top_k is None:
        return chunks
    return chunks[:top_k]


def search_for_eval(question, intent, chart_facts, db_path=None):
    """Variant for evaluate_rag.py that returns the full reranked list
    (not truncated) plus pre-rerank ordering.

    `search(..., top_k=DENSE_TOP_K)` would drop gold refs that fall outside the
    top-N after rerank; eval needs the complete deduped pool.

    Returns a tuple (post_rerank_chunks, pre_rerank_ref_ids).
    """
    chunks = search(
        question=question,
        intent=intent,
        chart_facts=chart_facts,
        top_k=None,
        db_path=db_path,
    )
    pre_order = sorted(chunks, key=lambda c: c.pre_rerank_rank)
    pre_rerank_ref_ids = [c.ref_id for c in pre_order]
    return chunks, pre_rerank_ref_ids
