"""D-ARCHIVED-SCENE-PROSE-LEAK — deleting a scene did not remove its prose from the book.

`generation_jobs.py` had **no `is_archived` filter anywhere**. Its three scene-prose
readers all joined `outline_node` and none of them excluded soft-deleted rows, so a scene
the author had deleted kept contributing its text to:

* `prior_scene_drafts` — the cross-scene state reinjection. Live on the Mị Đế book: five
  scenes were archived and rewritten, and the reinjection then reported *"74 paragraph(s)
  from 8 prior scene(s)"* for a FIVE-scene chapter. A discarded ending duly reappeared in a
  freshly written scene, which reads exactly like the model repeating itself — the symptom
  points at the model, the cause is a missing WHERE clause.
* `chapter_scene_drafts` — the STITCH input. An author who deleted a scene and published
  the chapter would find the deleted prose in the published text.
* `scene_drafts_detailed` — the branch prose-diff, which would compare against ghosts.

The tests read the real SQL rather than exercising a database, because the defect IS the
absent predicate: a fixture-based test would only catch it if the fixture happened to
contain an archived row, which is exactly the state nobody thinks to set up.
"""
from __future__ import annotations

import inspect
import re

import pytest

from app.db.repositories.generation_jobs import GenerationJobsRepo

#: Every reader that joins outline_node to pull a scene's prose. If a fourth is added and
#: not listed here, `test_no_scene_prose_reader_is_unlisted` fails.
_SCENE_PROSE_READERS = (
    "prior_scene_drafts",
    "chapter_scene_drafts",
    "scene_drafts_detailed",
)


def _sql_of(name: str) -> str:
    return inspect.getsource(getattr(GenerationJobsRepo, name))


@pytest.mark.parametrize("name", _SCENE_PROSE_READERS)
def test_a_scene_prose_reader_excludes_archived_scenes(name):
    sql = _sql_of(name)
    assert "JOIN outline_node" in sql, f"{name} no longer joins outline_node — re-check this gate"
    assert "NOT o.is_archived" in sql, (
        f"{name} reads scene prose but does not exclude soft-deleted scenes. A deleted "
        "scene would keep feeding its text into the reinjection, the stitch, or a branch "
        "diff — the author deletes it and it comes back."
    )


def test_no_scene_prose_reader_is_unlisted():
    """A fourth reader added without a filter would be invisible to the parametrised test
    above. Catch it by shape: any method whose SQL joins outline_node and selects the
    job's result text is a scene-prose reader and belongs in the list."""
    src = inspect.getsource(GenerationJobsRepo)
    # `^    async def` — CLASS-level methods only. A nested `async def _do(...)` inside a
    # method body is not an attribute of the class and would blow up getattr.
    readers = {
        m.group(1)
        for m in re.finditer(r"^    async def (\w+)\(", src, re.M)
        if "JOIN outline_node" in _sql_of(m.group(1))
        and "result->>'text'" in _sql_of(m.group(1))
    }
    unlisted = readers - set(_SCENE_PROSE_READERS)
    assert not unlisted, (
        f"these read scene prose via outline_node but are not covered by this gate: "
        f"{sorted(unlisted)} — add them to _SCENE_PROSE_READERS (and give them the filter)."
    )


def test_the_reinjection_keeps_its_other_two_guarantees():
    """The archived filter must not have displaced the position bound or the tenancy
    double-filter — both are load-bearing and both live in the same WHERE."""
    sql = _sql_of("prior_scene_drafts")
    assert "o.story_order < $3" in sql, "the strictly-prior spoiler bound is gone"
    assert "j.project_id = $1" in sql and "o.project_id = $1" in sql, (
        "the package-tenancy double filter (job AND node) is gone"
    )
