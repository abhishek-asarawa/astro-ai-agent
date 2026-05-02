"""Retrieval module for the RAG pipeline.

`search()` is the only public entry point. Given a user question, an
intent (from intent_router), and optional chart facts, it returns the
top-k most relevant chunks from the local Chroma index. Strategy:

1. Multi-query expansion (literal question + chart-derived structural
   query + intent-focused query) to widen recall.
2. Per-query dense retrieval from Chroma with an intent boolean filter.
3. Merge and dedupe by `ref_id`, keeping each chunk's best dense rank.
4. Heuristic rerank using entity overlap + intent match - length penalty.
5. Return top-k with both pre- and post-rerank ranks so eval_rag can
   compute heuristic_delta.
"""

from dataclasses import dataclass, field

import chromadb
import requests

import rag_config as cfg


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

    seen = set()
    deduped = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            deduped.append(q)
    return deduped


def _parse_entities_field(entities_field):
    if not entities_field:
        return set()
    return {tok for tok in entities_field.split("|") if tok}


def _query_entities(question, chart_facts):
    text_parts = [question or ""]
    text_parts.append(_summarize_chart_facts(chart_facts))
    combined = " ".join(part for part in text_parts if part)
    return set(cfg.extract_entities(combined))


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


def _rerank(chunks, query_entities, intent):
    intent_key = f"intent_{intent}" if intent in cfg.SUPPORTED_INTENTS else None
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
        chunk.score = (
            chunk.similarity
            + cfg.ENTITY_WEIGHT * capped_match_count
            + cfg.INTENT_WEIGHT * intent_match
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
    top_k=None,
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
        top_k: Final number of chunks to return after rerank.
        db_path: Override default Chroma path.
        dense_top_k: How many to pull from Chroma per query before rerank.
        fall_back_no_filter: If filtered query returns 0, retry with no
            intent filter. Useful when the corpus is small.

    Returns:
        List[RetrievedChunk] of length <= top_k, sorted by post-rerank
        score descending. Each chunk carries pre_rerank_rank and
        post_rerank_rank so eval can compute heuristic_delta.
    """
    if top_k is None:
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

    chunks = _build_chunks(merged)
    query_entities = _query_entities(question, chart_facts)
    chunks = _rerank(chunks, query_entities, intent)
    return chunks[:top_k]


def search_for_eval(question, intent, chart_facts, db_path=None):
    """Variant for evaluate_rag.py that returns the full reranked list
    (not just top-k) plus pre-rerank ordering.

    Returns a tuple (post_rerank_chunks, pre_rerank_ref_ids).
    """
    chunks = search(
        question=question,
        intent=intent,
        chart_facts=chart_facts,
        top_k=cfg.DENSE_TOP_K,
        db_path=db_path,
    )
    pre_order = sorted(chunks, key=lambda c: c.pre_rerank_rank)
    pre_rerank_ref_ids = [c.ref_id for c in pre_order]
    return chunks, pre_rerank_ref_ids
