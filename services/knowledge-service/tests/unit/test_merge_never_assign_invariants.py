"""T73 — the NEVER-ASSIGN fields of the three merge queries, as one rule.

§10.1 merged every `ON CREATE SET` / `ON MATCH SET` pair into a single unconditional `SET`
(AGE has no branch keywords). Most fields become `coalesce`. A few must not be assigned **at
all**, because they were ON-CREATE-ONLY and the value they set is exactly what an absent
property already means:

    valid_until        assigning it RESURRECTS a superseded fact/relation      (F5)
    valid_to_ordinal   owned by `temporal.maintain_chain`, not by the merge    (F3)
    archived_at        assigning it UN-ARCHIVES on every re-extraction
    glossary_entity_id assigning it DE-ANCHORS the entity from its glossary row (T78)

⚠️ **This file exists because the same defect appeared three times and only one instance had a
guard.** T71 shipped `valid_until` unconditionally in `_CREATE_RELATION_CYPHER` and the suite
caught it — that one was covered. Then bite 39 reinstated `archived_at` in `_MERGE_FACT_CYPHER`
and **every test in the repository passed**. Writing a third one-off would leave the fourth
undefended, so the rule is stated once, over all three queries.

Each of these fails SILENTLY: no error, no log, and a plausible-looking row. An un-archived
fact reappears in reads meant to exclude it; a resurrected relation re-enters an as-of window
an author had closed.
"""

from __future__ import annotations

import re

import pytest

from app.db.neo4j_repos import entities as en
from app.db.neo4j_repos import events as em
from app.db.neo4j_repos import facts as fm
from app.db.neo4j_repos import relations as rm


def _assignments(cypher: str, field: str) -> list[str]:
    """Lines that ASSIGN `field`.

    ONE matcher, shared by the rule and by its own non-vacuity checks below. The first cut had
    the rule using a regex and the checks using string containment, so the checks could pass
    while the rule was blind — and it was: bite 39 applied cleanly and the file still went
    green, because `"archived_at ="` never matches `f.archived_at       = NULL`.

    * **Whitespace-tolerant**, because the merged SET column-aligns its `=`.
    * **Prefix-safe**, because `valid_to_ordinal_eff` legitimately IS assigned and starts with
      `valid_to_ordinal`; flagging it would force the wrong fix.
    * A read predicate (`WHERE f.archived_at IS NULL`) is not an assignment and must not match.
    """
    pattern = re.compile(r"\." + re.escape(field) + r"\s*=(?!=)")
    return [
        line.strip() for line in cypher.splitlines()
        if pattern.search(line) and (field + "_") not in line
    ]


_NEVER_ASSIGN = [
    ("facts._MERGE_FACT_CYPHER", fm._MERGE_FACT_CYPHER,
     ("valid_until", "valid_to_ordinal", "archived_at")),
    ("events._MERGE_EVENT_CYPHER", em._MERGE_EVENT_CYPHER,
     ("archived_at",)),
    ("relations._CREATE_RELATION_CYPHER", rm._CREATE_RELATION_CYPHER,
     ("valid_until", "valid_to_ordinal")),
    # T76 — the glossary sync. `archived_at` was ON CREATE ONLY here too; assigning it would
    # UN-ARCHIVE an entity on every sync from the glossary.
    ("entities._GLOSSARY_ANCHOR_SYNC_CYPHER", en._GLOSSARY_ANCHOR_SYNC_CYPHER,
     ("archived_at",)),
    # T78 — the last and by far the largest. `_MERGE_ENTITY_CYPHER` had `glossary_entity_id =
    # NULL` and `archived_at = NULL` ON CREATE ONLY. Measured on the dev graph 2026-08-22:
    # 4287 of 4926 :Entity nodes carry an anchor, so assigning the first would de-anchor 87%
    # of the graph on the next extraction — every one of them silently, since a de-anchored
    # node is still a well-formed node.
    ("entities._MERGE_ENTITY_CYPHER", en._MERGE_ENTITY_CYPHER,
     ("glossary_entity_id", "archived_at")),
]

_WHY = {
    "valid_until": "resurrects a superseded fact/relation on every re-extraction (F5)",
    "valid_to_ordinal": "is owned by temporal.maintain_chain; the merge must not write it (F3)",
    "archived_at": "un-archives the node on every re-extraction",
    "glossary_entity_id": ("severs the node from its glossary row — 4287 of 4926 dev nodes "
                           "carry one, and a de-anchored node still looks well-formed"),
}


@pytest.mark.parametrize("name,cypher,fields", _NEVER_ASSIGN,
                         ids=[n for n, _, _ in _NEVER_ASSIGN])
def test_a_merge_query_never_ASSIGNS_a_create_only_lifecycle_field(name, cypher, fields):
    for field in fields:
        offenders = _assignments(cypher, field)
        assert not offenders, (
            f"{name} assigns `{field}` — it {_WHY[field]}. It was ON CREATE ONLY, and an "
            f"absent property is already null, so the merged SET must omit it entirely. "
            f"Offending line(s): {offenders}"
        )


def test_the_matcher_SEES_an_offending_assignment_including_an_ALIGNED_one():
    """Non-vacuity, using the SAME matcher the rule uses.

    The aligned case is the one that mattered: the first cut saw the plain form and missed the
    aligned one, which is the form every merged query actually uses.
    """
    plain = "SET f.archived_at = NULL,"
    aligned = "    f.archived_at       = NULL,"
    assert _assignments(plain, "archived_at"), "the matcher missed a plain assignment"
    assert _assignments(aligned, "archived_at"), (
        "the matcher missed a COLUMN-ALIGNED assignment — that is the form the merged SET "
        "uses, and missing it is how this file passed while the defect was present"
    )


def test_a_READ_predicate_is_not_an_assignment():
    """`WHERE f.archived_at IS NULL` appears all over the read queries. Flagging it would make
    the rule unsatisfiable and force someone to delete a filter to get green."""
    assert not _assignments("  AND f.archived_at IS NULL", "archived_at")
    assert not _assignments("  AND ($include_archived OR f.archived_at IS NULL)", "archived_at")


def test_valid_to_ordinal_EFF_is_not_caught_by_the_prefix():
    """`valid_to_ordinal_eff` IS assigned on purpose (the +inf null-sink). A prefix match would
    flag it and force the wrong fix — dropping a field the reads depend on."""
    line = "    f.valid_to_ordinal_eff = coalesce(f.valid_to_ordinal_eff, $open_ceiling),"
    assert not _assignments(line, "valid_to_ordinal")
    assert _assignments(line, "valid_to_ordinal_eff"), (
        "the prefix guard over-corrected — the _eff field's own assignment is invisible"
    )
