"""composition batch-job worker — foundation (Phase 3 M4).

The consumer's run_job orchestration (idempotent dispatch + business-fail), the
message branch, and run_decompose's reconstruction from the persisted input. All
fakes — no Redis, no DB, no real LLM.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.worker import job_consumer as jc
from app.worker.operations import run_decompose, run_plan_pipeline, run_selection_edit


def _llm_stub():
    """A bare `object()` used to stand in for the LLM client no longer suffices once
    an operation resolves model-context-aware budgets — give it the one method those
    call, returning "unresolved" so the flat default budget applies."""
    async def _resolve_context_length(model_source, model_ref):
        return None
    return SimpleNamespace(resolve_context_length=_resolve_context_length)


class _FakeRepo:
    def __init__(self, job):
        self._job = job
        self.updates: list = []

    async def get(self, jid):
        return self._job

    async def update_status(self, jid, status, *, result=None, **kw):
        self.updates.append((status, result))
        return self._job


def _job(operation="decompose_preview", status="pending", input=None):
    _uid = uuid4()
    return SimpleNamespace(
        id=uuid4(), created_by=_uid, user_id=_uid, project_id=uuid4(), operation=operation,
        status=status, input=input if input is not None else {},
    )


def _patch_run_job(monkeypatch, repo, *, result=None, raises=None):
    monkeypatch.setattr(jc, "GenerationJobsRepo", lambda pool: repo)

    async def _rd(llm, *, user_id, input, cancel_check=None):
        if raises is not None:
            raise raises
        return result if result is not None else {"tree": []}

    monkeypatch.setattr(jc, "run_decompose", _rd)


async def test_run_job_dispatches_decompose_and_completes(monkeypatch):
    job = _job()
    repo = _FakeRepo(job)
    _patch_run_job(monkeypatch, repo, result={"tree": [1, 2]})
    out = await jc.run_job(object(), object(), job_id=str(job.id), user_id=str(job.user_id))
    assert out == "completed"
    assert [u[0] for u in repo.updates] == ["running", "completed"]
    assert repo.updates[-1][1] == {"tree": [1, 2]}


async def test_run_job_completed_is_idempotent(monkeypatch):
    job = _job(status="completed")
    repo = _FakeRepo(job)
    _patch_run_job(monkeypatch, repo)
    out = await jc.run_job(object(), object(), job_id=str(job.id), user_id=str(job.user_id))
    assert out == "already_completed"
    assert repo.updates == []  # no recompute, no re-mark


async def test_run_job_business_error_marks_failed(monkeypatch):
    job = _job()
    repo = _FakeRepo(job)
    _patch_run_job(monkeypatch, repo, raises=ValueError("bad plan output"))
    out = await jc.run_job(object(), object(), job_id=str(job.id), user_id=str(job.user_id))
    assert out == "failed"
    assert repo.updates[0][0] == "running"
    assert repo.updates[-1][0] == "failed"
    assert "bad plan output" in repo.updates[-1][1]["error"]


async def test_run_selection_edit_errored_no_content_raises(monkeypatch):
    # D-ENGINE-ERRORED-JOB-MARKED-COMPLETED (worker path): stream_draft always yields a
    # terminal frame even after an LLMError, so `final is not None` — the errored-empty
    # case must RAISE (→ job failed via the business-error path above), never return an
    # empty completed edit.
    async def errored_stream(sdk, **kw):
        yield {"type": "error", "error": "model_ref could not be resolved"}
        yield {"type": "usage", "text": "", "metering": SimpleNamespace(
            input_tokens=10, output_tokens=0, measured=False, finish_reason=None),
            "capped": False, "error": "model_ref could not be resolved"}

    monkeypatch.setattr("app.engine.cowrite.stream_draft", errored_stream)
    with pytest.raises(ValueError, match="model_ref could not be resolved"):
        await run_selection_edit(SimpleNamespace(sdk=object()), input={
            "user_id": "u", "messages": [{"role": "user", "content": "x"}],
            "prompt_estimate": 10, "max_out": 100, "model_source": "user_model",
            "model_ref": str(uuid4())})


async def test_run_selection_edit_error_after_content_succeeds(monkeypatch):
    # The taxonomy boundary: partial content then error keeps the prose (not a failure).
    async def partial_then_error(sdk, **kw):
        yield {"type": "token", "delta": "partial"}
        yield {"type": "error", "error": "dropped"}
        yield {"type": "usage", "text": "partial", "metering": SimpleNamespace(
            input_tokens=10, output_tokens=2, measured=True, finish_reason=None),
            "capped": False, "error": "dropped"}

    monkeypatch.setattr("app.engine.cowrite.stream_draft", partial_then_error)
    out = await run_selection_edit(SimpleNamespace(sdk=object()), input={
        "user_id": "u", "messages": [{"role": "user", "content": "x"}],
        "prompt_estimate": 10, "max_out": 100, "model_source": "user_model",
        "model_ref": str(uuid4())})
    assert out["text"] == "partial"
    # review MED: the worker path doesn't stream, so this result is the ONLY interruption signal —
    # it must flag truncated + carry the error, not look like a clean edit.
    assert out["truncated"] is True
    assert out["error"] == "dropped"


async def test_run_job_unknown_operation_fails(monkeypatch):
    job = _job(operation="totally_unknown")
    repo = _FakeRepo(job)
    monkeypatch.setattr(jc, "GenerationJobsRepo", lambda pool: repo)
    out = await jc.run_job(object(), object(), job_id=str(job.id), user_id=str(job.user_id))
    assert out == "failed"  # UnsupportedOperationError is a business error


async def test_run_job_not_found(monkeypatch):
    repo = _FakeRepo(None)
    monkeypatch.setattr(jc, "GenerationJobsRepo", lambda pool: repo)
    out = await jc.run_job(object(), object(), job_id=str(uuid4()), user_id=str(uuid4()))
    assert out == "not_found"


async def test_dispatch_routes_to_run_job(monkeypatch):
    seen: dict = {}

    async def _run(pool, llm, *, job_id, user_id):
        seen.update(job_id=job_id, user_id=user_id)

    monkeypatch.setattr(jc, "run_job", _run)
    await jc.dispatch_job_message(
        object(), object(), fields={"job_id": "j-1", "user_id": "u-1", "project_id": "p"})
    assert seen == {"job_id": "j-1", "user_id": "u-1"}


async def test_run_job_dispatches_stitch_and_stores_result(monkeypatch):
    job = _job(operation="stitch_chapter", input={"chapter_id": "c1"})
    repo = _FakeRepo(job)
    monkeypatch.setattr(jc, "GenerationJobsRepo", lambda pool: repo)
    monkeypatch.setattr(jc, "get_knowledge_client", lambda: object())

    captured: dict = {}

    async def _rs(pool, llm, knowledge, *, input, cancel_check=None):
        captured.update(input)
        return {"text": "stitched chapter", "persisted": False}

    monkeypatch.setattr(jc, "run_stitch", _rs)
    out = await jc.run_job(object(), object(), job_id=str(job.id), user_id=str(job.user_id))
    assert out == "completed"
    assert repo.updates[-1][1]["text"] == "stitched chapter"
    # the consumer injects user_id/project_id (off the job row) into the worker input
    assert captured["user_id"] == str(job.user_id)
    assert captured["project_id"] == str(job.project_id)
    assert captured["chapter_id"] == "c1"


async def test_run_stitch_computes_and_stores_no_persist(monkeypatch):
    import app.db.repositories.works as works_mod
    import app.db.repositories.generation_jobs as gj_mod
    import app.engine.stitch as stitch_mod
    import app.engine.canon_reflect as reflect_mod
    import app.packer.profile as profile_mod
    from app.worker.operations import run_stitch

    class _FakeWorks:
        def __init__(self, pool): ...
        async def get(self, pid):
            return SimpleNamespace(settings={"source_language": "en"})

    class _FakeJobsRepo:
        def __init__(self, pool): ...
        async def chapter_scene_drafts(self, pid, cid):
            return [{"title": "Scene One", "text": "scene 1 draft"},
                    {"title": "Scene Two", "text": "scene 2 draft"}]

    stitch_inputs: dict = {}

    async def _fake_stitch(llm, **kw):
        stitch_inputs.update(kw)
        return ("STITCHED PROSE", "stop")

    reflect = SimpleNamespace(violations=[], resolved=True, iterations=0,
                              status="ok", revise_finish_reason=None)

    async def _fake_reflect(**kw):
        return (kw["draft"], reflect, 0)

    monkeypatch.setattr(works_mod, "WorksRepo", _FakeWorks)
    monkeypatch.setattr(gj_mod, "GenerationJobsRepo", _FakeJobsRepo)
    monkeypatch.setattr(stitch_mod, "stitch_chapter", _fake_stitch)
    monkeypatch.setattr(reflect_mod, "run_canon_reflect", _fake_reflect)
    monkeypatch.setattr(profile_mod, "from_settings", lambda s: SimpleNamespace(source_language="en"))

    inp = {
        "user_id": str(uuid4()), "project_id": str(uuid4()), "chapter_id": str(uuid4()),
        "model_source": "user_model", "model_ref": "m1", "chapter_intent": "the climax",
        "cast_glossary_ids": ["e1"], "chapter_sort": 3, "max_out": 4000,
        "reasoning_effort": None, "reflect_max_iters": 1,
        "critic_source": None, "critic_ref": None,
    }
    out = await run_stitch(object(), _llm_stub(), object(), input=inp)
    assert out["text"] == "STITCHED PROSE"
    assert out["stitched"] is True
    assert out["persisted"] is False  # Option A — persist is the separate bearer step
    assert out["canon"]["status"] == "ok"
    # F4 — each stitch input draft opens with its `### <scene title>` line
    assert stitch_inputs["scene_drafts"] == [
        "### Scene One\n\nscene 1 draft", "### Scene Two\n\nscene 2 draft"]


async def test_run_stitch_raises_when_no_drafts(monkeypatch):
    import app.db.repositories.works as works_mod
    import app.db.repositories.generation_jobs as gj_mod
    import app.packer.profile as profile_mod
    from app.worker.operations import run_stitch
    import pytest

    class _FakeWorks:
        def __init__(self, pool): ...
        async def get(self, pid):
            return SimpleNamespace(settings={})

    class _FakeJobsRepo:
        def __init__(self, pool): ...
        async def chapter_scene_drafts(self, pid, cid):
            return []  # nothing to stitch

    monkeypatch.setattr(works_mod, "WorksRepo", _FakeWorks)
    monkeypatch.setattr(gj_mod, "GenerationJobsRepo", _FakeJobsRepo)
    monkeypatch.setattr(profile_mod, "from_settings", lambda s: SimpleNamespace(source_language="en"))
    inp = {"user_id": str(uuid4()), "project_id": str(uuid4()), "chapter_id": str(uuid4())}
    with pytest.raises(ValueError):  # business error → run_job marks 'failed'
        await run_stitch(object(), object(), object(), input=inp)


async def test_run_job_dispatches_generate_via_worker_op(monkeypatch):
    # generate's `operation` column is the free-form prose op ("draft_scene"); the
    # canonical dispatch key is input['worker_op'] = 'generate'.
    job = _job(operation="draft_scene", input={"worker_op": "generate", "packed_prompt": "P"})
    repo = _FakeRepo(job)
    monkeypatch.setattr(jc, "GenerationJobsRepo", lambda pool: repo)
    monkeypatch.setattr(jc, "get_knowledge_client", lambda: object())

    captured: dict = {}

    async def _rg(pool, llm, knowledge, *, input, cancel_check=None):
        captured.update(input)
        return {"text": "auto winner", "persisted": False}

    monkeypatch.setattr(jc, "run_generate", _rg)
    out = await jc.run_job(object(), object(), job_id=str(job.id), user_id=str(job.user_id))
    assert out == "completed"
    assert repo.updates[-1][1]["text"] == "auto winner"
    assert captured["user_id"] == str(job.user_id)
    assert captured["project_id"] == str(job.project_id)
    assert captured["packed_prompt"] == "P"


async def test_run_generate_computes_winner_and_canon(monkeypatch):
    import app.db.repositories.works as works_mod
    import app.engine.select as select_mod
    import app.engine.canon_reflect as reflect_mod
    import app.packer.profile as profile_mod
    from app.engine.select import Candidate, Selection
    from app.engine.cowrite import DraftMetering
    from app.worker.operations import run_generate

    class _FakeWorks:
        def __init__(self, pool): ...
        async def get(self, pid):
            return SimpleNamespace(settings={"source_language": "en"})

    seen: dict = {}

    async def _fake_select(llm, judge, **kw):
        seen.update(kw)
        cands = [Candidate("draft A", DraftMetering(10, 5, True)),
                 Candidate("draft B", DraftMetering(10, 6, True))]
        return Selection(winner=cands[1], winner_index=1, candidates=cands,
                         rerank_reason="B", rerank_measured=True)

    reflect = SimpleNamespace(violations=[], resolved=True, iterations=0,
                              status="ok", revise_finish_reason=None)

    async def _fake_reflect(**kw):
        return (kw["draft"], reflect, 3)

    monkeypatch.setattr(works_mod, "WorksRepo", _FakeWorks)
    monkeypatch.setattr(select_mod, "select_draft", _fake_select)
    monkeypatch.setattr(reflect_mod, "run_canon_reflect", _fake_reflect)
    monkeypatch.setattr(profile_mod, "from_settings", lambda s: SimpleNamespace(source_language="en"))

    inp = {
        "user_id": str(uuid4()), "project_id": str(uuid4()), "outline_node_id": str(uuid4()),
        "model_source": "user_model", "model_ref": "m1", "operation": "draft_scene",
        "packed_prompt": "GROUNDING", "prompt_estimate": 10, "max_out": 1024,
        "present_entity_ids": ["e1"], "scene_sort_order": 4, "beat_role": None, "tension": None,
        "reasoning": "rule_based", "reasoning_effort": "medium", "reasoning_passthrough": False,
        "grounding_available": True, "reinjected_promise_count": 2, "assembly_mode": "per_scene",
        "reflect_max_iters": 1, "critic_source": None, "critic_ref": None,
    }
    out = await run_generate(object(), object(), object(), input=inp)
    assert out["text"] == "draft B" and out["winner_index"] == 1 and out["k"] == 2
    assert out["candidates"] == ["draft A", "draft B"]
    assert out["output_tokens"] == 6 + 3  # winner output + revise tokens
    assert out["canon"]["status"] == "ok"
    assert out["reasoning_effort"] == "medium" and out["reinjected_promise_count"] == 2
    assert out["persisted"] is False
    # no distinct critic → judge falls back to the drafter; passthrough False → effort passed
    assert seen["judge_ref"] == "m1" and seen["reasoning_effort"] == "medium"


async def test_run_generate_select_failure_is_terminal(monkeypatch):
    import app.db.repositories.works as works_mod
    import app.engine.select as select_mod
    import app.packer.profile as profile_mod
    from app.worker.operations import run_generate
    import pytest

    class _FakeWorks:
        def __init__(self, pool): ...
        async def get(self, pid):
            return SimpleNamespace(settings={})

    async def _boom(llm, judge, **kw):
        raise RuntimeError("diverge produced nothing")

    monkeypatch.setattr(works_mod, "WorksRepo", _FakeWorks)
    monkeypatch.setattr(select_mod, "select_draft", _boom)
    monkeypatch.setattr(profile_mod, "from_settings", lambda s: SimpleNamespace(source_language="en"))
    inp = {"user_id": str(uuid4()), "project_id": str(uuid4()), "model_source": "user_model",
           "model_ref": "m1", "operation": "draft_scene", "packed_prompt": "P",
           "prompt_estimate": 1, "max_out": 100}
    with pytest.raises(ValueError):  # → run_job marks 'failed' + ACK (mirrors inline 502)
        await run_generate(object(), object(), object(), input=inp)


async def test_run_job_dispatches_chapter_generate_via_worker_op(monkeypatch):
    job = _job(operation="draft_chapter",
               input={"worker_op": "chapter_generate", "chapter_id": "c9"})
    repo = _FakeRepo(job)
    monkeypatch.setattr(jc, "GenerationJobsRepo", lambda pool: repo)
    monkeypatch.setattr(jc, "get_knowledge_client", lambda: object())

    captured: dict = {}

    async def _rcg(pool, llm, knowledge, *, input, cancel_check=None):
        captured.update(input)
        return {"text": "chapter draft", "persisted": False, "chapter_id": "c9"}

    monkeypatch.setattr(jc, "run_chapter_generate", _rcg)
    out = await jc.run_job(object(), object(), job_id=str(job.id), user_id=str(job.user_id))
    assert out == "completed"
    assert repo.updates[-1][1]["text"] == "chapter draft"
    assert captured["user_id"] == str(job.user_id)
    assert captured["chapter_id"] == "c9"


async def test_run_chapter_generate_single_pass_no_persist(monkeypatch):
    import app.db.repositories.works as works_mod
    import app.engine.select as select_mod
    import app.engine.canon_reflect as reflect_mod
    import app.packer.profile as profile_mod
    from app.engine.select import Candidate
    from app.engine.cowrite import DraftMetering
    from app.worker.operations import run_chapter_generate

    class _FakeWorks:
        def __init__(self, pool): ...
        async def get(self, pid):
            return SimpleNamespace(settings={})  # narrative_thread off

    seen: dict = {}

    async def _fake_diverge(llm, **kw):
        seen.update(kw)
        return [Candidate("CHAPTER PROSE", DraftMetering(40, 12, True))]

    reflect = SimpleNamespace(violations=[], resolved=True, iterations=0,
                              status="checked", revise_finish_reason=None)

    async def _fake_reflect(**kw):
        return (kw["draft"], reflect, 4)

    monkeypatch.setattr(works_mod, "WorksRepo", _FakeWorks)
    monkeypatch.setattr(select_mod, "diverge", _fake_diverge)
    monkeypatch.setattr(reflect_mod, "run_canon_reflect", _fake_reflect)
    monkeypatch.setattr(profile_mod, "from_settings", lambda s: SimpleNamespace(source_language="en"))

    inp = {
        "user_id": str(uuid4()), "project_id": str(uuid4()), "chapter_id": str(uuid4()),
        "model_source": "user_model", "model_ref": "m1", "operation": "draft_chapter",
        "packed_prompt": "GROUNDING", "prompt_estimate": 20, "max_out": 4000,
        "present_entity_ids": ["e1", "e2"], "scene_sort_order": 3,
        "reasoning": "rule_based", "reasoning_effort": None, "reasoning_passthrough": True,
        "grounding_available": True, "reinjected_promise_count": 0, "reflect_max_iters": 1,
        "critic_source": None, "critic_ref": None,
    }
    out = await run_chapter_generate(object(), object(), object(), input=inp)
    assert out["text"] == "CHAPTER PROSE" and out["assembly_mode"] == "chapter"
    assert out["output_tokens"] == 12 + 4  # winner + revise tokens
    assert out["canon"]["status"] == "checked"
    assert out["persisted"] is False and out["draft_version"] is None  # Option A
    assert out["open_promise_count"] is None  # narrative_thread off
    assert out["max_output_tokens"] == 4000
    assert seen["k"] == 1  # single pass
    assert seen["reasoning_effort"] is None  # passthrough → omit effort


async def test_run_job_dispatches_selection_edit_via_worker_op(monkeypatch):
    job = _job(operation="rewrite", input={"worker_op": "selection_edit", "messages": []})
    repo = _FakeRepo(job)
    monkeypatch.setattr(jc, "GenerationJobsRepo", lambda pool: repo)

    captured: dict = {}

    async def _rse(llm, *, input, cancel_check=None):
        captured.update(input)
        return {"text": "edited prose", "persisted": False, "selection_edit": True}

    monkeypatch.setattr(jc, "run_selection_edit", _rse)
    out = await jc.run_job(object(), object(), job_id=str(job.id), user_id=str(job.user_id))
    assert out == "completed"
    assert repo.updates[-1][1]["text"] == "edited prose"
    assert captured["user_id"] == str(job.user_id)  # injected off the job row


async def test_run_selection_edit_drains_stream_to_final(monkeypatch):
    import app.engine.cowrite as cowrite_mod
    from app.engine.cowrite import DraftMetering
    from app.worker.operations import run_selection_edit

    async def _fake_stream(sdk, **kw):
        yield {"type": "token", "delta": "ed"}
        yield {"type": "usage", "text": "edited replacement",
               "metering": DraftMetering(20, 8, True, finish_reason="stop")}

    monkeypatch.setattr(cowrite_mod, "stream_draft", _fake_stream)
    inp = {
        "user_id": str(uuid4()), "model_source": "user_model", "model_ref": "m1",
        "messages": [{"role": "system", "content": "voice"},
                     {"role": "user", "content": "rewrite: the gate rose"}],
        "prompt_estimate": 5, "max_out": 512, "reasoning_passthrough": True,
        "reasoning_effort": None, "reasoning": "rule_based", "grounding_available": True,
    }
    out = await run_selection_edit(SimpleNamespace(sdk=object()), input=inp)
    assert out["text"] == "edited replacement" and out["output_tokens"] == 8
    assert out["finish_reason"] == "stop" and out["selection_edit"] is True
    assert out["persisted"] is False and out["grounding_available"] is True


async def test_run_selection_edit_no_output_is_terminal(monkeypatch):
    import app.engine.cowrite as cowrite_mod
    from app.worker.operations import run_selection_edit
    import pytest

    async def _empty_stream(sdk, **kw):
        if False:
            yield  # never yields a usage frame

    monkeypatch.setattr(cowrite_mod, "stream_draft", _empty_stream)
    inp = {"user_id": str(uuid4()), "model_source": "user_model", "model_ref": "m1",
           "messages": [], "prompt_estimate": 1, "max_out": 100}
    with pytest.raises(ValueError):  # no usage frame → run_job marks 'failed'
        await run_selection_edit(SimpleNamespace(sdk=object()), input=inp)


async def test_run_decompose_reconstructs_chapterplans_from_input(monkeypatch):
    import app.engine.plan as plan_mod

    @dataclasses.dataclass
    class _Res:
        tree: list

    captured: dict = {}

    async def _fake_decompose(llm, **kw):
        captured.update(kw)
        return _Res(tree=[{"scene": 1}])

    monkeypatch.setattr(plan_mod, "decompose", _fake_decompose)
    inp = {
        "model_source": "user_model", "model_ref": "m1", "premise": "a hero falls",
        "arc_title": "Hero's Journey", "beats": [],
        "chapters": [{"chapter_id": "c1", "title": "Ch1", "sort_order": 1,
                      "beat_role": None, "intent": ""}],
        "cast": [], "k_ceiling": 3, "high_threshold": 70,
        "min_scenes": 1, "max_scenes": 6, "source_language": "en",
    }
    out = await run_decompose(object(), user_id="u", input=inp)
    assert out == {"tree": [{"scene": 1}]}
    assert captured["premise"] == "a hero falls"
    # the chapter dict was reconstructed into a ChapterPlan dataclass
    assert captured["chapters"][0].chapter_id == "c1"
    assert captured["chapters"][0].title == "Ch1"


async def test_run_job_dispatches_plan_pipeline(monkeypatch):
    job = _job(operation="plan_pipeline", input={"worker_op": "plan_pipeline"})
    repo = _FakeRepo(job)
    monkeypatch.setattr(jc, "GenerationJobsRepo", lambda pool: repo)

    async def _rpp(pool, llm, *, user_id, input, cancel_check=None):
        return {"decompose": {"arc_title": "A"}, "heal_report": {"edits_applied": 3}}

    monkeypatch.setattr(jc, "run_plan_pipeline", _rpp)
    out = await jc.run_job(object(), object(), job_id=str(job.id), user_id=str(job.user_id))
    assert out == "completed"
    assert repo.updates[-1][1]["heal_report"]["edits_applied"] == 3


async def test_run_plan_pipeline_reconstructs_and_serializes(monkeypatch):
    import app.engine.planning_pipeline as pp_mod
    from app.engine.plan import ChapterPlan, ChapterScenes, DecomposeResult
    from app.engine.plan_heal import PlanHealReport
    from app.engine.planning_pipeline import PipelineResult

    captured: dict = {}

    async def _fake(llm, retriever, glossary, kal, **kw):
        captured.update(kw)
        dr = DecomposeResult(arc_title="A", chapters=[ChapterScenes(
            chapter=ChapterPlan("c1", "Ch1", 1, "hook", "i"), scenes=[])])
        return PipelineResult(decompose=dr, cast=[{"name": "Lâm Uyển"}], motifs=[],
                              char_arcs=[], heal_report=PlanHealReport(edits_applied=2))

    monkeypatch.setattr(pp_mod, "run_planning_pipeline", _fake)
    inp = {
        "model_source": "user_model", "model_ref": "m", "premise": "a hero falls",
        "beats": [{"key": "hook", "purpose": "establish"}],
        "chapters": [{"chapter_id": "c1", "title": "Ch1", "sort_order": 1,
                      "beat_role": None, "intent": ""}],
        "genre_tags": ["xianxia"], "book_id": "019f1783-ebb4-78de-ac9d-0dfba6539b7c",
        "project_id": "019f1783-ecca-7331-afab-9543762a8b68",
        "k_ceiling": 3, "high_threshold": 70, "min_scenes": 2, "max_scenes": 4,
        "source_language": "vi", "self_heal": True,
    }
    out = await run_plan_pipeline(object(), object(), user_id="u", input=inp)
    # serialized (asdict) — nested dataclasses flattened
    assert out["decompose"]["arc_title"] == "A"
    assert out["heal_report"]["edits_applied"] == 2 and out["cast"][0]["name"] == "Lâm Uyển"
    # inputs reconstructed + threaded
    assert captured["premise"] == "a hero falls" and captured["genre_tags"] == ["xianxia"]
    assert captured["chapters"][0].chapter_id == "c1"   # dict → ChapterPlan


async def test_run_job_dispatches_self_heal_propose(monkeypatch):
    job = _job(operation="self_heal_propose", input={"worker_op": "self_heal_propose"})
    repo = _FakeRepo(job)
    monkeypatch.setattr(jc, "GenerationJobsRepo", lambda pool: repo)

    async def _rshp(llm, *, user_id, input, cancel_check=None):
        return {"proposals": [{"id": "e0"}], "stats": {"edits": 1}}

    monkeypatch.setattr(jc, "run_self_heal_propose", _rshp)
    out = await jc.run_job(object(), object(), job_id=str(job.id), user_id=str(job.user_id))
    assert out == "completed"
    assert repo.updates[-1][1]["stats"]["edits"] == 1


async def test_run_self_heal_propose_serializes(monkeypatch):
    import app.engine.self_heal as sh
    from app.engine.self_heal import EditProposal, Finding, SelfHealReport
    from app.worker.operations import run_self_heal_propose

    async def _fake_propose(llm, *, user_id, model_source, model_ref, chapter, source_language,
                            canon, prefilter, rerank, cancel_check=None):
        props = [EditProposal(id="e0", type="xưng hô (code)", tier="deterministic", start=0,
                              end=3, before="ông", after="lão", issue="i", fix="f")]
        rep = SelfHealReport(
            findings=[Finding(type="t", span="s", issue="i", fix="f", skip_reason="refuted")],
            located=1, edits_applied=1, rejudge_before=2)
        return props, rep

    monkeypatch.setattr(sh, "propose_self_heal", _fake_propose)
    out = await run_self_heal_propose(
        object(), user_id="u",
        input={"chapter_text": "ông đi.", "model_source": "user_model", "model_ref": "m",
               "chapter_id": "c1", "draft_version": 7, "source_language": "vi"})
    assert out["proposals"][0]["after"] == "lão"
    assert out["proposals"][0]["tier"] == "deterministic"
    assert out["source_text"] == "ông đi." and out["draft_version"] == 7
    assert out["stats"] == {"findings": 2, "located": 1, "edits": 1, "refuted": 1}


async def test_run_job_dispatches_quality_report(monkeypatch):
    job = _job(operation="quality_report", input={"worker_op": "quality_report"})
    repo = _FakeRepo(job)
    monkeypatch.setattr(jc, "GenerationJobsRepo", lambda pool: repo)

    async def _rqr(llm, *, user_id, input, cancel_check=None):
        return {"report": {"critic": {"coherence": 4}, "promises": {"dropped": []}}}

    monkeypatch.setattr(jc, "run_quality_report", _rqr)
    out = await jc.run_job(object(), object(), job_id=str(job.id), user_id=str(job.user_id))
    assert out == "completed"
    assert repo.updates[-1][1]["report"]["critic"]["coherence"] == 4


async def test_run_quality_report_serializes(monkeypatch):
    import app.engine.quality_report as qr
    from app.worker.operations import run_quality_report

    async def _fake_report(llm, *, user_id, model_source, model_ref, chapter, source_language,
                           canon, cancel_check=None):
        return {"critic": {"coherence": 5, "violations": []},
                "threads": {"raised": ["the debt"], "raised_count": 1}}

    monkeypatch.setattr(qr, "build_quality_report", _fake_report)
    out = await run_quality_report(
        object(), user_id="u",
        input={"chapter_text": "prose.", "model_source": "user_model", "model_ref": "m",
               "chapter_id": "c1", "draft_version": 7, "source_language": "vi",
               "canon": "CANON"})
    assert out["report"]["critic"]["coherence"] == 5
    assert out["report"]["threads"]["raised"] == ["the debt"]
    assert out["chapter_id"] == "c1" and out["draft_version"] == 7


async def test_run_job_dispatches_promise_coverage(monkeypatch):
    job = _job(operation="promise_coverage", input={"worker_op": "promise_coverage"})
    repo = _FakeRepo(job)
    monkeypatch.setattr(jc, "GenerationJobsRepo", lambda pool: repo)

    async def _rpc(llm, *, user_id, input, cancel_check=None):
        return {"coverage": {"tracked_count": 3, "abandoned_count": 1}, "chapters": 12}

    monkeypatch.setattr(jc, "run_promise_coverage", _rpc)
    out = await jc.run_job(object(), object(), job_id=str(job.id), user_id=str(job.user_id))
    assert out == "completed"
    assert repo.updates[-1][1]["coverage"]["tracked_count"] == 3


async def test_run_promise_coverage_serializes(monkeypatch):
    import app.engine.quality_report as qr
    from app.worker.operations import run_promise_coverage

    async def _fake_cov(llm, *, user_id, model_source, model_ref, premise, plan_text,
                        book_text, source_language, window_chars=None, cancel_check=None):
        assert premise == "" and "Ch1" in plan_text and book_text
        return {"tracked_count": 2, "paid_count": 1, "abandoned_count": 1, "abandon_rate": 0.5}

    monkeypatch.setattr(qr, "build_promise_coverage", _fake_cov)
    out = await run_promise_coverage(
        _llm_stub(), user_id="u",
        input={"premise": "", "plan_text": "## Ch1: a debt", "book_text": "the book prose",
               "chapters": 12, "model_source": "user_model", "model_ref": "m",
               "source_language": "vi"})
    assert out["coverage"]["abandon_rate"] == 0.5
    assert out["chapters"] == 12
