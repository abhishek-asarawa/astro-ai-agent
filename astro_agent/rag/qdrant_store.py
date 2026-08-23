"""Shared Qdrant client/collection setup for the RAG ingest and retrieval
pipelines.

Both astro_agent/rag/builder.py (ingest) and astro_agent/rag/search.py
(retrieval) need an identically-configured collection (dense + sparse
named vectors). Centralizing schema creation here avoids the two files
drifting out of sync.
"""

from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client import models as qmodels

from astro_agent.rag import config as cfg

DENSE_VECTOR_NAME = cfg.DENSE_VECTOR_NAME
SPARSE_VECTOR_NAME = cfg.SPARSE_VECTOR_NAME


def ensure_collection(client):
    """Create the RAG collection if it doesn't already exist. Idempotent."""
    if client.collection_exists(cfg.QDRANT_COLLECTION):
        return
    client.create_collection(
        collection_name=cfg.QDRANT_COLLECTION,
        vectors_config={
            DENSE_VECTOR_NAME: qmodels.VectorParams(
                size=cfg.EMBED_DIM,
                distance=qmodels.Distance.COSINE,
            ),
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: qmodels.SparseVectorParams(
                modifier=qmodels.Modifier.IDF,
            ),
        },
    )


@lru_cache(maxsize=8)
def get_collection(db_path=None):
    """Return a cached QdrantClient (local/embedded mode) with the RAG collection ensured.

    Cached by path so multiple callers within the same process (e.g. the bulk
    ingest script and builder.ingest()) share one client instance — Qdrant's
    local mode uses an exclusive file lock that prevents two simultaneous
    clients on the same path.
    """
    client = QdrantClient(path=db_path or cfg.QDRANT_PATH)
    ensure_collection(client)
    return client
