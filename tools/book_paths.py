"""Paths to reference books used for corpus OCR and ingest."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

BPHS_SHARMA_VOL1_FILENAME = (
    "Brihat Parasara Hora Sastra with English Translation Girish Chand Sharma Volume 1.pdf"
)
BPHS_SHARMA_VOL1_PDF = _REPO_ROOT / "books" / BPHS_SHARMA_VOL1_FILENAME
BPHS_SHARMA_VOL1_PDF_REL = f"books/{BPHS_SHARMA_VOL1_FILENAME}"
