"""Rule-based confidence calibration for structured answers."""

from __future__ import annotations


def calibrate_confidence(
    model_confidence: int | None,
    evidence: list[str] | None,
    ref_ids_used: list[str] | None,
) -> int:
    """Cap model-reported confidence when grounding is weak."""
    conf = model_confidence if model_confidence is not None else 50
    if not ref_ids_used:
        conf = min(conf, 55)
    if len(evidence or []) < 2:
        conf = min(conf, 50)
    return max(0, min(100, conf))
