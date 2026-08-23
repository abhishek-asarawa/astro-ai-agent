"""BM25 sparse-vector encoding via fastembed, shared by ingest and retrieval.

fastembed's BM25 implementation is algorithmic (tokenize + stem + term
frequency), not a downloaded neural model, so this has no meaningful
first-use latency or network dependency beyond the fastembed package
itself.
"""

from functools import lru_cache

from fastembed import SparseTextEmbedding

from astro_agent.rag import config as cfg


@lru_cache(maxsize=1)
def _model():
    return SparseTextEmbedding(model_name=cfg.SPARSE_MODEL_NAME)


def embed_documents(texts):
    """Precompute one BM25 sparse vector per input text (ingest-time, term-frequency weighted)."""
    return list(_model().embed(list(texts)))


def embed_query(text):
    """Encode a single query string as a BM25 sparse vector (uniform token weights)."""
    return next(iter(_model().query_embed(text)))
