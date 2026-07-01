"""PlanForge HTTP router tests (M3)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.db.models import PlanRun
from app.main import app
from app.middleware.jwt_auth import get_current_user
from app.deps import get_grant_client_dep, get_plan_forge_service

USER = uuid.uuid4()
BOOK = uuid.uuid4()
RUN = uuid.uuid4()


class StubGrant:
    async def resolve_grant(self, book_id, caller):
        from app.grant_client import GrantLevel
        return GrantLevel.EDIT


class StubPlanForge:
    def __init__(self):
        self.run = PlanRun(
            id=RUN, owner_user_id=USER, book_id=BOOK, mode="rules", status="proposed",
        )

    async def create_run(self, owner_user_id, book_id, **kwargs):
        if kwargs.get("mode") == "llm" and kwargs.get("model_ref") is None:
            raise ValueError("model_ref required when mode=llm")
        return self.run, False, None

    async def get_run_detail(self, owner_user_id, book_id, run_id):
        if run_id != RUN:
            return None
        return {
            "id": str(RUN), "book_id": str(BOOK), "status": "proposed", "mode": "rules",
            "model_ref": None, "source_checksum": "abc", "active_job_id": None,
            "job_status": None, "error_detail": None, "checkpoint_state": {},
            "artifacts": [{"kind": "spec", "artifact_id": str(uuid.uuid4())}],
            "created_at": "2026-07-01T00:00:00+00:00",
            "updated_at": "2026-07-01T00:00:00+00:00",
        }

    async def list_runs(self, owner_user_id, book_id, *, limit, cursor):
        detail = await self.get_run_detail(owner_user_id, book_id, RUN)
        return {"items": [detail], "next_cursor": None}

    async def patch_spec(self, owner_user_id, book_id, run_id, patch):
        return await self.get_run_detail(owner_user_id, book_id, run_id)

    async def validate(self, owner_user_id, book_id, run_id):
        return {"passed": True, "rules": [], "fidelity_score": 0.9, "fidelity_report_id": None}

    async def refine(self, owner_user_id, book_id, run_id, **kwargs):
        return "sync", {"status": "no_change", "spec_artifact_id": str(uuid.uuid4())}

    async def interpret(self, owner_user_id, book_id, run_id, **kwargs):
        return {"intent": "clarify", "version": 1}

    async def self_check(self, owner_user_id, book_id, run_id):
        return {"gaps": [], "fidelity_score": 0.8}

    async def compile(self, owner_user_id, book_id, run_id, **kwargs):
        return "sync", {"package": {"arc_id": "arc_2"}, "pipeline_job_id": None, "work_id": str(uuid.uuid4())}


@pytest.fixture
def client():
    stub = StubPlanForge()
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_grant_client_dep] = lambda: StubGrant()
    app.dependency_overrides[get_plan_forge_service] = lambda: stub
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_plan_run_rules_201(client):
    r = client.post(
        f"/v1/composition/books/{BOOK}/plan/runs",
        json={"source_markdown": "# 1. Test\nbody", "mode": "rules"},
    )
    assert r.status_code == 201
    assert r.json()["status"] == "proposed"


def test_get_plan_run(client):
    r = client.get(f"/v1/composition/books/{BOOK}/plan/runs/{RUN}")
    assert r.status_code == 200
    assert r.json()["id"] == str(RUN)


def test_list_plan_runs(client):
    r = client.get(f"/v1/composition/books/{BOOK}/plan/runs")
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1


def test_validate_plan_run(client):
    r = client.post(f"/v1/composition/books/{BOOK}/plan/runs/{RUN}/validate")
    assert r.status_code == 200
    assert r.json()["passed"] is True


def test_compile_plan_run(client):
    r = client.post(
        f"/v1/composition/books/{BOOK}/plan/runs/{RUN}/compile",
        json={"arc_id": "arc_2"},
    )
    assert r.status_code == 200
    assert r.json()["package"]["arc_id"] == "arc_2"


def test_create_llm_requires_model_ref(client):
    r = client.post(
        f"/v1/composition/books/{BOOK}/plan/runs",
        json={"source_markdown": "x", "mode": "llm"},
    )
    assert r.status_code == 400
