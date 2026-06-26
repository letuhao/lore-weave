"""M1 (D-DERIVATIVE-ADAPT-FROM-SOURCE) — the `adapt_scene` op + source-prose lens.

Covers the four contract requirements (docs/plans/2026-06-26-composition-contracts):
  • the adapt op fires the SOURCE-prose lens — and ONLY for `adapt_scene` (every
    other op leaves the pack byte-unchanged);
  • entity-renaming overrides reach the adapt prompt (the derivative pack's override
    layer applies under the adapt op too);
  • empty-source safety (no draft / book outage → no <source_scene> block, no crash);
  • spoiler-bound: a pre-branch source chapter is inherited canon → not adapted.

These reuse the project-aware derivative harness in test_pack_override.
"""

from __future__ import annotations

import uuid

import pytest

from app.engine import cowrite
from app.packer.lenses import gather_source_scene
from app.packer.profile import NEUTRAL

from tests.unit.test_pack import BOOK, CHAPTER, StubGlossary
from tests.unit.test_pack_override import (
    DELTA_PROJECT, SOURCE_PROJECT, ProjectAwareKnowledge, _bio, _derivative_req,
    _override, _pack_deriv,
)


# A book stub whose chapter DRAFT carries distinctive SOURCE prose, with a
# configurable chapter sort_order (the reading-order position the spoiler bound
# checks against branch_point). Mirrors test_pack.StubBook's surface.
class SourceProseBook:
    def __init__(self, prose="the knight crossed the bridge\nand drew his sword",
                 chapter_sort=5, raise_on_draft=False):
        self._prose = prose
        self._sort = {str(CHAPTER): chapter_sort}
        self._raise = raise_on_draft

    async def owns_book(self, book_id, bearer):
        return True

    async def get_draft(self, book_id, chapter_id, bearer):
        if self._raise:
            from app.clients.book_client import BookClientError
            raise BookClientError(502, "BOOK_SERVICE_UNAVAILABLE")
        return {"text_content": self._prose}

    async def get_chapter_sort_orders(self, chapter_ids):
        return {k: v for k, v in self._sort.items() if k in {str(c) for c in chapter_ids}}

    async def get_reader_language(self, book_id, user_id):
        return None


def _adapt_req(**kw):
    kw.setdefault("branch_point", 3)
    kw.setdefault("story_order", 5)
    req = _derivative_req(**kw)
    req.operation = "adapt_scene"
    return req


# ── the op instruction (cowrite) ──


def test_adapt_scene_op_registered_with_its_own_instruction():
    msgs = cowrite.build_messages("<source_scene>x</source_scene>", NEUTRAL, "adapt_scene")
    user = msgs[1]["content"]
    assert "Adapt the SOURCE scene" in user
    assert "Do not copy the source verbatim" in user
    # plan-free: it is NOT the generic unknown-op fallback ("Write the next passage")
    assert "Write the next passage of the scene." not in user


def test_adapt_scene_instruction_is_distinct_from_draft_scene():
    adapt = cowrite._OPERATION_INSTRUCTIONS["adapt_scene"]
    draft = cowrite._OPERATION_INSTRUCTIONS["draft_scene"]
    assert adapt != draft


# ── the lens fires ONLY for adapt_scene (pack op-awareness) ──


async def test_adapt_op_fires_source_scene_lens():
    # On a derivative, the adapt op reads the SOURCE chapter draft into <source_scene>.
    kn = ProjectAwareKnowledge()
    pc = await _pack_deriv(_adapt_req(), knowledge=kn, book=SourceProseBook())
    assert "the knight crossed the bridge" in pc.blocks.get("source_scene", "")
    assert "<source_scene>" in pc.prompt


async def test_non_adapt_op_does_not_fire_source_scene_lens():
    # The SAME derivative pack under any other op (default draft_scene) MUST NOT
    # read source prose — no <source_scene> block (the normal pack is unchanged).
    kn = ProjectAwareKnowledge()
    req = _derivative_req(branch_point=3, story_order=5)  # operation defaults to draft_scene
    pc = await _pack_deriv(req, knowledge=kn, book=SourceProseBook())
    # NOTE: the prose itself also flows into <recent> via gather_recent (same chapter
    # draft) — that's the existing L3 lens, unchanged. The op-awareness contract is
    # specifically the <source_scene> BLOCK: it must NOT exist for a non-adapt op.
    assert "source_scene" not in pc.blocks
    assert "<source_scene>" not in pc.prompt


async def test_adapt_op_is_noop_on_non_derivative():
    # A greenfield (non-derivative) Work never has a source to adapt: the gather is
    # inside the is_derivative branch, so even an adapt_scene op yields no block.
    from tests.unit.test_pack import _req, StubBook, StubKnowledge, StubGrant
    from app.grant_client import GrantLevel
    from app.packer.pack import pack
    from tests.unit.test_pack import StubCanon, StubOutline, StubSceneLinks

    def _wc(t):
        return max(1, len(t.split()))

    req = _req()
    req.operation = "adapt_scene"
    bk = StubBook()
    pc = await pack(
        req, book=bk, glossary=StubGlossary(bios=[]), knowledge=StubKnowledge(),
        canon_repo=StubCanon(), outline_repo=StubOutline(),
        scene_links_repo=StubSceneLinks(), budget_tokens=10_000, counter=_wc,
        grant=StubGrant(GrantLevel.OWNER),
    )
    assert "source_scene" not in pc.blocks


# ── overrides reach the adapt prompt ──


async def test_entity_renaming_override_reaches_the_adapt_prompt():
    # An entity-RENAMING override (the headline divergence) must be applied in the
    # adapt pack so the adapted ghost uses the new name. The override layer runs
    # inside the derivative branch the adapt op also uses.
    ent_id = uuid.uuid4()
    kn = ProjectAwareKnowledge(base_bios=[_bio(str(ent_id), "Kael", "a knight")])
    ov = [_override(ent_id, {"name": "Mira"})]
    pc = await _pack_deriv(_adapt_req(overrides=ov), knowledge=kn, book=SourceProseBook())
    # the renamed entity is in <present>, AND the source prose is present (adapt pack)
    assert "Mira" in pc.prompt
    assert "Kael" not in pc.prompt
    assert "<source_scene>" in pc.prompt


# ── empty-source safety ──


async def test_empty_source_draft_yields_no_block():
    # An empty source chapter draft → no <source_scene> block (the caller surfaces
    # "nothing to adapt"; the FE falls back to draft_scene). No crash.
    kn = ProjectAwareKnowledge()
    pc = await _pack_deriv(_adapt_req(), knowledge=kn,
                           book=SourceProseBook(prose="   \n  \n"))
    assert "source_scene" not in pc.blocks


async def test_source_draft_book_outage_degrades_to_no_block():
    # A book-service error while reading the source draft degrades to [] (best-effort),
    # never 500s the adapt pack.
    kn = ProjectAwareKnowledge()
    pc = await _pack_deriv(_adapt_req(), knowledge=kn,
                           book=SourceProseBook(raise_on_draft=True))
    assert "source_scene" not in pc.blocks


# ── spoiler bound: pre-branch chapter is inherited canon (read-only) ──


async def test_pre_branch_source_chapter_is_not_adapted():
    # The source chapter sits BEFORE the branch_point (sort 2 < branch 4) → it is
    # inherited canon, not adaptable: the lens returns [] (server belt for the FE's
    # pre-branch read-only gate). No <source_scene> block.
    kn = ProjectAwareKnowledge()
    pc = await _pack_deriv(
        _adapt_req(branch_point=4, story_order=5),
        knowledge=kn, book=SourceProseBook(chapter_sort=2))
    assert "source_scene" not in pc.blocks


async def test_at_branch_source_chapter_is_adapted():
    # A chapter AT the branch (sort == branch_point) IS adaptable (the divergence
    # zone is at/after the branch).
    kn = ProjectAwareKnowledge()
    pc = await _pack_deriv(
        _adapt_req(branch_point=4, story_order=5),
        knowledge=kn, book=SourceProseBook(chapter_sort=4))
    assert "the knight crossed the bridge" in pc.blocks.get("source_scene", "")


# ── the lens unit, directly (bounds + budget) ──


async def test_gather_source_scene_pre_branch_returns_empty():
    out = await gather_source_scene(
        SourceProseBook(chapter_sort=2), BOOK, CHAPTER, "jwt",
        branch_point=4, chapter_sort_order=2)
    assert out == []


async def test_gather_source_scene_unplaceable_position_skips_bound():
    # An unplaceable chapter_sort_order (None) must NOT fail-empty (a sort-order
    # outage shouldn't kill an adapt the FE already offer-gated) — it reads the draft.
    out = await gather_source_scene(
        SourceProseBook(), BOOK, CHAPTER, "jwt",
        branch_point=4, chapter_sort_order=None)
    assert out and "the knight crossed the bridge" in out[0]


async def test_gather_source_scene_respects_paragraph_budget():
    # A long source chapter is windowed to the last k paragraphs (no context blow-up).
    prose = "\n".join(f"para {i}" for i in range(40))
    out = await gather_source_scene(
        SourceProseBook(prose=prose), BOOK, CHAPTER, "jwt", k=12)
    assert len(out) == 12
    assert out[-1] == "para 39"  # the tail (most-recent) window
