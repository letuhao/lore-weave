"""C18 — Cypher source-scan regression locks for event_date_iso.

These tests grep the Cypher string constants to assert structural
invariants that don't surface as Pydantic-model behavior. Mirrors the
test_migrate_ddl.py source-scan pattern: any future edit that drops
the precision-preserving CASE would break the test loudly rather
than silently downgrading the stored precision in production.
"""

from __future__ import annotations

import re

from app.db.neo4j_repos.events import _MERGE_EVENT_CYPHER


def test_merge_event_cypher_sets_event_date_iso_on_create():
    """ON CREATE branch must SET event_date_iso = $event_date_iso so
    a new node carries the LLM-extracted date."""
    assert "e.event_date_iso = $event_date_iso" in _MERGE_EVENT_CYPHER


def test_merge_event_cypher_on_match_uses_precision_preserving_case():
    """C18 review-impl HIGH-1 regression lock: the ON MATCH branch
    MUST prefer the longer ISO string when both old and new are
    non-null. A coalesce-only path would let a year-only re-mention
    downgrade a previously-stored full date."""
    # Strip whitespace so multi-line CASE matches against a single
    # canonical form regardless of formatting tweaks.
    flat = re.sub(r"\s+", " ", _MERGE_EVENT_CYPHER)
    # The CASE block must contain all three branches:
    #   - new param NULL → keep existing
    #   - existing NULL → take new
    #   - both non-null → prefer longer (more precise)
    assert "WHEN $event_date_iso IS NULL THEN e.event_date_iso" in flat
    assert "WHEN e.event_date_iso IS NULL THEN $event_date_iso" in flat
    assert (
        "WHEN size($event_date_iso) > size(e.event_date_iso) "
        "THEN $event_date_iso"
    ) in flat


def test_merge_event_cypher_on_match_does_not_use_plain_coalesce_for_date():
    """Negative regression lock: a future refactor might reintroduce
    the simpler ``coalesce($event_date_iso, e.event_date_iso)`` —
    that's the bug HIGH-1 fixed. Catch it at test-time."""
    flat = re.sub(r"\s+", " ", _MERGE_EVENT_CYPHER)
    assert "coalesce($event_date_iso, e.event_date_iso)" not in flat
