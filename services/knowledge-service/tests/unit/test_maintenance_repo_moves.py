"""Plan T17 — what the sweeper/passage moves must not have changed.

Every move in this task is meant to be behaviour-preserving, which is exactly the claim
that goes unchecked because "it's just a move". These are the three places where it was
not just a move, or where getting it wrong would be silent.
"""

from __future__ import annotations

import pytest

from app.db.neo4j_repos import maintenance
from app.db.neo4j_repos.passages import _RECENT_PASSAGE_TEXTS_CYPHER


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __aiter__(self):
        async def gen():
            for r in self._rows:
                yield r
        return gen()

    async def single(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, rows=()):
        self.cypher = None
        self.params = None
        self._rows = list(rows)

    async def run(self, cypher, **params):
        self.cypher, self.params = cypher, params
        return _FakeResult(self._rows)


# ── the collapse of two queries into one ─────────────────────────────


def test_global_scope_matches_only_projectless_passages():
    """`regenerate_summaries` had TWO near-identical queries differing only in the project
    predicate; they are one query now, with the branch expressed in Cypher.

    The rule that must survive the collapse is KSA §7.6 rule 5: the GLOBAL scope matches
    passages that are themselves project-less, NOT "any project". A naive collapse writes
    `($project_id IS NULL OR p.project_id = $project_id)`, which is true for every passage
    when project_id is None — so a global summary would be built from every project's
    passages. That is the cross-contamination the rule exists to prevent, and it would look
    like a slightly-too-good summary rather than a bug.
    """
    cypher = _RECENT_PASSAGE_TEXTS_CYPHER
    assert "$project_id IS NULL AND p.project_id IS NULL" in cypher, (
        "the global branch must require the PASSAGE to be project-less too"
    )
    assert "$project_id IS NOT NULL AND p.project_id = $project_id" in cypher
    # The naive form must NOT be what shipped.
    assert "($project_id IS NULL OR p.project_id = $project_id)" not in cypher


# ── the closed label sets that are injection barriers ────────────────


@pytest.mark.asyncio
async def test_count_rejects_a_label_outside_the_closed_set():
    """The label is INTERPOLATED because Cypher cannot parameterise one, so this check is
    the injection barrier — not a type nicety."""
    with pytest.raises(ValueError):
        await maintenance.count_nodes_by_label(
            _FakeSession(), user_id="u", project_id="p", label="Entity) DETACH DELETE (n",
        )


@pytest.mark.asyncio
async def test_reconcile_rejects_a_label_outside_the_closed_set():
    with pytest.raises(ValueError):
        await maintenance.reconcile_evidence_count_for_label(
            _FakeSession(), label="Relation", user_id="u",
        )


def test_the_reconcile_label_set_did_not_grow_in_the_move():
    """Relations are excluded on purpose — they track provenance via `source_event_ids` on
    the edge and have no cached counter. Adding a label here would make the sweeper write
    `evidence_count` onto nodes that never had one, and nothing would fail loudly."""
    assert maintenance.RECONCILE_LABELS == ("Entity", "Event", "Fact")
    assert maintenance.COUNTABLE_LABELS == ("Entity", "Fact", "Event")


@pytest.mark.asyncio
async def test_a_none_row_is_an_anomaly_not_an_empty_result():
    """`RETURN count(*)` always produces a row. None means the driver or session is broken,
    and returning 0 for it would report "no drift" on a reconciler that never ran."""
    with pytest.raises(RuntimeError):
        await maintenance.reconcile_evidence_count_for_label(
            _FakeSession(rows=[]), label="Entity", user_id="u",
        )
    with pytest.raises(RuntimeError):
        await maintenance.delete_orphan_extraction_sources(
            _FakeSession(rows=[]), user_id="u",
        )
