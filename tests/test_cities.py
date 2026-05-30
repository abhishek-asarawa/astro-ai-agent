"""Tests for cities.resolve_city_coordinates."""

import pytest

from astro_agent.utils.cities import CITY_COORDINATES, CityResolutionError, resolve_city_coordinates


def test_static_city_hit():
    geo = resolve_city_coordinates("delhi")
    assert geo["source"] == "static"
    assert geo["lat"] == pytest.approx(CITY_COORDINATES["delhi"]["lat"])
    assert geo["lon"] == pytest.approx(CITY_COORDINATES["delhi"]["lon"])


def test_alias_bangalore_maps_to_bengaluru():
    geo = resolve_city_coordinates("Bangalore")
    assert geo["source"] == "static"
    assert geo["label"] == "bengaluru"


def test_empty_city_raises():
    with pytest.raises(CityResolutionError, match="required"):
        resolve_city_coordinates("")


def test_unknown_city_raises_without_mock(monkeypatch):
    resolve_city_coordinates.cache_clear()

    class FakeGeocoder:
        def geocode(self, query):
            return None

    monkeypatch.setattr("geopy.geocoders.Nominatim", lambda **kw: FakeGeocoder())
    with pytest.raises(CityResolutionError, match="Could not find"):
        resolve_city_coordinates("xyznotacity999")


def test_geocode_success(monkeypatch):
    resolve_city_coordinates.cache_clear()

    class Loc:
        latitude = 18.5204
        longitude = 73.8567
        address = "Pune, Maharashtra, India"

    class FakeGeocoder:
        def geocode(self, query):
            return Loc()

    monkeypatch.setattr("geopy.geocoders.Nominatim", lambda **kw: FakeGeocoder())
    geo = resolve_city_coordinates("Someville")
    assert geo["source"] == "geocode"
    assert geo["lat"] == pytest.approx(18.5204)


def test_lru_cache_returns_same_object():
    resolve_city_coordinates.cache_clear()
    a = resolve_city_coordinates("mumbai")
    b = resolve_city_coordinates("mumbai")
    assert a == b
