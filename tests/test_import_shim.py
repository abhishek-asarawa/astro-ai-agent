"""Ensure astro_engine shim re-exports the public API."""

import astro_engine


def test_shim_exports_all():
    for name in astro_engine.__all__:
        assert hasattr(astro_engine, name), f"missing export: {name}"
