"""W10 — the PURE arc-materialize engine (D-W10-APPLY-PLANNER-MATERIALIZE).

Deterministic beat→chapter distribution + scene/ledger assembly, with NO DB/LLM. These
are the invariants the commit-path relies on: every beat lands in some chapter within its
span (no loss), multi-chapter motifs spread, unresolved placements surface, the arc roster
overrides motif-role binding, and the ledger carries beat_key + arc lineage.
"""
from uuid import uuid4

from app.db.models import ArcApplyPlan, Motif, ResolvedPlacement
from app.engine.arc_materialize import _distribute_beats, build_materialize_spec


def _beat(key: str, order: int, tension: int = 3) -> dict:
    return {"key": key, "label": f"beat {key}", "intent": f"{{protagonist}} does {key}",
            "tension_target": tension, "order": order}


def _motif(code: str, n_beats: int, *, roles=None) -> Motif:
    return Motif(
        id=uuid4(), code=code, name=code.title(),
        beats=[_beat(f"b{i}", i) for i in range(n_beats)],
        roles=roles or [{"key": "protagonist", "actant": "subject", "label": "the hero"}],
        tension_target=3,
    )


def _placement(code: str, thread: str, s: int, e: int, ord_: int = 0, motif_id=None) -> ResolvedPlacement:
    return ResolvedPlacement(
        motif_code=code, motif_id=motif_id, thread=thread, ord=ord_,
        src_span_start=s, src_span_end=e, span_start=s, span_end=e,
    )


def _plan(placements: list[ResolvedPlacement], *, target: int) -> ArcApplyPlan:
    return ArcApplyPlan(arc_template_id=uuid4(), source_chapter_span=target, target_chapters=target,
                        placements=placements)


def _build(plan, motifs, *, roster_bindings=None, cast_index=None, cast_names=None):
    return build_materialize_spec(
        plan, motifs,
        cast_index=cast_index or {}, cast_names=cast_names or {},
        roster_bindings=roster_bindings or {}, arc_template_id=str(plan.arc_template_id),
        k_ceiling=6, high_threshold=70, min_scenes=1, max_scenes=12,
    )


# ── beat distribution (pure) ──────────────────────────────────────────────────────
def test_distribute_one_beat_per_chapter_when_beats_equal_span():
    d = _distribute_beats(4, 2, 5)            # 4 beats over chapters 2..5
    assert d == {2: [0], 3: [1], 4: [2], 5: [3]}


def test_distribute_groups_when_more_beats_than_chapters():
    d = _distribute_beats(6, 1, 2)            # 6 beats over chapters 1..2 → 3 each
    assert sorted(b for beats in d.values() for b in beats) == [0, 1, 2, 3, 4, 5]  # no loss
    assert set(d.keys()) == {1, 2}


def test_distribute_single_chapter_span_holds_all_beats():
    assert _distribute_beats(5, 3, 3) == {3: [0, 1, 2, 3, 4]}


def test_distribute_empty():
    assert _distribute_beats(0, 1, 4) == {}


# ── full spec assembly ─────────────────────────────────────────────────────────────
def test_every_beat_materializes_across_a_multi_chapter_span():
    m = _motif("duel", 4)
    spec = _build(_plan([_placement("duel", "combat", 1, 4, motif_id=m.id)], target=4), [m])
    # 4 beats over chapters 1-4 → one scene per chapter.
    assert [c.chapter_index for c in spec.chapters] == [1, 2, 3, 4]
    assert all(len(c.scenes) == 1 for c in spec.chapters)
    assert spec.scenes_total == 4
    assert spec.beats_distributed == 4
    # the ledger row carries the bound beat_key + arc lineage + thread.
    row = spec.chapters[0].scenes[0].application_row
    assert row["annotations"]["beat_key"] == "b0"
    assert row["annotations"]["arc_template_id"] == str(spec_arc(spec))
    assert row["annotations"]["thread"] == "combat"
    assert row["motif_id"] == str(m.id)


def spec_arc(spec):  # helper: recover the arc id stamped on the first ledger row
    return spec.chapters[0].scenes[0].application_row["annotations"]["arc_template_id"]


def test_two_threads_interleave_into_the_same_chapters():
    a, b = _motif("duel", 2), _motif("tryst", 2)
    plan = _plan([
        _placement("duel", "combat", 1, 2, ord_=0, motif_id=a.id),
        _placement("tryst", "romance", 1, 2, ord_=0, motif_id=b.id),
    ], target=2)
    spec = _build(plan, [a, b])
    # each chapter holds one scene from each thread.
    by_idx = {c.chapter_index: c for c in spec.chapters}
    assert set(by_idx) == {1, 2}
    threads_ch1 = {s.application_row["annotations"]["thread"] for s in by_idx[1].scenes}
    assert threads_ch1 == {"combat", "romance"}


def test_unresolved_motif_is_surfaced_not_dropped():
    plan = _plan([_placement("ghost", "combat", 1, 2)], target=2)
    spec = _build(plan, [None])              # router couldn't resolve it
    assert spec.chapters == []
    assert spec.unresolved_placements == [{"motif_code": "ghost", "thread": "combat", "reason": "motif_not_visible"}]


def test_motif_with_no_beats_is_surfaced():
    m = _motif("empty", 0)
    spec = _build(_plan([_placement("empty", "combat", 1, 2, motif_id=m.id)], target=2), [m])
    assert spec.chapters == []
    assert spec.unresolved_placements[0]["reason"] == "motif_has_no_beats"


def test_arc_roster_binds_the_cast_into_scenes():
    eid = str(uuid4())
    m = _motif("duel", 1)
    plan = _plan([_placement("duel", "combat", 1, 1, motif_id=m.id)], target=1)
    spec = _build(plan, [m],
                  roster_bindings={"protagonist": "Lin Fei"},
                  cast_index={"lin fei": eid}, cast_names={eid: "Lin Fei"})
    scene = spec.chapters[0].scenes[0]
    assert scene.present_entity_ids == [eid]                 # bound cast propagated to the scene
    assert scene.application_row["role_bindings"]["protagonist"] == eid
    assert "Lin Fei" in scene.synopsis                       # {protagonist} token rendered to the name


def test_every_beat_materializes_even_past_the_planner_scene_cap():
    # 8 beats on a width-1 span → all 8 must become scenes, NOT clipped to the planner's
    # per-chapter max_scenes (=6 in prod) — materialize honors the arc's authored beats.
    m = _motif("epic", 8)
    plan = _plan([_placement("epic", "combat", 1, 1, motif_id=m.id)], target=1)
    spec = build_materialize_spec(
        plan, [m], cast_index={}, cast_names={}, roster_bindings={},
        arc_template_id=str(plan.arc_template_id),
        k_ceiling=6, high_threshold=70, min_scenes=1, max_scenes=6)
    assert spec.scenes_total == 8                 # no clip
    assert spec.beats_distributed == 8
    assert len(spec.chapters[0].scenes) == 8
    # the ledger covers every beat (b0..b7).
    keys = [s.application_row["annotations"]["beat_key"] for s in spec.chapters[0].scenes]
    assert keys == [f"b{i}" for i in range(8)]


def test_determinism_same_inputs_same_spec():
    m = _motif("duel", 3)
    plan = _plan([_placement("duel", "combat", 1, 3, motif_id=m.id)], target=3)
    s1 = _build(plan, [m])
    s2 = _build(plan, [m])
    assert [(c.chapter_index, [sc.title for sc in c.scenes]) for c in s1.chapters] == \
           [(c.chapter_index, [sc.title for sc in c.scenes]) for c in s2.chapters]
