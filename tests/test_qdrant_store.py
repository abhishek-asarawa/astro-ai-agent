"""Shared Qdrant collection setup: schema creation and idempotency."""

from astro_agent.rag import qdrant_store


def test_get_collection_creates_dense_and_sparse_vectors(tmp_path):
    client = qdrant_store.get_collection(db_path=str(tmp_path / "qdrant_db"))
    info = client.get_collection(qdrant_store.cfg.QDRANT_COLLECTION)
    assert qdrant_store.DENSE_VECTOR_NAME in info.config.params.vectors
    assert qdrant_store.SPARSE_VECTOR_NAME in info.config.params.sparse_vectors


def test_ensure_collection_is_idempotent(tmp_path):
    client = qdrant_store.QdrantClient(path=str(tmp_path / "qdrant_db"))
    qdrant_store.ensure_collection(client)
    qdrant_store.ensure_collection(client)  # must not raise
    assert client.collection_exists(qdrant_store.cfg.QDRANT_COLLECTION)
