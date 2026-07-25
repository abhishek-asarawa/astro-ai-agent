"""Idempotent ingest pipeline for the RAG corpus.

Reads a single chapter text file (typically OCR'd from a translation
PDF), cleans common OCR artifacts, splits into verse-level chunks plus
one chapter-summary chunk, regex-tags entities and intents, embeds via
Ollama (`nomic-embed-text` with `keep_alive=0`), and upserts into a
local ChromaDB collection. Chunk IDs are sha256(text) so re-runs skip
already-ingested chunks.

Usage:
    python knowledge_builder.py \
        --input data/corpus/bphs_sharma/ch_23_effects_of_10_house.txt \
        --book bphs \
        --translator sharma \
        --chapter 23

    After changing how verses are split, re-ingest with --replace-chapter so stale
    sha256 ids for the same ref_id are removed before new rows are added.
"""

import argparse
import hashlib
import re
import sys
from collections import Counter
from pathlib import Path

import chromadb
import requests

from astro_agent.rag import config as cfg

# Ranges may omit the dot (e.g. "20 1/2-22 If"); single sloka numbers must use
# a period so prose like "7 or the Uttarardha" does not start a false verse.
VERSE_HEAD_RE = re.compile(
    r"(?m)^(?:"
    r"(\d{1,2})(?:\s+1/2)?-(\d{1,2})(?:\s+1/2)?\.?\s+"
    r"|(\d{1,2})(?:\s+1/2)\.\s+"
    r"|(\d{1,2})\.\s+"
    r")(?=[A-Za-z])",
)


def _strip_known_running_headers(text):
    text = re.sub(
        r"(?im)^\s*\d+\s+Effects of [Tt]he [A-Za-z]+ House\s*$",
        "",
        text,
    )
    text = re.sub(
        r"(?im)^\s*Brihat Paras[ae]ra Hora Sh?astr[ae]\s+\d+\s*$",
        "",
        text,
    )
    return text


def _drop_repeating_short_lines(text):
    lines = text.split("\n")
    bodies = Counter()
    for line in lines:
        stripped = line.strip()
        if not stripped or len(stripped) > 60:
            continue
        body = re.sub(r"\d+", "", stripped).strip().lower()
        if body:
            bodies[body] += 1
    repeating = {b for b, c in bodies.items() if c >= 3}

    kept = []
    for line in lines:
        stripped = line.strip()
        if stripped.isdigit():
            continue
        body = re.sub(r"\d+", "", stripped).strip().lower()
        if body and body in repeating and len(stripped) <= 60:
            continue
        kept.append(line)
    return "\n".join(kept)


def _join_hyphenation(text):
    return re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)


def _normalize_whitespace(text):
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_ocr_text(text):
    """Apply OCR-tolerant cleanup. Errs on the side of keeping content."""
    text = _strip_known_running_headers(text)
    text = _drop_repeating_short_lines(text)
    text = _join_hyphenation(text)
    text = _normalize_whitespace(text)
    return text


def _split_verses(text):
    """Yield (verse_start, verse_end, verse_text) tuples.

    Multi-verse blocks like '8-10 If...' return verse_end > verse_start.
    Single verses return verse_end == verse_start. The chapter prelude
    before verse 1 is yielded as a synthetic (0, 0, prelude_text) tuple
    only if there is real content there.
    """
    matches = list(VERSE_HEAD_RE.finditer(text))
    if not matches:
        return

    prelude = text[: matches[0].start()].strip()
    if prelude:
        yield (0, 0, prelude)

    for idx, m in enumerate(matches):
        if m.group(1) is not None:
            start_num, end_num = int(m.group(1)), int(m.group(2))
        elif m.group(3) is not None:
            start_num = end_num = int(m.group(3))
        else:
            start_num = end_num = int(m.group(4))
        body_start = m.start()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        if body:
            yield (start_num, end_num, body)


def _build_chapter_summary(book, chapter, prelude, first_verse_text):
    title = f"BPHS Chapter {chapter}" if book == "bphs" else f"Chapter {chapter}"
    pieces = [f"[{title} - chapter overview]"]
    if prelude:
        pieces.append(prelude)
    if first_verse_text:
        pieces.append(first_verse_text)
    return "\n\n".join(pieces).strip()


def _hash_id(text):
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def _rough_sentences(text):
    """Split English OCR prose on paragraph breaks and sentence-ending punctuation."""
    sentences = []
    for para in re.split(r"\n\s*\n", (text or "").strip()):
        para = para.strip()
        if not para:
            continue
        for chunk in re.split(r"(?<=[.!?])\s+", para):
            chunk = chunk.strip()
            if chunk:
                sentences.append(chunk)
    return sentences if sentences else ([text.strip()] if text and text.strip() else [])


def _hard_split_words(text, max_tokens, estimate_fn):
    """Last resort: pack whitespace-delimited words under max_tokens each."""
    words = (text or "").split()
    if not words:
        return [text.strip()] if text and text.strip() else []
    out, buf = [], []
    for w in words:
        trial = " ".join(buf + [w])
        if buf and estimate_fn(trial) > max_tokens:
            out.append(" ".join(buf))
            buf = [w]
        else:
            buf.append(w)
    if buf:
        out.append(" ".join(buf))
    return out


def _pack_under_token_budget(sentences, pack_target, estimate_fn):
    """Greedy pack of sentences into segments each <= pack_target (estimated tokens)."""
    if not sentences:
        return []
    out, buf = [], []
    for s in sentences:
        pieces = _hard_split_words(s, pack_target, estimate_fn) if estimate_fn(s) > pack_target else [s]
        for piece in pieces:
            trial = " ".join(buf + [piece]) if buf else piece
            if buf and estimate_fn(trial) > pack_target:
                out.append(" ".join(buf).strip())
                buf = [piece]
            else:
                buf.append(piece)
    if buf:
        out.append(" ".join(buf).strip())
    return [x for x in out if x]


def _split_oversize_body(text, threshold_tokens, pack_target, estimate_fn):
    """Return one or more text segments; single element if already under threshold."""
    if estimate_fn(text) <= threshold_tokens:
        return [text]
    sents = _rough_sentences(text)
    packed = _pack_under_token_budget(sents, pack_target, estimate_fn)
    return packed if packed else [text]


def _expand_oversize_chunks(chunks):
    """Split verse/chapter chunks whose text exceeds cfg.CHUNK_MAX_TOKENS."""
    threshold = cfg.CHUNK_MAX_TOKENS
    pack_target = cfg.CHUNK_TARGET_TOKENS
    est = cfg.estimate_tokens
    expanded = []
    for ch in chunks:
        if ch["chunk_level"] not in ("verse", "chapter"):
            expanded.append(ch)
            continue
        if est(ch["text"]) <= threshold:
            expanded.append(ch)
            continue
        parts = _split_oversize_body(ch["text"], threshold, pack_target, est)
        if len(parts) <= 1:
            expanded.append(ch)
            continue
        for p in parts:
            expanded.append(
                {
                    "text": p,
                    "verse_start": ch["verse_start"],
                    "verse_end": ch["verse_end"],
                    "chunk_level": ch["chunk_level"],
                }
            )
    return expanded


def _delete_chapter_rows(collection, book, chapter):
    """Remove all indexed rows for this book/chapter (metadata filter)."""
    res = collection.get(
        where={
            "$and": [
                {"book": {"$eq": book}},
                {"chapter": {"$eq": int(chapter)}},
            ]
        },
    )
    ids = res.get("ids") or []
    if ids:
        collection.delete(ids=ids)
    return len(ids)


def _ref_id(book, chapter, verse_start, verse_end, chunk_level):
    if chunk_level == "chapter":
        return f"{book}-ch{chapter}-summary"
    if verse_start == verse_end:
        return f"{book}-ch{chapter}-v{verse_start}"
    return f"{book}-ch{chapter}-v{verse_start}-{verse_end}"


def _build_metadata(book, translator, chapter, verse_start, verse_end, chunk_level, text):
    entities = cfg.extract_entities(text)
    entity_field = "|" + "|".join(entities) + "|" if entities else "||"
    intent_flags = cfg.detect_intent_tags(text)
    meta = {
        "book": book,
        "translator": translator,
        "chapter": int(chapter),
        "verse_start": int(verse_start),
        "verse_end": int(verse_end),
        "chunk_level": chunk_level,
        "entities": entity_field,
        "token_count": cfg.estimate_tokens(text),
        "ref_id": _ref_id(book, chapter, verse_start, verse_end, chunk_level),
    }
    meta.update(intent_flags)
    return meta


def embed_text(text):
    """Single embedding call. Evicts the model after each call (keep_alive=0)."""
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
    data = response.json()
    embedding = data.get("embedding")
    if not embedding or len(embedding) != cfg.EMBED_DIM:
        raise RuntimeError(f"Embedding API returned unexpected payload: dim={len(embedding) if embedding else 0}")
    return embedding


def get_collection(db_path):
    client = chromadb.PersistentClient(path=db_path)
    return client.get_or_create_collection(
        name=cfg.CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def ingest(input_path, book, translator, chapter, db_path, verbose=False, replace_chapter=False):
    raw = Path(input_path).read_text(encoding="utf-8")
    cleaned = clean_ocr_text(raw)

    verses = list(_split_verses(cleaned))
    if not verses:
        print(f"No verses detected in {input_path}.", file=sys.stderr)
        return 0, 0

    prelude_text = ""
    first_verse_text = ""
    for vs, _ve, body in verses:
        if vs == 0:
            prelude_text = body
        elif first_verse_text == "" and vs == 1:
            first_verse_text = body
            break

    summary_text = _build_chapter_summary(book, chapter, prelude_text, first_verse_text)

    chunks = []
    if summary_text:
        chunks.append(
            {
                "text": summary_text,
                "verse_start": 1,
                "verse_end": 1,
                "chunk_level": "chapter",
            }
        )
    for vs, ve, body in verses:
        if vs == 0:
            continue
        chunks.append(
            {
                "text": body,
                "verse_start": vs,
                "verse_end": ve,
                "chunk_level": "verse",
            }
        )

    chunks = _expand_oversize_chunks(chunks)

    collection = get_collection(db_path)
    if replace_chapter:
        removed = _delete_chapter_rows(collection, book, chapter)
        if verbose:
            print(
                f"replace-chapter: removed {removed} existing row(s) for {book} chapter {chapter}",
                file=sys.stderr,
            )

    new_ids, new_docs, new_embeddings, new_metas = [], [], [], []
    skipped = 0

    for chunk in chunks:
        chunk_id = _hash_id(chunk["text"])
        existing = collection.get(ids=[chunk_id])
        if existing and existing.get("ids"):
            skipped += 1
            if verbose:
                print(f"  skip {chunk_id[:10]}  {chunk['chunk_level']}  v{chunk['verse_start']}-{chunk['verse_end']}")
            continue

        embedding = embed_text(chunk["text"])
        meta = _build_metadata(
            book=book,
            translator=translator,
            chapter=chapter,
            verse_start=chunk["verse_start"],
            verse_end=chunk["verse_end"],
            chunk_level=chunk["chunk_level"],
            text=chunk["text"],
        )

        new_ids.append(chunk_id)
        new_docs.append(chunk["text"])
        new_embeddings.append(embedding)
        new_metas.append(meta)

        if verbose:
            print(
                f"  add  {chunk_id[:10]}  {meta['ref_id']:24s}  tokens={meta['token_count']:4d}  entities={meta['entities']}"
            )

    if new_ids:
        collection.add(
            ids=new_ids,
            documents=new_docs,
            embeddings=new_embeddings,
            metadatas=new_metas,
        )

    return len(new_ids), skipped


def parse_args():
    parser = argparse.ArgumentParser(description="Ingest a classical text chapter into the RAG vector DB.")
    parser.add_argument("--input", required=True, help="Path to a chapter .txt file.")
    parser.add_argument("--book", default="bphs", help="Book key (e.g. 'bphs').")
    parser.add_argument("--translator", default="sharma", help="Translator key.")
    parser.add_argument("--chapter", type=int, required=True, help="Chapter number from the source edition.")
    parser.add_argument("--db-path", default=cfg.CHROMA_PATH, help="ChromaDB persistence directory.")
    parser.add_argument("--verbose", action="store_true", help="Print per-chunk add/skip log.")
    parser.add_argument(
        "--replace-chapter",
        action="store_true",
        help="Delete all Chroma rows for this book+chapter before ingest (drops stale hashes after text splits).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    added, skipped = ingest(
        input_path=args.input,
        book=args.book,
        translator=args.translator,
        chapter=args.chapter,
        db_path=args.db_path,
        verbose=args.verbose,
        replace_chapter=args.replace_chapter,
    )
    print(f"Ingested {added} new chunks, skipped {skipped} already present.")
