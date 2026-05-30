"""Bhava (cusp-based) house assignment tests."""

import pytest

from astro_agent.chart.engine import _bhava_house_for_longitude, build_chart_features


def test_bhava_house_simple_interval():
    cusps = [0.0, 30.0, 60.0, 90.0, 120.0, 150.0, 180.0, 210.0, 240.0, 270.0, 300.0, 330.0]
    assert _bhava_house_for_longitude(15.0, cusps) == 1
    assert _bhava_house_for_longitude(45.0, cusps) == 2


def test_bhava_house_wrap_at_360():
    cusps = [330.0, 30.0, 60.0, 90.0, 120.0, 150.0, 180.0, 210.0, 240.0, 270.0, 300.0, 315.0]
    assert _bhava_house_for_longitude(340.0, cusps) == 1
    assert _bhava_house_for_longitude(45.0, cusps) == 2


def test_build_chart_features_has_bhava_and_sign_houses():
    features = build_chart_features(1990, 5, 15, 10, 30, "bengaluru")
    planets = features["planets"]
    assert set(features["sign_houses"].keys()) == set(planets.keys())
    assert set(features["bhava_positions"].keys()) == set(planets.keys())
    for house in features["bhava_positions"].values():
        assert 1 <= house <= 12
    for house in features["sign_houses"].values():
        assert house is None or 1 <= house <= 12
