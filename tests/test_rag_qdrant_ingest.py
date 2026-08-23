"""Ingest pipeline against Qdrant: chunk counts, idempotency, replace-chapter."""

from unittest.mock import patch

from astro_agent.rag import builder

FIXTURE_TEXT = """1. Saturn in the 10th house gives rise through delayed effort and perseverance.

2. The Moon exalted in Taurus in the 4th house blesses domestic happiness.
"""


def _fake_embed_text(text):
    return [0.1] * 768


def test_ingest_adds_expected_chunk_count(tmp_path):
    input_path = tmp_path / "ch_1_test.txt"
    input_path.write_text(FIXTURE_TEXT, encoding="utf-8")
    db_path = str(tmp_path / "qdrant_db")

    with patch.object(builder, "embed_text", side_effect=_fake_embed_text):
        added, skipped = builder.ingest(
            input_path=input_path,
            book="test",
            translator="test",
            chapter=1,
            db_path=db_path,
        )

    # chapter summary + 2 verses = 3 chunks
    assert added == 3
    assert skipped == 0


def test_ingest_is_idempotent_on_rerun(tmp_path):
    input_path = tmp_path / "ch_1_test.txt"
    input_path.write_text(FIXTURE_TEXT, encoding="utf-8")
    db_path = str(tmp_path / "qdrant_db")

    with patch.object(builder, "embed_text", side_effect=_fake_embed_text):
        builder.ingest(input_path=input_path, book="test", translator="test", chapter=1, db_path=db_path)
        added_second, skipped_second = builder.ingest(
            input_path=input_path,
            book="test",
            translator="test",
            chapter=1,
            db_path=db_path,
        )

    assert added_second == 0
    assert skipped_second == 3


def test_replace_chapter_clears_prior_rows(tmp_path):
    input_path = tmp_path / "ch_1_test.txt"
    input_path.write_text(FIXTURE_TEXT, encoding="utf-8")
    db_path = str(tmp_path / "qdrant_db")

    with patch.object(builder, "embed_text", side_effect=_fake_embed_text):
        builder.ingest(input_path=input_path, book="test", translator="test", chapter=1, db_path=db_path)
        added, skipped = builder.ingest(
            input_path=input_path,
            book="test",
            translator="test",
            chapter=1,
            db_path=db_path,
            replace_chapter=True,
        )

    # replace-chapter deletes the 3 existing rows first, so all 3 are re-added fresh
    assert added == 3
    assert skipped == 0
