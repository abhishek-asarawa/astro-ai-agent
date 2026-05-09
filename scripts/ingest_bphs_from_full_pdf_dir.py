#!/usr/bin/env python3
"""Batch-ingest BPHS chapter .txt files from a directory into Chroma.

Expects filenames like ``ch_14_effects_of_1_house.txt`` (``ch_<n>_`` prefix).

Examples:
  python scripts/ingest_bphs_from_full_pdf_dir.py \\
    --dir data/corpus/bphs_sharma/from_full_pdf --verbose

  # Skip whole chapters that already have any rows for book+chapter in Chroma:
  python scripts/ingest_bphs_from_full_pdf_dir.py \\
    --dir data/corpus/bphs_sharma/from_full_pdf --skip-existing-in-chroma --verbose
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import rag_config as cfg
from knowledge_builder import get_collection, ingest

CHAPTER_FROM_NAME = re.compile(r"^ch_(\d+)_", re.IGNORECASE)


def _chapter_from_path(path: Path) -> int | None:
    m = CHAPTER_FROM_NAME.match(path.name)
    return int(m.group(1)) if m else None


def _chapter_has_any_rows(collection, book: str, chapter: int) -> bool:
    res = collection.get(
        where={
            "$and": [
                {"book": {"$eq": book}},
                {"chapter": {"$eq": int(chapter)}},
            ]
        },
        limit=1,
    )
    return bool(res.get("ids"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest all ch_N_*.txt files from a directory.")
    parser.add_argument(
        "--dir",
        type=Path,
        required=True,
        help="Directory containing chapter .txt files (e.g. data/corpus/bphs_sharma/from_full_pdf).",
    )
    parser.add_argument("--book", default="bphs")
    parser.add_argument("--translator", default="sharma")
    parser.add_argument("--db-path", default=cfg.CHROMA_PATH)
    parser.add_argument(
        "--skip-existing-in-chroma",
        action="store_true",
        help="If Chroma already has any chunk for this book+chapter, skip the file entirely.",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--replace-chapter",
        action="store_true",
        help="Passed through to ingest: delete existing rows for each chapter before adding.",
    )
    args = parser.parse_args()

    root: Path = args.dir
    if not root.is_dir():
        print(f"Not a directory: {root.resolve()}", file=sys.stderr)
        sys.exit(1)

    files: list[tuple[int, Path]] = []
    for p in sorted(root.glob("*.txt")):
        ch = _chapter_from_path(p)
        if ch is not None:
            files.append((ch, p))
        elif args.verbose:
            print(f"  (ignored — no ch_<n>_ prefix: {p.name})", file=sys.stderr)

    if not files:
        print(f"No ch_<n>_*.txt files under {root}", file=sys.stderr)
        sys.exit(1)

    files.sort(key=lambda t: t[0])
    collection = get_collection(args.db_path)
    total_added = total_skipped_chunks = 0
    skipped_files = 0

    for chapter, path in files:
        if args.skip_existing_in_chroma and _chapter_has_any_rows(collection, args.book, chapter):
            skipped_files += 1
            if args.verbose:
                print(f"skip file (chapter already in Chroma): {path.name}", file=sys.stderr)
            continue
        added, skipped = ingest(
            input_path=path,
            book=args.book,
            translator=args.translator,
            chapter=chapter,
            db_path=args.db_path,
            verbose=args.verbose,
            replace_chapter=args.replace_chapter,
        )
        total_added += added
        total_skipped_chunks += skipped
        print(f"{path.name}  chapter={chapter}  +{added} new chunks, {skipped} hash-skipped")

    print(
        f"Done. Files processed: {len(files) - skipped_files}/{len(files)}; "
        f"new chunks: {total_added}; in-file hash skips: {total_skipped_chunks}; "
        f"files skipped (--skip-existing-in-chroma): {skipped_files}"
    )


if __name__ == "__main__":
    main()
