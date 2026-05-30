#!/usr/bin/env python3
"""OCR-scan every PDF page; detect early-window chapter headers; emit start pages.

Heuristic: in the first ~350 characters of Tesseract output, if exactly one
\"Chapter N\" / \"CHAPTER N\" appears, treat that page as the start page for N
(unless a smaller start was already recorded).

Writes JSON: {\"1\": 12, \"2\": 29, ...} (1-based PDF page indices).

Depends: PyMuPDF, tesseract.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
from book_paths import BPHS_SHARMA_VOL1_PDF  # noqa: E402

# Tesseract often reads "Chapter -7" / "Chapter-9" for some titles.
HEAD_RE = re.compile(r"(?i)(?:Chapter|CHAPTER)\s*-?\s*(\d+)\b")


def ocr_page(doc: fitz.Document, page_1based: int, dpi: int, psm: str) -> str:
    page = doc[page_1based - 1]
    pix = page.get_pixmap(dpi=dpi)
    fd, png = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        pix.save(png)
        r = subprocess.run(
            ["tesseract", png, "stdout", "-l", "eng", "--psm", psm],
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        return r.stdout or ""
    finally:
        try:
            os.unlink(png)
        except OSError:
            pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", type=Path, default=BPHS_SHARMA_VOL1_PDF)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dpi", type=int, default=96)
    ap.add_argument("--psm", default="1")
    ap.add_argument("--head-chars", type=int, default=350)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    try:
        first_page: dict[int, int] = {}
        for i in range(len(doc)):
            p1 = i + 1
            text = ocr_page(doc, p1, args.dpi, args.psm)
            head = text[: args.head_chars]
            nums = [int(m.group(1)) for m in HEAD_RE.finditer(head)]
            uniq = sorted(set(nums))
            if len(uniq) != 1:
                continue
            ch = uniq[0]
            if ch not in first_page or p1 < first_page[ch]:
                first_page[ch] = p1
                if args.verbose:
                    print(f"ch {ch} start pdf page {p1}", flush=True)
    finally:
        doc.close()

    # Stable string keys for JSON
    out = {str(k): first_page[k] for k in sorted(first_page.keys())}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({len(out)} chapter starts)")


if __name__ == "__main__":
    main()
