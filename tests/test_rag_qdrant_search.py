"""Retrieval pipeline against Qdrant: dense+sparse plumbing and reranking."""

from unittest.mock import patch

from astro_agent.rag import builder
from astro_agent.rag import search as rag_search

FIXTURE_TEXT = """1. Saturn in the 10th house gives rise through delayed effort and perseverance.

2. The Moon exalted in Taurus in the 4th house blesses domestic happiness.
"""


def _fake_embed(text):
    # Deterministic per-text fake vector so dense similarity is meaningful.
    seed = sum(ord(c) for c in text) % 97
    return [(seed + i) / 1000.0 for i in range(768)]


def _ingest_fixture(tmp_path):
    input_path = tmp_path / "ch_1_test.txt"
    input_path.write_text(FIXTURE_TEXT, encoding="utf-8")
    db_path = str(tmp_path / "qdrant_db")
    with patch.object(builder, "embed_text", side_effect=_fake_embed):
        builder.ingest(input_path=input_path, book="test", translator="test", chapter=1, db_path=db_path)
    return db_path


def test_search_returns_retrieved_chunks_with_ranks(tmp_path):
    db_path = _ingest_fixture(tmp_path)

    with patch.object(rag_search, "embed_query", side_effect=_fake_embed):
        results = rag_search.search(
            question="Saturn in the 10th house",
            intent="general",
            db_path=db_path,
            top_k=None,
        )

    assert results
    assert all(isinstance(r, rag_search.RetrievedChunk) for r in results)
    assert all(r.pre_rerank_rank >= 0 for r in results)
    assert all(r.post_rerank_rank >= 0 for r in results)
    ref_ids = {r.ref_id for r in results}
    assert "test-ch1-v1" in ref_ids
    assert "test-ch1-v2" in ref_ids


def test_sparse_side_finds_lexical_match_dense_alone_would_miss(tmp_path):
    db_path = _ingest_fixture(tmp_path)

    # Every query maps to the same non-zero dense vector (not nearer to
    # either chunk than the other), so a correct top-2 match here can only
    # come from the BM25 sparse side actually being wired up — this is the
    # test that would catch a broken sparse integration.
    neutral_vector = _fake_embed("xyz unrelated filler text")
    with patch.object(rag_search, "embed_query", return_value=neutral_vector):
        results = rag_search.search(
            question="Moon exalted Taurus fourth house",
            intent="general",
            db_path=db_path,
            top_k=None,
        )

    top_ref_ids = [r.ref_id for r in results[:2]]
    assert "test-ch1-v2" in top_ref_ids
