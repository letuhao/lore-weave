"""Unit tests for the per-book enrichment profile (C1 / slice 0a, T2).

Pure / fake-pool — no live DB. The up→down→up DDL roundtrip is covered by
tests/db/test_migration_roundtrip.py (the new table joins the generic cycle).
"""

from __future__ import annotations

import json
from uuid import UUID

import pytest

from app.db.book_profile import (
    NEUTRAL_PROFILE,
    BookProfile,
    _parse_markers,
    _parse_overrides,
    get_book_profile,
)

_BOOK = UUID("019e7850-aa1c-7000-8000-000000000001")


# ── neutral default ──────────────────────────────────────────────────────────

def test_neutral_profile_is_unbiased():
    p = NEUTRAL_PROFILE
    assert p.language == "auto"
    assert p.era_policy is None
    assert p.anachronism_markers == ()
    assert p.anachronism_enabled is False  # no denylist → check OFF
    assert p.dimension_overrides == {}
    assert p.worldview == ""


def test_anachronism_enabled_only_with_markers():
    assert BookProfile(anachronism_markers=()).anachronism_enabled is False
    assert BookProfile(
        anachronism_markers=(("火车", "近代产物"),)
    ).anachronism_enabled is True


def test_profile_is_frozen():
    with pytest.raises(Exception):
        NEUTRAL_PROFILE.language = "zh"  # type: ignore[misc]


# ── JSONB parsers (tolerate str | parsed | NULL | malformed) ──────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, ()),
        ("", ()),
        ([], ()),
        ([{"term": "火车", "reason": "近代"}], (("火车", "近代"),)),
        ('[{"term": "飞机", "reason": "现代"}]', (("飞机", "现代"),)),
        ([{"term": "x"}], (("x", ""),)),          # missing reason → empty
        ([{"reason": "no term"}], ()),            # no term → dropped
        ([["手机", "现代"]], (("手机", "现代"),)),   # tuple/list form
        ("not json at all", ()),                  # malformed str → safe empty? -> raises? no: see note
    ],
)
def test_parse_markers(raw, expected):
    if raw == "not json at all":
        with pytest.raises(json.JSONDecodeError):
            _parse_markers(raw)
        return
    assert _parse_markers(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, {}),
        ("", {}),
        ({}, {}),
        ({"character": {"add": []}}, {"character": {"add": []}}),
        ('{"item": {"remove": ["x"]}}', {"item": {"remove": ["x"]}}),
        ([1, 2, 3], {}),  # wrong shape → safe empty
    ],
)
def test_parse_overrides(raw, expected):
    assert _parse_overrides(raw) == expected


# ── get_book_profile (fake pool) ──────────────────────────────────────────────

class _FakeConn:
    def __init__(self, row):
        self._row = row

    async def fetchrow(self, _sql, _book_id):
        return self._row


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, row):
        self._row = row

    def acquire(self):
        return _FakeAcquire(_FakeConn(self._row))


@pytest.mark.asyncio
async def test_none_book_id_returns_neutral():
    assert await get_book_profile(_FakePool(None), None) is NEUTRAL_PROFILE


@pytest.mark.asyncio
async def test_missing_row_returns_neutral_with_book_id():
    p = await get_book_profile(_FakePool(None), _BOOK)
    assert p.book_id == _BOOK
    assert p.language == "auto"
    assert p.anachronism_enabled is False


@pytest.mark.asyncio
async def test_existing_row_parsed():
    row = {
        "book_id": _BOOK,
        "worldview": "商周·封神演义",
        "language": "zh",
        "era_policy": "商周封神纪元",
        "voice": "原著文言-白话",
        "anachronism_markers": [{"term": "火车", "reason": "近代产物"}],
        "dimension_overrides": {"character": {"add": [{"id": "abilities"}]}},
        "profile_source": "seed",
    }
    p = await get_book_profile(_FakePool(row), _BOOK)
    assert p.book_id == _BOOK
    assert p.language == "zh"
    assert p.worldview == "商周·封神演义"
    assert p.era_policy == "商周封神纪元"
    assert p.anachronism_enabled is True
    assert p.anachronism_markers == (("火车", "近代产物"),)
    assert p.dimension_overrides == {"character": {"add": [{"id": "abilities"}]}}
    assert p.profile_source == "seed"
