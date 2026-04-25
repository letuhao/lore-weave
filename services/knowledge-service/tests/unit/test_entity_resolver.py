"""K13.0 resolver — unit tests for anchor-aware entity resolution."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.db.neo4j_repos.entities import Entity
from app.extraction.anchor_loader import Anchor
from app.extraction.entity_resolver import (
    build_anchor_index,
    normalize_kind_for_anchor_lookup,
    resolve_or_merge_entity,
)

USER_ID = "user-1"
PROJECT_ID = "project-1"


def _anchor(name: str, kind: str = "character", aliases: tuple[str, ...] = ()) -> Anchor:
    gid = str(uuid4())
    return Anchor(
        canonical_id=f"canon-{name.lower()}-{kind}",
        glossary_entity_id=gid,
        name=name,
        kind=kind,
        aliases=aliases,
    )


def test_build_anchor_index_expands_aliases():
    a = _anchor("Arthur", aliases=("Art", "King Arthur"))
    idx = build_anchor_index([a])
    assert ("arthur", "character") in idx
    assert ("art", "character") in idx
    assert ("king arthur", "character") in idx
    # Same anchor object returned for every key.
    assert idx[("arthur", "character")] is a
    assert idx[("art", "character")] is a


def test_build_anchor_index_kind_qualified():
    """Same surface form for different kinds must not collide."""
    person = _anchor("Phoenix", kind="person")
    org = _anchor("Phoenix", kind="organization")
    idx = build_anchor_index([person, org])
    assert idx[("phoenix", "person")] is person
    assert idx[("phoenix", "organization")] is org


def test_build_anchor_index_collision_warns_and_keeps_first(caplog):
    """Two anchors of the same kind sharing an alias → first wins, WARN."""
    first = _anchor("Arthur", aliases=("King",))
    second = _anchor("Arthuria", aliases=("King",))
    import logging
    with caplog.at_level(logging.WARNING, logger="app.extraction.entity_resolver"):
        idx = build_anchor_index([first, second])
    assert idx[("king", "character")] is first
    collision_logs = [r for r in caplog.records if "alias collision" in r.getMessage()]
    assert len(collision_logs) == 1


def test_build_anchor_index_dedupes_same_anchor():
    """Same anchor appearing twice in the input is not a collision."""
    a = _anchor("Arthur", aliases=("Art",))
    idx = build_anchor_index([a, a])
    # No duplicate keys added; both references still resolve to `a`.
    assert idx[("arthur", "character")] is a
    assert idx[("art", "character")] is a


@pytest.mark.asyncio
async def test_resolve_hits_anchor_and_skips_merge(monkeypatch):
    a = _anchor("Arthur", aliases=("Art",))
    idx = build_anchor_index([a])

    async def must_not_call(*args, **kwargs):
        raise AssertionError("merge_entity must not run on anchor hit")

    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity", must_not_call,
    )

    ent = await resolve_or_merge_entity(
        MagicMock(), idx,
        user_id=USER_ID, project_id=PROJECT_ID,
        name="Arthur", kind="person",
        source_type="chapter", confidence=0.8,
    )
    assert isinstance(ent, Entity)
    assert ent.id == a.canonical_id
    assert ent.glossary_entity_id == a.glossary_entity_id
    assert ent.anchor_score == 1.0


@pytest.mark.asyncio
async def test_resolve_alias_hit(monkeypatch):
    """Extraction surface 'Art' matches 'Arthur' via alias."""
    a = _anchor("Arthur", aliases=("Art",))
    idx = build_anchor_index([a])

    async def must_not_call(*args, **kwargs):
        raise AssertionError("alias hit must skip merge")

    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity", must_not_call,
    )

    ent = await resolve_or_merge_entity(
        MagicMock(), idx,
        user_id=USER_ID, project_id=PROJECT_ID,
        name="Art", kind="person",
        source_type="chapter",
    )
    assert ent.id == a.canonical_id


@pytest.mark.asyncio
async def test_resolve_miss_calls_merge(monkeypatch):
    """No match → merge_entity runs and its result is returned."""
    idx = build_anchor_index([_anchor("Arthur")])
    merge_calls: list[dict] = []

    async def fake_merge(session, **kwargs):
        merge_calls.append(kwargs)
        return Entity(
            id="newly-merged",
            user_id=kwargs["user_id"],
            project_id=kwargs["project_id"],
            name=kwargs["name"],
            canonical_name=kwargs["name"].lower(),
            kind=kwargs["kind"],
        )

    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity", fake_merge,
    )

    ent = await resolve_or_merge_entity(
        MagicMock(), idx,
        user_id=USER_ID, project_id=PROJECT_ID,
        name="Lancelot", kind="person",
        source_type="chapter", confidence=0.7,
    )
    assert ent.id == "newly-merged"
    assert len(merge_calls) == 1
    assert merge_calls[0]["name"] == "Lancelot"
    assert merge_calls[0]["confidence"] == 0.7


@pytest.mark.asyncio
async def test_resolve_kind_miss_calls_merge(monkeypatch):
    """Same name, different kind → NOT an anchor hit."""
    idx = build_anchor_index([_anchor("Phoenix", kind="character")])
    calls = 0

    async def fake_merge(session, **kwargs):
        nonlocal calls
        calls += 1
        return Entity(
            id="minted",
            user_id=kwargs["user_id"],
            project_id=kwargs["project_id"],
            name=kwargs["name"],
            canonical_name=kwargs["name"].lower(),
            kind=kwargs["kind"],
        )

    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity", fake_merge,
    )

    await resolve_or_merge_entity(
        MagicMock(), idx,
        user_id=USER_ID, project_id=PROJECT_ID,
        name="Phoenix", kind="organization",
        source_type="chapter",
    )
    assert calls == 1


# ── kind vocabulary normalization (Pass 2 LLM → glossary kind_code) ──


def test_normalize_kind_maps_extractor_to_glossary():
    """LLM extractor vocabulary → glossary kind_code."""
    assert normalize_kind_for_anchor_lookup("person") == "character"
    assert normalize_kind_for_anchor_lookup("place") == "location"
    assert normalize_kind_for_anchor_lookup("artifact") == "item"
    assert normalize_kind_for_anchor_lookup("concept") == "terminology"


def test_normalize_kind_passes_through_when_already_aligned():
    """Pass 1 writers emit glossary kinds natively — no-op map."""
    assert normalize_kind_for_anchor_lookup("character") == "character"
    assert normalize_kind_for_anchor_lookup("location") == "location"
    assert normalize_kind_for_anchor_lookup("organization") == "organization"


def test_normalize_kind_passes_through_unknown():
    """Tenant-custom or 'other' kinds stay unchanged → natural miss."""
    assert normalize_kind_for_anchor_lookup("other") == "other"
    assert normalize_kind_for_anchor_lookup("custom_tenant_kind") == "custom_tenant_kind"


@pytest.mark.asyncio
async def test_resolve_pass2_person_hits_character_anchor(monkeypatch):
    """Pass 2 LLM emits kind='person'; glossary anchor has
    kind='character'. With normalization the resolver MUST still
    hit the anchor — this is the core K13.0 acceptance for LLM
    extractors.
    """
    anchor = _anchor("Arthur", kind="character", aliases=("Art",))
    idx = build_anchor_index([anchor])

    async def must_not_call(*args, **kwargs):
        raise AssertionError(
            "Pass 2 LLM 'person' must normalize to 'character' and hit anchor"
        )

    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity", must_not_call,
    )

    # LLM-style surface form + LLM kind vocabulary.
    ent = await resolve_or_merge_entity(
        MagicMock(), idx,
        user_id=USER_ID, project_id=PROJECT_ID,
        name="Arthur", kind="person",
        source_type="chapter",
    )
    assert ent.id == anchor.canonical_id
    assert ent.kind == "character"  # returned with the anchor's glossary kind


@pytest.mark.asyncio
async def test_resolve_pass2_place_hits_location_anchor(monkeypatch):
    anchor = _anchor("Camelot", kind="location")
    idx = build_anchor_index([anchor])

    async def must_not_call(*args, **kwargs):
        raise AssertionError("place must normalize to location")

    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity", must_not_call,
    )

    ent = await resolve_or_merge_entity(
        MagicMock(), idx,
        user_id=USER_ID, project_id=PROJECT_ID,
        name="Camelot", kind="place",
        source_type="chapter",
    )
    assert ent.id == anchor.canonical_id


# ── Prometheus counters ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_increments_hit_counter_on_anchor_hit(monkeypatch):
    from app.metrics import anchor_resolver_hits_total

    anchor = _anchor("Arthur", kind="character")
    idx = build_anchor_index([anchor])

    # Bypass the "merge must not call" guard — we're checking the hit path.
    async def fake_merge(*a, **kw):
        raise AssertionError("miss path should not fire on hit")

    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity", fake_merge,
    )

    before = anchor_resolver_hits_total.labels(kind="character")._value.get()
    await resolve_or_merge_entity(
        MagicMock(), idx,
        user_id=USER_ID, project_id=PROJECT_ID,
        name="Arthur", kind="person",  # LLM kind normalizes to character
        source_type="chapter",
    )
    after = anchor_resolver_hits_total.labels(kind="character")._value.get()
    assert after - before == 1


@pytest.mark.asyncio
async def test_resolve_increments_miss_counter_on_no_match(monkeypatch):
    from app.metrics import anchor_resolver_misses_total

    idx = build_anchor_index([_anchor("Arthur", kind="character")])

    async def fake_merge(session, **kwargs):
        return Entity(
            id="minted",
            user_id=kwargs["user_id"],
            project_id=kwargs["project_id"],
            name=kwargs["name"],
            canonical_name=kwargs["name"].lower(),
            kind=kwargs["kind"],
        )

    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity", fake_merge,
    )

    # No anchor for "Lancelot" → miss. Lookup kind is "character" (normalized
    # from "person"), so the miss is labelled "character".
    before = anchor_resolver_misses_total.labels(kind="character")._value.get()
    await resolve_or_merge_entity(
        MagicMock(), idx,
        user_id=USER_ID, project_id=PROJECT_ID,
        name="Lancelot", kind="person",
        source_type="chapter",
    )
    after = anchor_resolver_misses_total.labels(kind="character")._value.get()
    assert after - before == 1


@pytest.mark.asyncio
async def test_resolve_does_not_bump_miss_counter_when_index_empty(monkeypatch):
    """Empty index = "no anchors available" — not a miss worth counting.

    Otherwise Mode-1 chat sessions (no book, no glossary, no anchors)
    would peg the miss counter at 100% forever, drowning out the
    hit/miss ratio signal from projects that actually have anchors.
    """
    from app.metrics import anchor_resolver_misses_total

    empty: dict = {}

    async def fake_merge(session, **kwargs):
        return Entity(
            id="minted",
            user_id=kwargs["user_id"],
            project_id=kwargs["project_id"],
            name=kwargs["name"],
            canonical_name=kwargs["name"].lower(),
            kind=kwargs["kind"],
        )

    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity", fake_merge,
    )

    before = anchor_resolver_misses_total.labels(kind="character")._value.get()
    await resolve_or_merge_entity(
        MagicMock(), empty,
        user_id=USER_ID, project_id=PROJECT_ID,
        name="Lancelot", kind="person",
        source_type="chapter",
    )
    after = anchor_resolver_misses_total.labels(kind="character")._value.get()
    assert after == before  # NOT incremented


# ── C17 alias-map redirect tests ───────────────────────────────────
# C17 tests construct a real UUID for user_id because the resolver
# calls ``UUID(user_id)`` to parameterize the alias-map lookup. The
# pre-C17 ``USER_ID = "user-1"`` works for non-alias-map paths because
# merge_entity passes user_id through as-is to Cypher.
_C17_USER_ID = str(uuid4())


@pytest.mark.asyncio
async def test_resolver_alias_map_hit_redirects_to_target(monkeypatch):
    """C17: when alias_map_repo.lookup returns a target id, the
    resolver calls merge_entity_at_id (not the SHA-hash merge_entity).
    Ensures post-merge re-extraction lands on target rather than
    resurrecting source."""
    target_id = "tgt-id-32hex"
    redirected_entity = Entity(
        id=target_id,
        user_id=USER_ID,
        project_id=PROJECT_ID,
        name="Captain Brave",
        canonical_name="brave",
        kind="person",
        aliases=["Captain Brave", "Alice"],
        glossary_entity_id=None,
        anchor_score=0.0,
    )
    alias_repo = MagicMock()
    alias_repo.lookup = AsyncMock(return_value=target_id)

    merge_at_id_mock = AsyncMock(return_value=redirected_entity)
    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity_at_id",
        merge_at_id_mock,
    )
    merge_mock = AsyncMock()
    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity",
        merge_mock,
    )

    result = await resolve_or_merge_entity(
        session=MagicMock(),
        index={},
        user_id=_C17_USER_ID,
        project_id=PROJECT_ID,
        name="Alice",
        kind="person",
        source_type="chapter",
        alias_map_repo=alias_repo,
    )

    assert result.id == target_id
    merge_at_id_mock.assert_awaited_once()
    # SHA-hash path NOT taken.
    merge_mock.assert_not_awaited()
    # Repo lookup keyed on canonicalize_entity_name("Alice") == "alice".
    lookup_kwargs = alias_repo.lookup.await_args
    # positional: (user_id, project_scope, kind, canonical_alias)
    assert lookup_kwargs.args[1] == PROJECT_ID  # project_scope = PROJECT_ID
    assert lookup_kwargs.args[2] == "person"
    assert lookup_kwargs.args[3] == "alice"


@pytest.mark.asyncio
async def test_resolver_alias_map_miss_falls_through_to_sha_hash(
    monkeypatch,
):
    """C17: lookup miss → standard SHA-hash MERGE path. Pre-C17
    behavior preserved when no merge has registered the alias."""
    fresh_entity = Entity(
        id="fresh-sha-id",
        user_id=USER_ID,
        project_id=PROJECT_ID,
        name="Brand New",
        canonical_name="brand new",
        kind="person",
        aliases=["Brand New"],
        glossary_entity_id=None,
        anchor_score=0.0,
    )
    alias_repo = MagicMock()
    alias_repo.lookup = AsyncMock(return_value=None)

    merge_at_id_mock = AsyncMock()
    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity_at_id",
        merge_at_id_mock,
    )
    merge_mock = AsyncMock(return_value=fresh_entity)
    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity",
        merge_mock,
    )

    result = await resolve_or_merge_entity(
        session=MagicMock(),
        index={},
        user_id=_C17_USER_ID,
        project_id=PROJECT_ID,
        name="Brand New",
        kind="person",
        source_type="chapter",
        alias_map_repo=alias_repo,
    )

    assert result is fresh_entity
    merge_mock.assert_awaited_once()
    merge_at_id_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolver_stale_alias_row_logs_warning_and_falls_through(
    monkeypatch, caplog,
):
    """C17 REVIEW-DESIGN catch: alias_map points at deleted entity →
    merge_entity_at_id returns None → resolver logs WARNING + falls
    through to SHA-hash MERGE so extraction still produces an entity.
    Ops can find these via the WARNING log filter."""
    import logging

    fresh_entity = Entity(
        id="fresh-sha-id",
        user_id=USER_ID,
        project_id=PROJECT_ID,
        name="Alice",
        canonical_name="alice",
        kind="person",
        aliases=["Alice"],
        glossary_entity_id=None,
        anchor_score=0.0,
    )
    alias_repo = MagicMock()
    alias_repo.lookup = AsyncMock(return_value="stale-target-id")

    # Stale: at_id helper returns None (target not found).
    merge_at_id_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity_at_id",
        merge_at_id_mock,
    )
    merge_mock = AsyncMock(return_value=fresh_entity)
    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity",
        merge_mock,
    )

    with caplog.at_level(logging.WARNING, logger="app.extraction.entity_resolver"):
        result = await resolve_or_merge_entity(
            session=MagicMock(),
            index={},
            user_id=_C17_USER_ID,
            project_id=PROJECT_ID,
            name="Alice",
            kind="person",
            source_type="chapter",
            alias_map_repo=alias_repo,
        )

    assert result is fresh_entity
    merge_at_id_mock.assert_awaited_once()
    merge_mock.assert_awaited_once()  # fall-through
    # WARNING log emitted with the alias-map message.
    stale_logs = [
        r for r in caplog.records
        if "C17 alias_map points to missing entity" in r.getMessage()
    ]
    assert len(stale_logs) == 1


@pytest.mark.asyncio
async def test_resolver_none_alias_map_repo_keeps_pre_c17_behavior(
    monkeypatch,
):
    """C17 back-compat: alias_map_repo=None (default for ~6 test
    sites that haven't been wired) skips the lookup entirely and
    behaves exactly as pre-C17."""
    fresh_entity = Entity(
        id="fresh-sha-id",
        user_id=USER_ID,
        project_id=PROJECT_ID,
        name="Alice",
        canonical_name="alice",
        kind="person",
        aliases=["Alice"],
        glossary_entity_id=None,
        anchor_score=0.0,
    )
    merge_mock = AsyncMock(return_value=fresh_entity)
    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity",
        merge_mock,
    )

    result = await resolve_or_merge_entity(
        session=MagicMock(),
        index={},
        user_id=USER_ID,
        project_id=PROJECT_ID,
        name="Alice",
        kind="person",
        source_type="chapter",
        # alias_map_repo deliberately not passed.
    )

    assert result is fresh_entity
    merge_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolver_global_scope_uses_global_string_in_lookup(
    monkeypatch,
):
    """C17 scope semantics: project_id=None → project_scope='global'
    in the lookup key (mirrors entity_canonical_id's shape)."""
    target_id = "tgt-global"
    redirected = Entity(
        id=target_id, user_id=USER_ID, project_id=None,
        name="Global Alice", canonical_name="global alice", kind="person",
        aliases=["Global Alice"], glossary_entity_id=None, anchor_score=0.0,
    )
    alias_repo = MagicMock()
    alias_repo.lookup = AsyncMock(return_value=target_id)
    monkeypatch.setattr(
        "app.extraction.entity_resolver.merge_entity_at_id",
        AsyncMock(return_value=redirected),
    )

    await resolve_or_merge_entity(
        session=MagicMock(),
        index={},
        user_id=_C17_USER_ID,
        project_id=None,
        name="Alice",
        kind="person",
        source_type="chapter",
        alias_map_repo=alias_repo,
    )

    # project_scope arg = literal 'global' (not None, not empty).
    assert alias_repo.lookup.await_args.args[1] == "global"
