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
        id=uuid4(), user_id=uuid4(), operation=operation, status=status,
        input=input if input is not None else {},
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
