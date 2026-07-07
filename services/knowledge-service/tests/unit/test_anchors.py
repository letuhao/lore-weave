"""M-recall — unit tests for the CJK/VI Aho-Corasick anchor resolver.

Covers the non-Latin gate, the longest-match tiling / dedup / cap of
`resolve_anchors`, and the per-project cache + degrade paths of `get_anchor_index`
(the load itself is mocked; the live end-to-end path is smoke-tested against the
real wangu graph)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

ahocorasick = pytest.importorskip("ahocorasick")

from app.context import anchors
from app.context.anchors import (
    get_anchor_index,
    get_project_protagonist,
    has_non_ascii_letter,
    has_protagonist_role,
    resolve_anchors,
)


def _automaton(pairs):
    """Build a real automaton from (surface, canonical) pairs — mirroring
    get_anchor_index's value shape (canonical, surface_len)."""
    a = ahocorasick.Automaton()
    for surface, canon in pairs:
        a.add_word(surface, (canon, len(surface)))
    a.make_automaton()
    return a


# ── has_non_ascii_letter (the gate) ─────────────────────────────────────────


@pytest.mark.parametrize("text", ["九王子修炼什么武功？", "林泞姗", "Cửu U Ma Cơ", "café"])
def test_gate_true_for_non_latin(text):
    assert has_non_ascii_letter(text) is True


@pytest.mark.parametrize("text", ["what weapon does the girl own", "Zhang Ruochen?", "", "123 !!!"])
def test_gate_false_for_pure_ascii(text):
    assert has_non_ascii_letter(text) is False


# ── resolve_anchors (tiling / dedup / cap) ──────────────────────────────────


def test_longest_match_drops_nested_shorter():
    """王子 nested inside 九王子 at the same span is dropped."""
    auto = _automaton([("九王子", "九王子"), ("王子", "王子"), ("张若尘", "张若尘")])
    got = resolve_anchors(auto, "九王子修炼什么武功？张若尘也在", max_anchors=12, min_len=2)
    assert got == ["九王子", "张若尘"]


def test_standalone_short_name_kept():
    """王子 nested in 九王子 is dropped, but a standalone 王子 later is kept."""
    auto = _automaton([("九王子", "九王子"), ("王子", "王子")])
    got = resolve_anchors(auto, "九王子和另一个王子", max_anchors=12, min_len=2)
    assert got == ["九王子", "王子"]


def test_alias_emits_canonical_name():
    """A surface alias in the text resolves to the canonical anchor value."""
    auto = _automaton([("明帝", "云武郡王"), ("云武郡王", "云武郡王")])
    got = resolve_anchors(auto, "明帝是谁", max_anchors=12, min_len=2)
    assert got == ["云武郡王"]


def test_dedup_same_name_multiple_occurrences():
    auto = _automaton([("张若尘", "张若尘")])
    got = resolve_anchors(auto, "张若尘打败了张若尘的对手，张若尘赢了", max_anchors=12, min_len=2)
    assert got == ["张若尘"]


def test_cap_limits_anchor_count():
    auto = _automaton([(n, n) for n in ["甲", "乙一", "丙二", "丁三", "戊四"]])
    got = resolve_anchors(auto, "乙一丙二丁三戊四", max_anchors=2, min_len=2)
    assert len(got) == 2
    assert got == ["乙一", "丙二"]


def test_min_len_drops_single_char():
    auto = _automaton([("王", "王"), ("九王子", "九王子")])
    got = resolve_anchors(auto, "九王子", max_anchors=12, min_len=2)
    assert got == ["九王子"]  # the 1-char 王 match is filtered by min_len


def test_empty_automaton_or_message():
    assert resolve_anchors(None, "九王子", max_anchors=12, min_len=2) == []
    auto = _automaton([("张若尘", "张若尘")])
    assert resolve_anchors(auto, "", max_anchors=12, min_len=2) == []


# ── get_anchor_index (cache + degrade) ──────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_cache():
    anchors.clear_anchor_cache()
    yield
    anchors.clear_anchor_cache()


def _patch_session(monkeypatch):
    @asynccontextmanager
    async def fake_session():
        yield MagicMock()
    monkeypatch.setattr("app.context.anchors.neo4j_session", fake_session)


@pytest.mark.asyncio
async def test_index_builds_and_caches(monkeypatch):
    _patch_session(monkeypatch)
    loader = AsyncMock(return_value=[("九王子", []), ("张若尘", ["尘哥"])])
    monkeypatch.setattr("app.context.anchors.list_project_entity_names", loader)

    a1 = await get_anchor_index("u", "p", ttl_s=300.0)
    assert a1 is not None
    assert resolve_anchors(a1, "九王子和尘哥", max_anchors=12, min_len=2) == ["九王子", "张若尘"]
    # second call within TTL is served from cache (no reload)
    a2 = await get_anchor_index("u", "p", ttl_s=300.0)
    assert a2 is a1
    loader.assert_awaited_once()


@pytest.mark.asyncio
async def test_ttl_expiry_reloads(monkeypatch):
    _patch_session(monkeypatch)
    loader = AsyncMock(return_value=[("九王子", [])])
    monkeypatch.setattr("app.context.anchors.list_project_entity_names", loader)
    clock = {"t": 1000.0}
    monkeypatch.setattr("app.context.anchors.time.monotonic", lambda: clock["t"])

    await get_anchor_index("u", "p", ttl_s=300.0)
    clock["t"] += 301.0  # past TTL
    await get_anchor_index("u", "p", ttl_s=300.0)
    assert loader.await_count == 2


@pytest.mark.asyncio
async def test_empty_project_returns_none_cached(monkeypatch):
    _patch_session(monkeypatch)
    loader = AsyncMock(return_value=[])
    monkeypatch.setattr("app.context.anchors.list_project_entity_names", loader)
    assert await get_anchor_index("u", "p", ttl_s=300.0) is None
    # cached miss — not reloaded within TTL
    assert await get_anchor_index("u", "p", ttl_s=300.0) is None
    loader.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_failure_degrades_to_none(monkeypatch):
    _patch_session(monkeypatch)
    loader = AsyncMock(side_effect=RuntimeError("neo4j down"))
    monkeypatch.setattr("app.context.anchors.list_project_entity_names", loader)
    assert await get_anchor_index("u", "p", ttl_s=300.0) is None


# ── has_protagonist_role (role gate) ────────────────────────────────────────


@pytest.mark.parametrize("msg", [
    "主角的母亲是谁？", "主人公修炼什么功法", "男主是谁",
    "who is the protagonist's mother", "the main character's weapon",
    "mẹ của nhân vật chính là ai",
])
def test_protagonist_role_detected(msg):
    assert has_protagonist_role(msg) is True


@pytest.mark.parametrize("msg", [
    "那位重生的少年修炼的功法",   # 少年 is generic — deliberately NOT a protagonist term
    "张若尘的父亲是谁",           # named, no role term
    "who does the girl marry",
    "云武郡王有哪几个儿子",
])
def test_non_protagonist_message_not_detected(msg):
    assert has_protagonist_role(msg) is False


# ── get_project_protagonist (cache + degrade) ───────────────────────────────


@pytest.mark.asyncio
async def test_protagonist_resolves_and_caches(monkeypatch):
    _patch_session(monkeypatch)
    resolver = AsyncMock(return_value="张若尘")
    monkeypatch.setattr("app.context.anchors.get_most_connected_entity", resolver)
    assert await get_project_protagonist("u", "p", ttl_s=300.0) == "张若尘"
    assert await get_project_protagonist("u", "p", ttl_s=300.0) == "张若尘"
    resolver.assert_awaited_once()  # second call served from cache


@pytest.mark.asyncio
async def test_protagonist_degrades_to_none_on_failure(monkeypatch):
    _patch_session(monkeypatch)
    resolver = AsyncMock(side_effect=RuntimeError("neo4j down"))
    monkeypatch.setattr("app.context.anchors.get_most_connected_entity", resolver)
    assert await get_project_protagonist("u", "p", ttl_s=300.0) is None
