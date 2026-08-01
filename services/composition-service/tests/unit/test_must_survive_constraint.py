"""The PREVENTION half — the drafter is TOLD who the plan still needs.

The detection half catches a draft that kills one of them, after the tokens are spent and with
a revise to pay for. This is the half that stops it being written. Measured before it existed:
`gather_present` put each cast member's name, bio and relations into the prompt and NOT ONE WORD
about who may die.

Two things get pinned here, and the second is the one a "does the line appear" test would miss:
the constraint must be PROTECTED, so a tight budget can never trim the single line that says
what the scene may not do.
"""
from __future__ import annotations

import uuid

import pytest

from app.packer.assemble import build_segments
from app.packer.lenses import LensBundle, gather_must_survive

DAO, VIEN, GHOST = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
PRESENT = [
    {"entity_id": DAO, "name": "Tô Thanh Dao", "summary": "", "relations": []},
    {"entity_id": VIEN, "name": "Lạc Viên", "summary": "", "relations": []},
]


class _Outline:
    def __init__(self, plan=None, raises=False):
        self._plan, self._raises = plan or {}, raises
        self.calls = []

    async def plan_liveness_after(self, project_id, chapter_id, order):
        self.calls.append((str(project_id), str(chapter_id), order))
        if self._raises:
            raise RuntimeError("db down")
        return self._plan


def _node(**kw):
    return {"chapter_id": str(uuid.uuid4()), "story_order": 1000, **kw}


# ── the lens ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_plan_alive_cast_comes_back_by_NAME():
    repo = _Outline({DAO: "alive", VIEN: "alive"})
    got = await gather_must_survive(repo, PRESENT, project_id=uuid.uuid4(), node=_node())
    assert got == ["Lạc Viên", "Tô Thanh Dao"], "sorted, so the prompt is byte-stable"


@pytest.mark.asyncio
async def test_CONTROL_no_later_scene_means_no_constraint():
    """The last scene of a chapter may kill anyone. A constraint that always fires would
    forbid every planned death in the book."""
    repo = _Outline({})
    assert await gather_must_survive(repo, PRESENT, project_id=uuid.uuid4(), node=_node()) == []


@pytest.mark.asyncio
async def test_an_entity_with_no_NAME_in_present_is_dropped():
    """A constraint the drafter cannot act on is worse than none: it spends prompt budget and
    names something the model never saw. The id is in the plan; nothing in `present` names it."""
    repo = _Outline({DAO: "alive", GHOST: "alive"})
    got = await gather_must_survive(repo, PRESENT, project_id=uuid.uuid4(), node=_node())
    assert got == ["Tô Thanh Dao"]


@pytest.mark.asyncio
async def test_a_scene_with_NO_POSITION_asks_nothing():
    repo = _Outline({DAO: "alive"})
    got = await gather_must_survive(
        repo, PRESENT, project_id=uuid.uuid4(), node=_node(story_order=None))
    assert got == [] and repo.calls == [], "no position ⇒ no query at all"


@pytest.mark.asyncio
async def test_a_repo_FAILURE_thins_the_lens_it_does_not_fail_the_pack():
    repo = _Outline(raises=True)
    assert await gather_must_survive(repo, PRESENT, project_id=uuid.uuid4(), node=_node()) == []


# ── the render, and the property a "does the line appear" test would miss ─────────────────

def test_the_constraint_reaches_the_prompt_and_names_them():
    segs = build_segments(LensBundle(must_survive=["Tô Thanh Dao", "Lạc Viên"]))
    hit = [s for s in segs if "must still be alive" in s.text]
    assert len(hit) == 1
    assert "Tô Thanh Dao" in hit[0].text and "Lạc Viên" in hit[0].text


def test_the_constraint_is_PROTECTED_so_a_tight_budget_cannot_trim_it():
    """InkOS F5 applied literally: do not compress what the next step must OBEY. A constraint
    the budget may drop is a constraint that vanishes on exactly the long scenes where the
    drafter is most likely to need it."""
    seg = next(s for s in build_segments(LensBundle(must_survive=["Tô Thanh Dao"]))
               if "must still be alive" in s.text)
    assert seg.protected is True
    assert seg.block == "canon", "it is a RULE, not context — `present` describes, canon forbids"


def test_CONTROL_an_empty_list_renders_NOTHING():
    """Not an empty constraint line. A sentence that names nobody still costs budget and still
    reads to the model as a rule about someone."""
    segs = build_segments(LensBundle(must_survive=[]))
    assert not [s for s in segs if "must still be alive" in s.text]
