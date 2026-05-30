#!/usr/bin/env python3
"""OCR BPHS Sharma Vol. 1 chapters using tools/bphs_vol1_sharma_chapter_starts.json.

Skips chapters 13–25 by default (existing hand-tuned filenames in data/corpus/bphs_sharma).

Example:
  python tools/extract_bphs_vol1_from_map.py

  # Override PDF path if needed:
  python tools/extract_bphs_vol1_from_map.py --pdf books/Brihat\\ Parasara\\ Hora\\ Sastra\\ with\\ English\\ Translation\\ Girish\\ Chand\\ Sharma\\ Volume\\ 1.pdf
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import fitz

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
from ocr_bphs_chapter_range import ocr_page  # noqa: E402
from book_paths import BPHS_SHARMA_VOL1_PDF  # noqa: E402

DEFAULT_SKIP = tuple(range(13, 26))  # existing corpus files


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, default=BPHS_SHARMA_VOL1_PDF)
    ap.add_argument(
        "--map-json",
        type=Path,
        default=_TOOLS_DIR / "bphs_vol1_sharma_chapter_starts.json",
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/corpus/bphs_sharma"),
    )
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--psm", default="1")
    ap.add_argument(
        "--only",
        type=str,
        default="",
        help="Comma-separated chapter numbers to extract only (e.g. '1,2,26').",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Re-OCR even when output file already exists.",
    )
    args = ap.parse_args()

    starts = {int(k): v for k, v in json.loads(args.map_json.read_text(encoding="utf-8")).items()}
    order = sorted(starts.keys())
    only_set = {int(x.strip()) for x in args.only.split(",") if x.strip()}

    doc = fitz.open(args.pdf)
    try:
        n_pages = len(doc)
        ends: dict[int, int] = {}
        for i, ch in enumerate(order):
            if i + 1 < len(order):
                ends[ch] = starts[order[i + 1]] - 1
            else:
                ends[ch] = n_pages

        for ch in order:
            if ch in DEFAULT_SKIP:
                print(f"skip ch {ch} (default 13–25 existing corpus)")
                continue
            if only_set and ch not in only_set:
                continue
            start, end = starts[ch], ends[ch]
            out = args.out_dir / f"ch_{ch}_bphs_vol1.txt"
            if out.exists() and not args.force:
                print(f"skip ch {ch} exists {out.name}")
                continue
            parts: list[str] = []
            for p in range(start, end + 1):
                if p < 1 or p > n_pages:
                    print(f"error: page {p} out of range for ch {ch}", file=sys.stderr)
                    sys.exit(1)
                parts.append(ocr_page(doc, p, args.dpi, args.psm))
                parts.append("\n\n")
            text = "".join(parts).strip() + "\n"
            args.out_dir.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            print(f"ch {ch} pages {start}-{end} -> {out.name} ({end - start + 1} pp)")
    finally:
        doc.close()


if __name__ == "__main__":
    main()
