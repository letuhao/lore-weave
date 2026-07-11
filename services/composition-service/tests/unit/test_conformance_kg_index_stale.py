"""WS-0.7 — composition's `index_stale` / `prose_drift`, re-keyed onto the KG pointer.

Spec: docs/specs/2026-07-11-publish-independent-kg-indexing.md §3.6 (red-team **P0-3**).

composition-service hand-copies book-service's reparse-sweeper WHERE clause in Python to
compute the `index_stale` badge. The sweeper was re-keyed onto `kg_indexed_revision_id`
(WS-0.5); if this mirror kept evaluating the OLD predicate the badge would be
**permanently stuck**:

    publish@A  →  index a draft@B
    composition (old):  editorial_status='published' AND last_parsed(B) != published(A)
                        ⇒ STALE
    sweeper     (new):  last_parsed(B) == kg_indexed(B)
                        ⇒ nothing to heal
    ⇒ the arc's conformance report stays dirty FOREVER, and the LLM-judged, token-costly
      conformance job keeps re-running against a chapter nothing can fix.

The invariant, stated once: **the badge must never fire on a chapter the sweeper cannot
heal.** These tests pin exactly that.

`_dirty_reasons` is a pure function — no DB, no HTTP.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.engine.arc_conformance_orchestrate import _dirty_reasons

_A = str(uuid4())  # the published revision
_B = str(uuid4())  # a later, draft-indexed revision


def _snap(chapters: list[dict], spec: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(input_manifest={"v": 1, "chapters": chapters, "spec": spec or {}})


def _call(*, snap, markers, chapter_ids, spec: dict | None = None):
    """_dirty_reasons with the spec fingerprint stubbed to match, so spec_drift stays
    out of the way and we assert purely on prose_drift / index_stale."""
    import app.engine.arc_conformance_orchestrate as mod

    orig = mod._spec_fingerprints
    mod._spec_fingerprints = lambda *a, **k: (spec or {})
    try:
        return _dirty_reasons(
            snap=snap,
            arc=SimpleNamespace(id=uuid4()),
            member_rows=[],
            binding_rows=[],
            chapter_ids=chapter_ids,
            markers=markers,
        )
    finally:
        mod._spec_fingerprints = orig


# ── THE P0-3 SCENARIO — acceptance §5.7 ──


def test_published_at_A_indexed_at_B_is_not_index_stale():
    """publish@A + index-draft@B ⇒ index_stale must be FALSE.

    The scenes were parsed from B and last_parsed == B, so the sweeper considers the
    chapter fresh. If composition disagreed, the badge could never clear.
    """
    cid = str(uuid4())
    markers = {
        cid: {
            "editorial_status": "published",
            "published_revision_id": _A,     # canon is still A
            "kg_indexed_revision_id": _B,    # but the KG reflects B
            "last_parsed_revision_id": _B,   # and the scene index is B — fresh
            "kg_exclude": False,
            "parse_version": 3,
        }
    }
    snap = _snap([{"chapter_id": cid, "kg_indexed_revision_id": _B,
                   "published_revision_id": _A, "parse_version": 3}])

    reasons, stale_chapters, index_stale = _call(snap=snap, markers=markers, chapter_ids=[cid])

    assert "index_stale" not in reasons, (
        "PERMANENTLY-STUCK BADGE (P0-3): composition called a chapter index-stale that "
        "the sweeper considers fresh (last_parsed == kg_indexed), so nothing can ever "
        "clear it. The mirror must repeat the sweeper's CURRENT predicate."
    )
    assert index_stale == []
    assert stale_chapters == []


def test_index_lagging_the_kg_pointer_is_stale():
    """The badge must still FIRE when the index genuinely lags what the KG reflects —
    i.e. exactly when the sweeper WOULD heal it."""
    cid = str(uuid4())
    markers = {
        cid: {
            "editorial_status": "draft",
            "published_revision_id": None,
            "kg_indexed_revision_id": _B,
            "last_parsed_revision_id": _A,  # index lags the indexed revision
            "kg_exclude": False,
            "parse_version": 1,
        }
    }
    snap = _snap([{"chapter_id": cid, "kg_indexed_revision_id": _B, "parse_version": 1}])

    reasons, _stale, index_stale = _call(snap=snap, markers=markers, chapter_ids=[cid])

    assert "index_stale" in reasons
    assert index_stale == [cid]


def test_draft_indexed_chapter_can_be_index_stale_even_though_unpublished():
    """Under the OLD predicate a DRAFT chapter could never be index_stale (it gated on
    editorial_status == 'published'). Now a draft the user explicitly indexed is a
    first-class member of the graph, so a lagging index on it is real staleness."""
    cid = str(uuid4())
    markers = {
        cid: {
            "editorial_status": "draft",
            "published_revision_id": None,
            "kg_indexed_revision_id": _B,
            "last_parsed_revision_id": None,  # never parsed
            "kg_exclude": False,
            "parse_version": 0,
        }
    }
    snap = _snap([{"chapter_id": cid, "kg_indexed_revision_id": _B, "parse_version": 0}])

    _reasons, _stale, index_stale = _call(snap=snap, markers=markers, chapter_ids=[cid])
    assert index_stale == [cid]


def test_kg_excluded_chapter_is_never_index_stale():
    """The sweeper skips kg_exclude'd chapters by design, so a badge on one could never
    clear — the same stuck-badge failure, via a different door."""
    cid = str(uuid4())
    markers = {
        cid: {
            "editorial_status": "published",
            "published_revision_id": _A,
            "kg_indexed_revision_id": None,  # retraction cleared it
            "last_parsed_revision_id": _A,
            "kg_exclude": True,
            "parse_version": 2,
        }
    }
    snap = _snap([{"chapter_id": cid, "kg_indexed_revision_id": None, "parse_version": 2}])

    _reasons, _stale, index_stale = _call(snap=snap, markers=markers, chapter_ids=[cid])
    assert index_stale == [], (
        "a kg_exclude'd chapter must never be index_stale — the sweeper will not touch "
        "it, so the badge would be unclearable"
    )


def test_unindexed_chapter_is_not_index_stale():
    """A chapter that was never added to the knowledge graph has no index to be stale."""
    cid = str(uuid4())
    markers = {
        cid: {
            "editorial_status": "draft",
            "published_revision_id": None,
            "kg_indexed_revision_id": None,
            "last_parsed_revision_id": None,
            "kg_exclude": False,
            "parse_version": 0,
        }
    }
    snap = _snap([{"chapter_id": cid, "kg_indexed_revision_id": None, "parse_version": 0}])

    _reasons, _stale, index_stale = _call(snap=snap, markers=markers, chapter_ids=[cid])
    assert index_stale == []


# ── prose_drift is re-keyed too ──


def test_prose_drift_fires_when_the_indexed_revision_moves():
    """The report binds motifs to SCENES, and scenes are parsed from the INDEXED
    revision. So a re-index (even with no publish at all) is real prose drift."""
    cid = str(uuid4())
    snap = _snap([{"chapter_id": cid, "kg_indexed_revision_id": _A, "parse_version": 1}])
    markers = {
        cid: {
            "editorial_status": "draft",
            "published_revision_id": None,
            "kg_indexed_revision_id": _B,  # re-indexed since the snapshot
            "last_parsed_revision_id": _B,
            "kg_exclude": False,
            "parse_version": 2,
        }
    }

    reasons, stale_chapters, _index_stale = _call(snap=snap, markers=markers, chapter_ids=[cid])

    assert "prose_drift" in reasons
    assert cid in stale_chapters, (
        "a prose-drifted chapter must be in stale_chapters or the scene-inspector chip "
        "renders false-fresh (COMP-STALE-1)"
    )


def test_no_drift_when_nothing_moved():
    cid = str(uuid4())
    snap = _snap([{"chapter_id": cid, "kg_indexed_revision_id": _B, "parse_version": 2}])
    markers = {
        cid: {
            "editorial_status": "published",
            "published_revision_id": _B,
            "kg_indexed_revision_id": _B,
            "last_parsed_revision_id": _B,
            "kg_exclude": False,
            "parse_version": 2,
        }
    }
    reasons, stale_chapters, index_stale = _call(snap=snap, markers=markers, chapter_ids=[cid])
    assert reasons == []
    assert stale_chapters == []
    assert index_stale == []


# ── LEGACY MANIFEST — the deploy must not trigger a mass LLM re-run ──


def test_legacy_manifest_without_kg_key_does_not_false_drift():
    """A snapshot written BEFORE WS-0.7 recorded only `published_revision_id`.

    If the new comparison read a missing key as None, EVERY existing arc would report
    prose_drift on the first status poll after deploy and re-run its LLM-judged,
    token-costly conformance job — a mass spend event caused by a deploy.

    The fallback is safe because the WS-0.2 migration seeded
    kg_indexed_revision_id := published_revision_id on the whole legacy corpus, so the
    two are equal there.
    """
    cid = str(uuid4())
    # Legacy shape: NO kg_indexed_revision_id key at all.
    snap = _snap([{"chapter_id": cid, "published_revision_id": _A, "parse_version": 1}])
    markers = {
        cid: {
            "editorial_status": "published",
            "published_revision_id": _A,
            "kg_indexed_revision_id": _A,  # backfilled to equal the published rev
            "last_parsed_revision_id": _A,
            "kg_exclude": False,
            "parse_version": 1,
        }
    }

    reasons, _stale, _index_stale = _call(snap=snap, markers=markers, chapter_ids=[cid])

    assert "prose_drift" not in reasons, (
        "a legacy (pre-WS-0.7) manifest must NOT read as drifted just because the new "
        "key is absent — that would re-run every arc's costly conformance job on deploy"
    )
