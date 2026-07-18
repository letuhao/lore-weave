"""27 V2-H1/H2 — the EFFECT tests, and the crash-resume derivation.

Every other test in this cluster reads source or asserts a return value. These assert that a change
in one place CHANGES SOMETHING SOMEWHERE ELSE — the `checklist-is-self-report-enforce-by-tests`
discipline. They exist because the compiler is a chain of artifacts, and a link in that chain can be
written, stored, green in every unit test, and READ BY NOBODY. That is the write-only bug, and it is
the single most-repeated defect class in this repo.

The question each one answers is not "does the code do X" but "would anything notice if it stopped".
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.db.models import PlanRun
from app.services import plan_pass_service as pps


def _run(state: dict) -> PlanRun:
    return PlanRun(
        id=uuid4(), created_by=uuid4(), book_id=uuid4(),
        status="compiled", mode="rules", pass_state=state,
    )


def _done(artifact_id, fp, decision="auto") -> dict:
    return {
        "status": "completed", "decision": decision,
        "artifact_id": str(artifact_id), "input_fingerprint": fp, "params": {},
    }


# ── H2 · effect: the CAST reaches pass 6's prompt ────────────────────────────────────────────────

def test_CHANGING_THE_CAST_CHANGES_PASS_6s_PROMPT():
    """`cast_plan` is pass 6's input. If the cast could change without the scene-decomposition
    prompt changing, then `cast_plan` would be a stored-and-unread artifact — the whole seven-pass
    chain would be theatre, and the human's blocking checkpoint on the cast would decide nothing.

    This asserts the opposite by effect: two casts, two different prompts, each naming its own
    people."""
    from app.engine.plan import ChapterPlan, build_scene_decompose_messages

    chapter = ChapterPlan(
        chapter_id="e1", title="The Summons", sort_order=1,
        beat_role="setup", intent="Ha is called",
    )
    kw = dict(
        premise="A courier crosses the Iron Court.", chapter=chapter,
        beat_purpose="establish the court", min_scenes=2, max_scenes=4,
        source_language="en",
    )

    _, user_a = build_scene_decompose_messages(cast_names=["Ha", "The Gatekeeper"], **kw)
    _, user_b = build_scene_decompose_messages(cast_names=["Mara Vance", "The Diver"], **kw)

    assert user_a != user_b, "the cast does not reach the pass-6 prompt — cast_plan is write-only"
    assert "Ha" in user_a and "Mara Vance" not in user_a
    assert "Mara Vance" in user_b and "The Gatekeeper" not in user_b


def test_the_TENSION_TARGET_reaches_pass_6s_prompt():
    """Pass 4's curve is the other half of the same argument. A human edits the tension curve at the
    blocking `beats` checkpoint; if that number never reached the prompt, the checkpoint would be a
    form the author fills in and nothing reads."""
    from app.engine.plan import ChapterPlan, build_scene_decompose_messages

    chapter = ChapterPlan(chapter_id="e1", title="T", sort_order=1, beat_role="climax", intent="")
    kw = dict(
        premise="p", chapter=chapter, beat_purpose="", cast_names=["Ha"],
        min_scenes=2, max_scenes=4, source_language="en",
    )
    _, low = build_scene_decompose_messages(tension_target=10, **kw)
    _, high = build_scene_decompose_messages(tension_target=95, **kw)

    assert low != high
    assert "10" in low and "95" in high


# ── H2 · effect: a linked scene's tension + cast reach the READ path ─────────────────────────────

def test_a_LINKED_SCENES_tension_and_cast_REACH_THE_READ_PATH():
    """The linker writes `tension` and `present_entity_ids` onto the scene node. The SceneRail reads
    outline nodes through `_node_out`. If that serializer dropped either field, the plan's scenes
    would arrive in the UI stripped of exactly the two things pass 6 spent an LLM call deciding —
    and every backend test would still be green, because the WRITE is fine.

    This is the `fe-status-default-fallback` shape: the field exists, the writer writes it, and the
    reader silently omits it."""
    import inspect

    from app.routers import outline

    src = inspect.getsource(outline)
    node_out = src[src.index('"chapter_id": str(node.chapter_id)'):][:900]
    assert '"tension": node.tension' in node_out
    assert '"present_entity_ids"' in node_out

    # …and the LINKER is what puts them there — the two halves of the same contract.
    from app.services import plan_link_service

    link_src = inspect.getsource(plan_link_service)
    assert "tension" in link_src and "present_entity_ids" in link_src


# ── H1 · resume after a simulated crash ──────────────────────────────────────────────────────────

def test_a_CRASHED_pass_leaves_the_run_RESUMABLE_not_corrupt():
    """The crash window: the worker saved the artifact, then died before recording the pointer.

    The artifact is an orphan; `pass_state` still says the pass never completed. That is EXACTLY the
    state we chose (finalize writes artifact-then-pointer), and the recovery is to re-run the pass —
    which costs tokens, not correctness. What must NOT happen is the run reading as further along
    than it is: the cursor must not advance past a pass whose artifact nothing points at.
    """
    pkg = uuid4()
    fp = pps.fingerprint(input_artifact_ids=[str(pkg)])

    # motifs completed; cast CRASHED mid-run (status recorded, no artifact pointer)
    crashed = _run({
        "motifs": _done(uuid4(), fp),
        "cast": {"status": "running", "decision": "pending"},
    })
    assert pps.pass_cursor(crashed, package_artifact_id=pkg) == 1  # …not 2
    assert pps.is_fresh(crashed, "cast", package_artifact_id=pkg) is False
    # and `world`, which depends on cast, refuses
    assert pps.blockers_for(crashed, "world", package_artifact_id=pkg) == ["cast"]


def test_RE_RUNNING_a_pass_stales_everything_downstream_with_ZERO_invalidation_writes():
    """PF-3, the property the whole design rests on. A re-run mints a NEW artifact id; every
    downstream pass's fingerprint was computed over the OLD id; so they go stale by DERIVATION.

    Nothing is written to invalidate them. If this were a stored dirty-flag instead, every writer
    that touched an artifact would have to remember to set it — and the one that forgot would leave
    a plan that is internally inconsistent and reports itself as fresh."""
    pkg = uuid4()
    cast_v1 = uuid4()
    cast_fp = pps.fingerprint(input_artifact_ids=[str(pkg)])
    world_fp = pps.fingerprint(input_artifact_ids=[str(pkg), str(cast_v1)])

    before = _run({
        "cast": _done(cast_v1, cast_fp, decision="accepted"),
        "world": _done(uuid4(), world_fp),
    })
    assert pps.is_fresh(before, "world", package_artifact_id=pkg) is True

    # …re-run `cast`. We touch NOTHING else — only its own entry changes.
    after = _run({
        "cast": _done(uuid4(), cast_fp, decision="accepted"),   # a NEW artifact id
        "world": before.pass_state["world"],                    # byte-identical
    })
    assert pps.is_fresh(after, "cast", package_artifact_id=pkg) is True
    assert pps.is_fresh(after, "world", package_artifact_id=pkg) is False   # …stale, by derivation
    assert pps.blockers_for(after, "character_arcs", package_artifact_id=pkg)


def test_a_RECOMPILE_stales_the_ENTRY_passes_too():
    """The package is an input. `motifs` and `cast` have no PASS dependencies, so with the package
    left out of their fingerprint their input set would be EMPTY — a constant — and they would be
    fresh forever, including after the author re-compiled against a different arc and every artifact
    they were built from ceased to describe the plan."""
    pkg_v1, pkg_v2 = uuid4(), uuid4()
    r = _run({"cast": _done(uuid4(), pps.fingerprint(input_artifact_ids=[str(pkg_v1)]))})

    assert pps.is_fresh(r, "cast", package_artifact_id=pkg_v1) is True
    assert pps.is_fresh(r, "cast", package_artifact_id=pkg_v2) is False


@pytest.mark.parametrize("blocking_pass", ["cast", "beats"])
def test_a_BLOCKING_pass_STOPS_the_runner_until_a_human_accepts(blocking_pass):
    """PF-6. `completed` is not `accepted` — and the gap between them is the only place in this
    system where the author is structurally required to look at what the machine decided."""
    pkg = uuid4()
    fp = pps.fingerprint(input_artifact_ids=[str(pkg)])

    # every upstream fresh; the blocking pass COMPLETED but sits at decision=pending
    state = {
        pid: _done(uuid4(), fp, decision="auto")
        for pid in pps.PASS_ORDER[: pps.PASS_ORDER.index(blocking_pass)]
    }
    state[blocking_pass] = _done(uuid4(), fp, decision="pending")
    run = _run(state)

    downstream = next(
        pid for pid in pps.PASS_ORDER[pps.PASS_ORDER.index(blocking_pass) + 1 :]
        if blocking_pass in pps.PASS_REGISTRY[pid].depends_on
    )
    assert blocking_pass in pps.blockers_for(run, downstream, package_artifact_id=pkg)
    with pytest.raises(pps.UpstreamStale):
        pps.assert_runnable(run, downstream, package_artifact_id=pkg)

    # …and `force` is the only escape, an explicit per-call argument (never an env flag)
    pps.assert_runnable(run, downstream, force=True, package_artifact_id=pkg)
