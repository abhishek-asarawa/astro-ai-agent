#!/usr/bin/env python3
"""OCR an inclusive 1-based PDF page range from the Sharma BPHS Vol. 1 PDF.

Depends: PyMuPDF (fitz), tesseract on PATH, English traineddata.

Example:
  PYTHONPATH=.pip_target python tools/ocr_bphs_chapter_range.py \\
    --pdf \"Brihat Parasara Hora Sastra with English Translation Girish Chand Sharma Volume 1.pdf\" \\
    --start 202 --end 208 \\
    --output data/corpus/bphs_sharma/ch_14_effects_of_1_house.txt

Verified 1-based PDF page spans (Internet Archive Sharma Vol. 1, image-only English):
  ch 13 -> 197–201, 14 -> 202–208, 16 -> 219–227, 17 -> 228–231,
  18 -> 232–240, 20 -> 249–258, 25 -> 279–282.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

import fitz  # PyMuPDF


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
            timeout=300,
            check=True,
        )
        return r.stdout or ""
    finally:
        try:
            os.unlink(png)
        except OSError:
            pass


def main() -> None:
    ap = argparse.ArgumentParser(description="OCR a page range from BPHS PDF.")
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--start", type=int, required=True, help="First page (1-based, inclusive).")
    ap.add_argument("--end", type=int, required=True, help="Last page (1-based, inclusive).")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--psm", default="1", help="Tesseract page segmentation mode (default 1).")
    args = ap.parse_args()

    if args.end < args.start:
        raise SystemExit("--end must be >= --start")

    doc = fitz.open(args.pdf)
    try:
        parts: list[str] = []
        for p in range(args.start, args.end + 1):
            if p < 1 or p > len(doc):
                raise SystemExit(f"Page {p} out of range (1–{len(doc)})")
            parts.append(ocr_page(doc, p, args.dpi, args.psm))
            parts.append("\n\n")
        text = "".join(parts).strip() + "\n"
    finally:
        doc.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"Wrote {args.output} ({args.end - args.start + 1} pages)")


if __name__ == "__main__":
    main()
