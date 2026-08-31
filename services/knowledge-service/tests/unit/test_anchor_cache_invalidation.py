"""T39 — the anchor cache is invalidated by EVENT, not only by a 300-second guess.

The two caches in `context/anchors.py` were TTL-only. The service already receives
`glossary.entity_updated` and `.deleted` and syncs the node — and then left the anchor
dictionary describing the world as it was up to five minutes ago, *while the code that knew
about the change was running*. For a delete that is the worse direction: the removed name
stays anchorable.

The TTL is deliberately kept as the backstop. Events can be missed — a consumer restart, a
dropped delivery — and a cache with no expiry would then be wrong until the process dies.
"""
from __future__ import annotations

from app.context import anchors


def test_invalidate_drops_only_the_named_project():
    """Per-project, not a global clear. Dropping every project's automaton on one book's
    edit turns a targeted invalidation into a stampede on a busy host — the cure being
    worse than the 300 seconds it replaces."""
    anchors.clear_anchor_cache()
    anchors._CACHE[("u1", "p1")] = (0.0, "automaton-1")
    anchors._CACHE[("u1", "p2")] = (0.0, "automaton-2")
    anchors._PROTAGONIST_CACHE[("u1", "p1")] = (0.0, "Kai")
    anchors._PROTAGONIST_CACHE[("u1", "p2")] = (0.0, "Mira")

    anchors.invalidate_anchor_cache("u1", "p1")

    assert ("u1", "p1") not in anchors._CACHE
    assert ("u1", "p1") not in anchors._PROTAGONIST_CACHE
    assert anchors._CACHE[("u1", "p2")] == (0.0, "automaton-2"), (
        "invalidating one project dropped another's automaton"
    )
    assert anchors._PROTAGONIST_CACHE[("u1", "p2")] == (0.0, "Mira")


def test_invalidating_an_absent_project_is_a_no_op():
    """A delete for a project that was never cached must not raise — the handler runs on
    every entity event, including the first one for a cold process."""
    anchors.clear_anchor_cache()
    anchors.invalidate_anchor_cache("nobody", "nothing")   # must not raise


def test_uuid_keys_are_normalised_to_the_strings_the_cache_uses():
    """The handler holds UUIDs from the database; the cache is keyed by str. Without the
    coercion the pop would silently miss and the invalidation would do NOTHING — a green
    handler, a stale cache, and no way to tell from the outside."""
    from uuid import uuid4

    u, p = uuid4(), uuid4()
    anchors.clear_anchor_cache()
    anchors._CACHE[(str(u), str(p))] = (0.0, "automaton")

    anchors.invalidate_anchor_cache(u, p)                  # type: ignore[arg-type]

    assert (str(u), str(p)) not in anchors._CACHE


# ── T39a: the WIRING, not the function ───────────────────────────────────────
#
# 🔴 The three rules above all call `invalidate_anchor_cache` directly. Measured 2026-08-14 by
# deleting the call from `handle_glossary_entity_updated`: **the entire 4233-test unit suite
# stayed green.** T39's whole point — the anchor automaton is stale NOW, not in up to 300
# seconds — could be removed and nothing would say so, which is the same defect class as
# T35e's collision guard that the loader never fed and T39's own second cache that no
# consumer calls.
#
# These drive the HANDLER and assert the cache is gone afterwards. They fail if the call is
# removed, reordered after a failing sync, or given the wrong key type.

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.events.dispatcher import EventData
from app.events.handlers import (
    handle_glossary_entity_deleted,
    handle_glossary_entity_updated,
)

_WU = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
_WP = "019f1783-ecca-7331-afab-9543762a8b68"
_WE = "019f0835-1111-7000-8000-000000000001"


def _seed_automaton(monkeypatch):
    """Put a live entry in the cache under the exact key shape the module uses."""
    from app.context import anchors
    anchors._CACHE[(_WU, _WP)] = ("sentinel-automaton", 1_000_000.0)
    return anchors


def _pool_resolving_to_the_project():
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _WP, "user_id": _WU,
        "embedding_model": None, "embedding_dimension": None,
    })
    pool.execute = AsyncMock()
    pool.fetch = AsyncMock(return_value=[])
    return pool


@pytest.mark.asyncio
async def test_the_UPDATE_handler_actually_invalidates(monkeypatch):
    anchors = _seed_automaton(monkeypatch)
    pool = _pool_resolving_to_the_project()
    event = EventData(
        stream="loreweave:events:glossary", message_id="1-0",
        event_type="glossary.entity_updated", aggregate_id=_WE,
        payload={"book_id": _WP, "glossary_entity_id": _WE, "name": "Kai",
                 "kind": "character", "aliases": [], "op": "updated",
                 "source_type": "glossary"},
        source="glossary-service", raw={},
    )
    # The sync RAISES on purpose. B9's decision is that invalidation happens BEFORE the sync,
    # because a cache still holding the pre-edit dictionary after a FAILED write is the worse
    # of the two states. A test with a happy-path sync could not tell the two orders apart.
    monkeypatch.setattr("app.extraction.glossary_sync.sync_glossary_entity_to_neo4j",
                        AsyncMock(side_effect=RuntimeError("sync exploded")))
    with patch("app.config.settings") as ms:
        ms.neo4j_uri = "bolt://fake"
        try:
            await handle_glossary_entity_updated(event, pool=pool)
        except Exception:  # noqa: BLE001 — the sync failure is the point, not the outcome
            pass

    assert (_WU, _WP) not in anchors._CACHE, (
        "the update handler did not invalidate the anchor cache. The automaton keeps "
        "describing the pre-edit entity set for up to the TTL while the code that knew about "
        "the change has already run — which is exactly what T39 exists to remove.")


@pytest.mark.asyncio
async def test_the_DELETE_handler_actually_invalidates(monkeypatch):
    """The worse direction of the two: without this the REMOVED name stays anchorable for the
    rest of the window, so extraction keeps anchoring onto an entity the author deleted."""
    anchors = _seed_automaton(monkeypatch)
    pool = _pool_resolving_to_the_project()
    event = EventData(
        stream="loreweave:events:glossary", message_id="2-0",
        event_type="glossary.entity_deleted", aggregate_id=_WE,
        payload={"book_id": _WP, "glossary_entity_id": _WE},
        source="glossary-service", raw={},
    )
    with patch("app.config.settings") as ms:
        ms.neo4j_uri = "bolt://fake"
        try:
            await handle_glossary_entity_deleted(event, pool=pool)
        except Exception:  # noqa: BLE001
            pass

    assert (_WU, _WP) not in anchors._CACHE, (
        "the delete handler did not invalidate the anchor cache — the deleted name stays "
        "anchorable for the rest of the TTL window.")
