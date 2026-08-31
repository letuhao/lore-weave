"""The rebuild's REPORT must reconcile against the graph it produced.

Found by the QC-7 drill on a real book: 3187 rows written, `failed=0`, and 3171 nodes in
the graph. Nothing was lost — `resolve_or_merge_entity` is keyed on the CANONICAL name, and
16 rows were punctuation variants and honorific forms the canonicaliser folds together on
purpose. The graph was right and the REPORT was wrong.

During a disaster the report is all an operator has. "3187 written, 0 failed" against 3171
nodes reads as silent data loss to anyone who counts afterwards, and the only other way to
learn the truth is to count the graph and subtract — the reconciliation nobody should have
to invent mid-recovery.
"""
from __future__ import annotations

import pytest
from loreweave_extraction.canonical import canonicalize_entity_name

from app.adapters.fake_graph_store import FakeGraphStore
from app.jobs.graph_rebuild import rebuild_entities_from_glossary

USER = "11111111-1111-1111-1111-111111111111"
PROJECT = "22222222-2222-2222-2222-222222222222"


def _folding_pair() -> tuple[str, str]:
    """Two spellings the canonicaliser folds into one identity.

    Derived from the canonicaliser rather than hardcoded: if its folding rules change, this
    test should follow them, not assert against a spelling that stopped colliding.
    """
    for a, b in (("Arthur", "Arthur."), ("Arthur", " Arthur "), ("Arthur", "arthur")):
        if canonicalize_entity_name(a) == canonicalize_entity_name(b):
            return a, b
    pytest.skip("no folding pair available from the canonicaliser")


@pytest.mark.asyncio
async def test_two_rows_that_fold_are_reported_as_one_node():
    a, b = _folding_pair()
    store = FakeGraphStore()

    stats = await rebuild_entities_from_glossary(
        store, user_id=USER, project_id=PROJECT,
        entities=[{"id": "1", "name": a, "kind": "character"},
                  {"id": "2", "name": b, "kind": "character"}])

    assert stats.entities_written == 2, "both rows were processed"
    assert stats.merged_onto_existing == 1, "the fold was not counted"
    assert stats.distinct_nodes == 1
    # THE assertion: the claim reconciles against the graph. Everything above is bookkeeping
    # that only matters because this must hold.
    assert stats.distinct_nodes == store.entity_count()


@pytest.mark.asyncio
async def test_distinct_rows_report_no_merges():
    store = FakeGraphStore()
    stats = await rebuild_entities_from_glossary(
        store, user_id=USER, project_id=PROJECT,
        entities=[{"id": "1", "name": "Arthur", "kind": "character"},
                  {"id": "2", "name": "Merlin", "kind": "character"}])
    assert stats.merged_onto_existing == 0
    assert stats.distinct_nodes == store.entity_count() == 2


@pytest.mark.asyncio
async def test_a_nameless_row_is_failed_not_merged():
    """The two counters must not absorb each other: an unprojectable row is a FAILURE, and
    counting it as a merge would make a broken row look like a tidy one."""
    store = FakeGraphStore()
    stats = await rebuild_entities_from_glossary(
        store, user_id=USER, project_id=PROJECT,
        entities=[{"id": "1", "name": "Arthur", "kind": "character"},
                  {"id": "2", "name": "", "kind": "character"}])
    assert stats.failed == 1 and stats.merged_onto_existing == 0
    assert stats.distinct_nodes == store.entity_count() == 1
