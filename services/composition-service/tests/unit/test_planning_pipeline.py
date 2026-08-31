"""Unit test for planning Stage 6 — run_planning_pipeline (engine/planning_pipeline.py).

Stubs each stage and asserts the orchestrator chains them correctly: cast is seeded +
joined to roster entity-ids, motifs/char-arcs thread into the grounded decompose, L1
runs once, and self-heal runs.
"""

from uuid import UUID

from app.engine import planning_pipeline as pp
from app.engine.cast_plan import ProposedChar
from app.engine.character_plan import CharacterArc
from app.engine.motif_plan import SelectedArcMotif
from app.engine.plan import ChapterPlan, ChapterScenes, DecomposeResult
from app.engine.plan_heal import PlanHealReport

BOOK = UUID("019f1783-ebb4-78de-ac9d-0dfba6539b7c")
PROJ = UUID("019f1783-ecca-7331-afab-9543762a8b68")


class _Gloss:
    def __init__(self):
        self.seeded = None

    async def seed_entities(self, book_id, **kw):
        self.seeded = kw["entities"]
        return []


class _Kal:
    """T37 — the double carries the ROLE surface too, because the pipeline now writes and
    closes plan-authored roles (SPEC §4.2b). It failed at the call when `close_stale_planned_roles`
    landed (`'_Kal' object has no attribute 'open_facts_for'`), which is a narrow double doing
    its job: the break belongs here rather than in production."""

    def __init__(self):
        self.appended: list[dict] = []
        self.closed: list[dict] = []

    async def roster(self, book_id, **kw):
        return [{"entity_id": "e1", "name": "Lâm Uyển"}, {"entity_id": "e2", "name": "Hắc Sát"}]

    async def append_role_fact(self, book_id, **kw):
        self.appended.append(kw)
        return {"fact_id": "f-" + str(len(self.appended))}

    async def open_facts_for(self, book_id, entity_id, *, user_id=None):
        return []

    async def close_fact(self, book_id, *, fact_id, valid_to_ordinal, user_id=None):
        self.closed.append({"fact_id": fact_id, "valid_to_ordinal": valid_to_ordinal})
        return {"fact_id": fact_id}


async def test_pipeline_chains_all_stages(monkeypatch):
    captured: dict = {}

    async def _cast(llm, **kw):
        return [ProposedChar(name="Lâm Uyển", role="protagonist", is_new=False),
                ProposedChar(name="Hắc Sát", role="ally", is_new=True)]

    async def _motifs(llm, retr, **kw):
        return [SelectedArcMotif(code="m", name="M", summary="s", arc_role="central spine")]

    async def _arcs(llm, **kw):
        captured["arcs_beats"] = kw["beat_roles"]
        return [CharacterArc(name="Hắc Sát", introduce_at_chapter=5)]

    async def _ground(llm, **kw):
        captured.update(kw)
        return DecomposeResult(arc_title="A", chapters=[ChapterScenes(
            chapter=ChapterPlan("c", "t", 1, "hook", "i"), scenes=[])])

    async def _heal(llm, result, **kw):
        return result, PlanHealReport(edits_applied=2)

    async def _l1(llm, **kw):
        return None  # L1 degrades → chapters keep beat_role=None (still runs once)

    monkeypatch.setattr(pp, "propose_cast", _cast)
    monkeypatch.setattr(pp, "select_arc_motifs", _motifs)
    monkeypatch.setattr(pp, "plan_character_arcs", _arcs)
    monkeypatch.setattr(pp, "grounded_decompose", _ground)
    monkeypatch.setattr(pp, "run_plan_self_heal", _heal)
    monkeypatch.setattr(pp, "_llm_json", _l1)

    gloss = _Gloss()
    res = await pp.run_planning_pipeline(
        object(), object(), gloss, _Kal(), user_id="019d5e3c-7cc5-7e6a-8b27-1344e148bf7c",
        book_id=BOOK, project_id=PROJ, premise="p", beats=[{"key": "hook"}],
        chapters=[ChapterPlan("c", "t", 1, None, "")], genre_tags=["xianxia"],
        model_source="user_model", model_ref="m", k_ceiling=3, high_threshold=70,
        min_scenes=2, max_scenes=4)

    # Stage 0: both cast seeded, then joined to roster entity-ids for the decompose
    assert {e["name"] for e in gloss.seeded} == {"Lâm Uyển", "Hắc Sát"}
    assert {c["entity_id"] for c in captured["cast"]} == {"e1", "e2"}
    # Stage 1 + 3 thread into Stage 4
    assert captured["motifs"][0]["name"] == "M" and captured["motifs"][0]["arc_role"] == "central spine"
    assert captured["char_arcs"][0]["introduce_at_chapter"] == 5
    # the SAME L1 result feeds Stage 3's beats and Stage 4's chapters (one map)
    assert captured["arcs_beats"] == [None]      # L1 degraded → beat_role None, reused
    assert captured["skip_l1"] is True           # orchestrator owns L1 → grounded never re-runs it
    # Stage 5 ran; intermediates surfaced
    assert res.heal_report.edits_applied == 2
    assert res.cast[0]["name"] == "Lâm Uyển" and res.motifs[0]["code"] == "m"
