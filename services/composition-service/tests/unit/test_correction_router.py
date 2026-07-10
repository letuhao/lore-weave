"""Correction-capture router tests (V1 flywheel slice 1, §3) — TestClient.

Repos stubbed; the real repo's txn-local emit is exercised in the integration
suite (test_repositories.py). Here we lock the router's validation + the §5
opt-in raw-prose gating + the H2 taxonomy (no `accept`).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.db.models import CompositionWork, GenerationCorrection, GenerationJob
from app.db.repositories import ReferenceViolationError
from app.db.repositories.generation_corrections import count_changed_blocks

USER = uuid.uuid4()
PROJECT = uuid.uuid4()
BOOK = uuid.uuid4()
JOB = uuid.uuid4()


def _work(settings=None):
    return CompositionWork(project_id=PROJECT, created_by=USER, book_id=BOOK, settings=settings or {})


def _job(result=None):
    return GenerationJob(id=JOB, created_by=USER, project_id=PROJECT, book_id=BOOK,
                         operation="draft_scene",
                         status="completed", result=result if result is not None else {"text": "winner prose"})


class StubWorks:
    def __init__(self): self.work = _work()
    async def get(self, p): return self.work


class StubJobs:
    def __init__(self): self.job = _job()
    async def get(self, jid): return self.job


class StubCorrections:
    def __init__(self):
        self.calls = []
        self.raise_ref = False
    async def create(self, project_id, job_id, *, created_by=None, **kw):
        if self.raise_ref:
            raise ReferenceViolationError("cross-user/project")
        self.calls.append(kw)
        return GenerationCorrection(
            id=uuid.uuid4(), created_by=created_by, project_id=project_id, job_id=job_id,
            kind=kw["kind"], chosen_candidate_index=kw.get("chosen_candidate_index"),
            guidance=kw.get("guidance"), changed_blocks=kw.get("changed_blocks"),
            raw_before=kw.get("raw_before"), raw_after=kw.get("raw_after"),
            regenerated_to_job_id=kw.get("regenerated_to_job_id"),
        )
    async def correction_stats(self, project_id):
        from app.db.models import CorrectionStats, ModeCorrectionStats
        return CorrectionStats(project_id=project_id, by_mode=[
            ModeCorrectionStats(mode="auto", generations=4, corrected_jobs=2, accept_rate=0.5,
                                edit_rate=0.25, pick_different_rate=0.25, regenerate_rate=0.0,
                                reject_rate=0.0, avg_edit_magnitude=3.0),
            ModeCorrectionStats(mode="cowrite", generations=2, corrected_jobs=1, accept_rate=0.5,
                                regenerate_rate=0.5),
        ])


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())

    from app.main import app
    from app.deps import (get_generation_corrections_repo, get_generation_jobs_repo,
                          get_grant_client_dep, get_works_repo)
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_current_user

    # E0 book-grant authority stubbed at OWNER; the correction endpoints now
    # _gate_work (resolve the Work's book, then gate) before acting.
    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER
        async def resolve_access(self, book_id, user_id):
            return GrantLevel.OWNER, "active"

    works, jobs, corr = StubWorks(), StubJobs(), StubCorrections()
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_works_repo] = lambda: works
    app.dependency_overrides[get_generation_jobs_repo] = lambda: jobs
    app.dependency_overrides[get_generation_corrections_repo] = lambda: corr
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    with TestClient(app) as c:
        yield c, works, jobs, corr
    app.dependency_overrides.clear()


def _url():
    return f"/v1/composition/jobs/{JOB}/correction"


# ── happy paths per kind ──

def test_edit_records_changed_blocks(ctx):
    c, _, jobs, corr = ctx
    jobs.job = _job({"text": "line one\nline two"})
    r = c.post(_url(), json={"kind": "edit", "edited_text": "line one\nline TWO edited"})
    assert r.status_code == 201
    kw = corr.calls[0]
    assert kw["kind"] == "edit"
    assert kw["changed_blocks"] == 1  # one of two lines differs


def test_edit_without_edited_text_422(ctx):
    c, *_ = ctx
    assert c.post(_url(), json={"kind": "edit"}).status_code == 422


def test_edit_with_no_change_rejected_422(ctx):
    # /review-impl MED#3: edited_text == winner is a disguised accept (H2 self-
    # reinforcement) → rejected, nothing stored.
    c, _, jobs, corr = ctx
    jobs.job = _job({"text": "same prose"})
    r = c.post(_url(), json={"kind": "edit", "edited_text": "same prose"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "EDIT_NO_CHANGE"
    assert corr.calls == []  # no row, no event


def test_oversized_guidance_rejected_422_before_write(ctx):
    # /review-impl MED#1: a >20k guidance must 422 at validation, NOT commit the
    # row+event and then 500 on read-back (capped row model).
    c, _, _, corr = ctx
    r = c.post(_url(), json={"kind": "regenerate", "guidance": "x" * 20001})
    assert r.status_code == 422
    assert corr.calls == []


def test_pick_different_records_index(ctx):
    c, _, jobs, corr = ctx
    jobs.job = _job({"text": "winner", "candidates": ["A", "B", "winner"], "winner_index": 2})
    r = c.post(_url(), json={"kind": "pick_different", "chosen_candidate_index": 1})
    assert r.status_code == 201
    kw = corr.calls[0]
    assert kw["chosen_candidate_index"] == 1
    # LOW#4: the winner (i) + k are forwarded for slice-2 `j ≻ i` reconstruction
    assert kw["winner_index"] == 2 and kw["candidate_count"] == 3


def test_pick_different_without_index_422(ctx):
    c, *_ = ctx
    assert c.post(_url(), json={"kind": "pick_different"}).status_code == 422


def test_pick_different_out_of_range_422(ctx):
    c, _, jobs, _ = ctx
    jobs.job = _job({"text": "winner", "candidates": ["A", "B"]})
    r = c.post(_url(), json={"kind": "pick_different", "chosen_candidate_index": 5})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "CANDIDATE_INDEX_OUT_OF_RANGE"


def test_regenerate_records_guidance(ctx):
    c, _, _, corr = ctx
    r = c.post(_url(), json={"kind": "regenerate", "guidance": "darker tone"})
    assert r.status_code == 201
    assert corr.calls[0]["guidance"] == "darker tone"


def test_reject_records(ctx):
    c, _, _, corr = ctx
    r = c.post(_url(), json={"kind": "reject"})
    assert r.status_code == 201 and corr.calls[0]["kind"] == "reject"


def test_accept_is_not_a_valid_kind_422(ctx):
    # H2: accept-as-is is NOT a correction (self-reinforcement) → rejected by the
    # CorrectionKind Literal at validation.
    c, *_ = ctx
    assert c.post(_url(), json={"kind": "accept"}).status_code == 422


# ── §5 opt-in raw prose gating ──

def test_raw_prose_not_captured_by_default(ctx):
    c, _, jobs, corr = ctx
    jobs.job = _job({"text": "winner prose"})
    c.post(_url(), json={"kind": "edit", "edited_text": "edited prose"})
    kw = corr.calls[0]
    assert kw["raw_before"] is None and kw["raw_after"] is None  # default off


def test_raw_prose_captured_when_opted_in(ctx):
    c, works, jobs, corr = ctx
    works.work = _work({"capture_correction_prose": True})
    jobs.job = _job({"text": "winner prose"})
    c.post(_url(), json={"kind": "edit", "edited_text": "edited prose"})
    kw = corr.calls[0]
    assert kw["raw_before"] == "winner prose" and kw["raw_after"] == "edited prose"


def test_raw_prose_pick_different_captures_chosen(ctx):
    c, works, jobs, corr = ctx
    works.work = _work({"capture_correction_prose": True})
    jobs.job = _job({"text": "winner", "candidates": ["A", "chosen B"]})
    c.post(_url(), json={"kind": "pick_different", "chosen_candidate_index": 1})
    kw = corr.calls[0]
    assert kw["raw_before"] == "winner" and kw["raw_after"] == "chosen B"


# ── not-found paths ──

def test_job_not_found_404(ctx):
    c, _, jobs, _ = ctx
    jobs.get = AsyncMock(return_value=None)
    assert c.post(_url(), json={"kind": "reject"}).status_code == 404


def test_work_not_found_404(ctx):
    c, works, _, _ = ctx
    works.get = AsyncMock(return_value=None)
    assert c.post(_url(), json={"kind": "reject"}).status_code == 404


def test_reference_violation_maps_to_404(ctx):
    c, _, _, corr = ctx
    corr.raise_ref = True
    assert c.post(_url(), json={"kind": "reject"}).status_code == 404


# ── correction-stats endpoint (slice 5) ──

def test_correction_stats_happy(ctx):
    c, *_ = ctx
    r = c.get(f"/v1/composition/works/{PROJECT}/correction-stats")
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"] == str(PROJECT)
    modes = {m["mode"]: m for m in body["by_mode"]}
    assert modes["auto"]["accept_rate"] == 0.5
    assert modes["auto"]["avg_edit_magnitude"] == 3.0
    assert "cowrite" in modes  # both modes always present for the A/B


def test_correction_stats_404_when_no_work(ctx):
    c, works, _, _ = ctx
    works.get = AsyncMock(return_value=None)
    assert c.get(f"/v1/composition/works/{PROJECT}/correction-stats").status_code == 404


# ── pure: count_changed_blocks ──

def test_count_changed_blocks_identical_is_zero():
    assert count_changed_blocks("a\nb\nc", "a\nb\nc") == 0


def test_count_changed_blocks_detects_change():
    assert count_changed_blocks("a\nb\nc", "a\nB\nc") >= 1


def test_count_changed_blocks_empty_to_text():
    assert count_changed_blocks("", "new line") >= 1
