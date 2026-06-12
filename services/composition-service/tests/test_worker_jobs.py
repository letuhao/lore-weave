"""composition batch-job worker — foundation (Phase 3 M4).

The consumer's run_job orchestration (idempotent dispatch + business-fail), the
message branch, and run_decompose's reconstruction from the persisted input. All
fakes — no Redis, no DB, no real LLM.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from uuid import uuid4

from app.worker import job_consumer as jc
from app.worker.operations import run_decompose


class _FakeRepo:
    def __init__(self, job):
        self._job = job
        self.updates: list = []

    async def get(self, uid, jid):
        return self._job

    async def update_status(self, uid, jid, status, *, result=None, **kw):
        self.updates.append((status, result))
        return self._job


def _job(operation="decompose_preview", status="pending", input=None):
    return SimpleNamespace(
        id=uuid4(), user_id=uuid4(), project_id=uuid4(), operation=operation,
        status=status, input=input if input is not None else {},
    )


def _patch_run_job(monkeypatch, repo, *, result=None, raises=None):
    monkeypatch.setattr(jc, "GenerationJobsRepo", lambda pool: repo)

    async def _rd(llm, *, user_id, input):
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

    async def _rs(pool, llm, knowledge, *, input):
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
        async def get(self, uid, pid):
            return SimpleNamespace(settings={"source_language": "en"})

    class _FakeJobsRepo:
        def __init__(self, pool): ...
        async def chapter_scene_drafts(self, uid, pid, cid):
            return ["scene 1 draft", "scene 2 draft"]

    async def _fake_stitch(llm, **kw):
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
    out = await run_stitch(object(), object(), object(), input=inp)
    assert out["text"] == "STITCHED PROSE"
    assert out["stitched"] is True
    assert out["persisted"] is False  # Option A — persist is the separate bearer step
    assert out["canon"]["status"] == "ok"


async def test_run_stitch_raises_when_no_drafts(monkeypatch):
    import app.db.repositories.works as works_mod
    import app.db.repositories.generation_jobs as gj_mod
    import app.packer.profile as profile_mod
    from app.worker.operations import run_stitch
    import pytest

    class _FakeWorks:
        def __init__(self, pool): ...
        async def get(self, uid, pid):
            return SimpleNamespace(settings={})

    class _FakeJobsRepo:
        def __init__(self, pool): ...
        async def chapter_scene_drafts(self, uid, pid, cid):
            return []  # nothing to stitch

    monkeypatch.setattr(works_mod, "WorksRepo", _FakeWorks)
    monkeypatch.setattr(gj_mod, "GenerationJobsRepo", _FakeJobsRepo)
    monkeypatch.setattr(profile_mod, "from_settings", lambda s: SimpleNamespace(source_language="en"))
    inp = {"user_id": str(uuid4()), "project_id": str(uuid4()), "chapter_id": str(uuid4())}
    with pytest.raises(ValueError):  # business error → run_job marks 'failed'
        await run_stitch(object(), object(), object(), input=inp)


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
