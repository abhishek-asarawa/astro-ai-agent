"""BM25 sparse-vector encoding via fastembed."""

from astro_agent.rag import sparse


def test_embed_documents_returns_one_sparse_vector_per_text():
    texts = [
        "Saturn in the 10th house delays but rewards effort.",
        "The Moon in Cancer is exalted.",
    ]
    embeddings = sparse.embed_documents(texts)
    assert len(embeddings) == 2
    for emb in embeddings:
        assert len(emb.indices) > 0
        assert len(emb.indices) == len(emb.values)


def test_embed_query_shares_indices_with_matching_document():
    doc_emb = sparse.embed_documents(["Saturn debilitated in the tenth house"])[0]
    query_emb = sparse.embed_query("Saturn debilitated tenth house")
    shared = set(doc_emb.indices) & set(query_emb.indices)
    assert shared, "query and document sharing vocabulary should share sparse indices"
