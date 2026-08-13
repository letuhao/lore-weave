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
