"""Antardasha (Vimshottari sub-period) invariants for dashas.calculate_antardashas."""

import datetime

import pytest

from dashas import DASHA_SEQUENCE, calculate_antardashas, get_current_and_next_antardasha


def _parse(d: dict):
    return (
        datetime.date.fromisoformat(d["start"]),
        datetime.date.fromisoformat(d["end"]),
    )


def _lord_sequence_from_md(mahadasha_lord: str):
    start_idx = next(i for i, (n, _) in enumerate(DASHA_SEQUENCE) if n == mahadasha_lord)
    return [DASHA_SEQUENCE[(start_idx + k) % 9][0] for k in range(9)]


@pytest.mark.parametrize(
    "md_lord",
    ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"],
)
def test_antardasha_order_and_count(md_lord):
    m_start = datetime.date(2020, 1, 1)
    m_end = datetime.date(2030, 1, 1)
    ant = calculate_antardashas(md_lord, m_start, m_end)
    assert len(ant) == 9
    expected_lords = _lord_sequence_from_md(md_lord)
    assert [a["dasha"] for a in ant] == expected_lords


def test_antardasha_contiguity_mass_balance_and_nesting():
    md_lord = "Saturn"
    m_start = datetime.date(2015, 6, 15)
    m_end = datetime.date(2034, 10, 28)
    ant = calculate_antardashas(md_lord, m_start, m_end)
    assert len(ant) == 9

    md_span_days = (m_end - m_start).total_seconds() / 86400.0
    total_antar_days = 0.0
    for i, seg in enumerate(ant):
        s, e = _parse(seg)
        assert s <= e
        assert m_start <= s <= m_end
        assert m_start <= e <= m_end
        total_antar_days += (e - s).total_seconds() / 86400.0
        if i > 0:
            prev_e = _parse(ant[i - 1])[1]
            gap_days = abs((s - prev_e).days)
            assert gap_days <= 1

    assert abs(total_antar_days - md_span_days) <= 2.0


def test_get_current_and_next_antardasha_finds_window():
    md_lord = "Jupiter"
    m_start = datetime.date(2022, 1, 1)
    m_end = datetime.date(2038, 1, 1)
    ant = calculate_antardashas(md_lord, m_start, m_end)
    on = datetime.date(2030, 6, 1)
    cur, nxt = get_current_and_next_antardasha(ant, on)
    assert cur is not None
    s, e = _parse(cur)
    assert s <= on <= e
    if nxt:
        assert datetime.date.fromisoformat(nxt["start"]) >= e


def test_invalid_inputs_return_empty():
    assert calculate_antardashas("NotAPlanet", datetime.date(2020, 1, 1), datetime.date(2021, 1, 1)) == []
    assert calculate_antardashas("Sun", datetime.date(2021, 1, 1), datetime.date(2020, 1, 1)) == []
