"""KG-TL — unit tests for the Event-timeline localization logic.

DB-free coverage of the pieces the spec flags as good unit targets:
  - the on-demand cache coalesce-read (hit / miss / stale source_hash)
  - the participant decoration (translated vs source-fallback per slot)
  - source_hash stability + the upsert RowsAffected parsing
  - the enricher language threading (M1)

Neo4j / Postgres / glossary / translation are faked (AsyncMock), so these run
without any live infra (mirrors the other unit suites).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.clients.chapter_title_enricher import enrich_events_with_chapter_titles
from app.db.neo4j_repos.events import Event
from app.db.repositories.event_text_translations import (
    EVENT_TEXT_FIELDS,
    EventTextTranslationsRepo,
    source_hash,
)
from app.labels import timeline_localizer
from app.labels.timeline_localizer import localize_event_text, localize_participants
from uuid import UUID, uuid4


def _evt(
    *,
    ident: str = "evt-1",
    project_id: str | None = None,
    title: str = "桥上的决斗",
    summary: str | None = "主角在桥上击败了对手。",
    time_cue: str | None = "次日清晨",
    participants: list[str] | None = None,
) -> Event:
    return Event(
        id=ident,
        user_id="user-1",
        project_id=project_id,
        title=title,
        canonical_title=title,
        summary=summary,
        time_cue=time_cue,
        participants=participants or [],
        confidence=0.9,
        source_types=["chapter"],
    )


# ── source_hash ──────────────────────────────────────────────────────────────


# ── AC-T5: canonical response stays byte-identical (no new keys) ─────────────


def test_event_serialization_omits_kg_tl_fields_when_unset():
    """No reader language ⇒ the 8 KG-TL fields are None ⇒ they must NOT appear in
    the serialized wire shape (back-compat, AC-T5)."""
    dumped = _evt().model_dump()
    for f in (
        "participants_localized",
        "participants_translated",
        "summary_localized",
        "summary_translated",
        "time_cue_localized",
        "time_cue_translated",
        "title_localized",
        "title_translated",
    ):
        assert f not in dumped
    # the canonical fields are still present (we didn't drop everything).
    assert "summary" in dumped and "participants" in dumped


def test_event_serialization_includes_kg_tl_fields_once_localized():
    """When localization populated even one field, ALL 8 serialize (the FE needs
    the parallel arrays + flags together)."""
    e = _evt()
    e.summary_localized = "Cốt truyện."
    e.summary_translated = True
    dumped = e.model_dump()
    assert dumped["summary_localized"] == "Cốt truyện."
    assert dumped["summary_translated"] is True
    # the other (still-None) KG-TL fields are present too (full parallel shape).
    assert "participants_localized" in dumped
    assert "title_translated" in dumped


def test_source_hash_is_stable_and_distinct():
    assert source_hash("abc") == source_hash("abc")
    assert source_hash("abc") != source_hash("abd")
    # hex sha256 → 64 chars
    assert len(source_hash("abc")) == 64


# ── M1: enricher threads language ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enricher_forwards_language_to_client():
    cid = uuid4()
    events = [_evt(ident="e1")]
    events[0].chapter_id = str(cid)
    book_client = MagicMock()
    book_client.get_chapter_titles = AsyncMock(return_value={cid: "Chương 5 — Giải cứu"})
    await enrich_events_with_chapter_titles(events, book_client, language="vi")
    # language must reach the client as a kwarg (the sibling-language lookup).
    _, kwargs = book_client.get_chapter_titles.call_args
    assert kwargs.get("language") == "vi"
    assert events[0].chapter_title == "Chương 5 — Giải cứu"


@pytest.mark.asyncio
async def test_enricher_language_none_is_legacy():
    cid = uuid4()
    events = [_evt(ident="e1")]
    events[0].chapter_id = str(cid)
    book_client = MagicMock()
    book_client.get_chapter_titles = AsyncMock(return_value={cid: "Chapter 5"})
    await enrich_events_with_chapter_titles(events, book_client, language=None)
    _, kwargs = book_client.get_chapter_titles.call_args
    assert kwargs.get("language") is None


# ── M2: participant decoration ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_participants_localized_marks_per_slot(monkeypatch):
    """A name with a glossary translation → localized + translated=True; an
    unresolved/untranslated name → source + translated=False (AC-T3)."""
    events = [_evt(participants=["凯", "赵", "无名"])]

    # Fake the Neo4j name→entity inversion: 凯 and 赵 anchor; 无名 doesn't.
    async def fake_resolve(*, user_id, project_id, names):
        return {"凯": "gid-kai", "赵": "gid-zhao"}

    monkeypatch.setattr(
        timeline_localizer, "_resolve_names_to_entity_ids", fake_resolve
    )

    glossary = MagicMock()
    # glossary translated only 凯; 赵 anchored but no vi translation → omitted.
    glossary.fetch_entity_display_names = AsyncMock(return_value={"gid-kai": "Khải"})

    await localize_participants(
        events,
        user_id="user-1",
        project_id="proj-1",
        book_id=uuid4(),
        language="vi",
        glossary=glossary,
    )
    e = events[0]
    assert e.participants_localized == ["Khải", "赵", "无名"]
    assert e.participants_translated == [True, False, False]


@pytest.mark.asyncio
async def test_participants_no_book_is_noop():
    """No book_id ⇒ no glossary anchor ⇒ leave the fields None (not all-false)."""
    events = [_evt(participants=["凯"])]
    glossary = MagicMock()
    glossary.fetch_entity_display_names = AsyncMock()
    await localize_participants(
        events,
        user_id="user-1",
        project_id="proj-1",
        book_id=None,
        language="vi",
        glossary=glossary,
    )
    assert events[0].participants_localized is None
    assert events[0].participants_translated is None
    glossary.fetch_entity_display_names.assert_not_called()


# ── M3: cache coalesce-read ──────────────────────────────────────────────────


class _FakeRepo:
    """Stands in for EventTextTranslationsRepo.fetch with a preset cache."""

    def __init__(self, cache):
        self._cache = cache

    async def fetch(self, *, user_id, language_code, keys):
        return {k: v for k, v in self._cache.items() if k in set(keys)}


@pytest.mark.asyncio
async def test_event_text_hit_miss_and_stale(monkeypatch):
    """summary cached + fresh hash → translated; time_cue not cached → miss
    (source + translated=False + lazy fill); title cached but STALE hash → miss."""
    e = _evt(summary="主角在桥上击败了对手。", time_cue="次日清晨", title="桥上的决斗")
    summary_hash = source_hash(e.summary)
    repo = _FakeRepo(
        {
            (e.id, "summary"): ("Cốt truyện đã thắng.", summary_hash),
            (e.id, "title"): ("TIÊU ĐỀ CŨ", "deadbeef-stale-hash"),
        }
    )
    translation = MagicMock()
    translation.translate_text = AsyncMock(return_value=None)

    # Capture the misses passed to the (fire-and-forget) fill instead of running
    # the real translate. We leave the real create_task in place (an async test
    # has a running loop) so the strong-ref bookkeeping path is exercised too.
    captured = {}

    async def fake_fill(misses, **kw):
        captured["misses"] = misses

    monkeypatch.setattr(timeline_localizer, "_fill_misses", fake_fill)

    await localize_event_text(
        [e], user_id=uuid4(), language="vi", repo=repo, translation=translation
    )
    # Let the scheduled fire-and-forget task run so the capture lands.
    import asyncio as _aio

    await _aio.sleep(0)

    assert e.summary_localized == "Cốt truyện đã thắng."
    assert e.summary_translated is True
    # time_cue: miss → source + False
    assert e.time_cue_localized == "次日清晨"
    assert e.time_cue_translated is False
    # title: stale hash → treated as miss → source + False
    assert e.title_localized == "桥上的决斗"
    assert e.title_translated is False

    # The lazy fill was handed exactly the two misses (time_cue + stale title),
    # never the fresh-hit summary.
    miss_fields = {field for (_eid, field, _src, _pid) in captured["misses"]}
    assert miss_fields == {"time_cue", "title"}


def test_event_text_fields_match_check_constraint():
    """The repo's field tuple must equal the three fields the localizer + the
    migrate.go CHECK constraint allow — a drift would silently drop a field."""
    assert set(EVENT_TEXT_FIELDS) == {"summary", "time_cue", "title"}


# ── upsert RowsAffected parsing (no DB) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_returns_true_on_rows_affected():
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="INSERT 0 1")
    repo = EventTextTranslationsRepo(pool)
    ok = await repo.upsert_machine(
        event_id="e1", field="summary", language_code="vi",
        value="x", src_hash="h", user_id=uuid4(), project_id=None,
    )
    assert ok is True


@pytest.mark.asyncio
async def test_upsert_returns_false_when_verified_row_preserved():
    """ON CONFLICT WHERE confidence<>'verified' suppressed the update →
    'INSERT 0 0' → False (skipped, verified kept)."""
    pool = MagicMock()
    pool.execute = AsyncMock(return_value="INSERT 0 0")
    repo = EventTextTranslationsRepo(pool)
    ok = await repo.upsert_machine(
        event_id="e1", field="summary", language_code="vi",
        value="x", src_hash="h", user_id=uuid4(), project_id=None,
    )
    assert ok is False
