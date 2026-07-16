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
ART = uuid.uuid4()


class StubGrant:
    async def resolve_grant(self, book_id, caller):
        from app.grant_client import GrantLevel
        return GrantLevel.EDIT


class StubPlanForge:
    def __init__(self):
        self.run = PlanRun(
            id=RUN, created_by=USER, book_id=BOOK, mode="rules", status="proposed",
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
            "arcs": [{"id": "arc_2", "title": "Arc 2"}],
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

    async def get_artifact(self, owner_user_id, book_id, run_id, artifact_id):
        # Mirrors artifacts_by_ids' scoping: a foreign book_id, a foreign run, or an unknown
        # artifact_id ALL collapse to None → one 404, never a 403 oracle (H13).
        if book_id != BOOK or run_id != RUN or artifact_id != ART:
            return None
        return {
            "artifact_id": str(ART), "kind": "cast_plan",
            "content": {"roster": []}, "created_at": "2026-07-01T00:00:00+00:00",
        }


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


def test_get_plan_artifact_200(client):
    r = client.get(f"/v1/composition/books/{BOOK}/plan/runs/{RUN}/artifacts/{ART}")
    assert r.status_code == 200
    assert set(r.json()) == {"artifact_id", "kind", "content", "created_at"}
    assert r.json()["artifact_id"] == str(ART)


def test_get_plan_artifact_unknown_is_404(client):
    r = client.get(f"/v1/composition/books/{BOOK}/plan/runs/{RUN}/artifacts/{uuid.uuid4()}")
    assert r.status_code == 404


def test_get_plan_artifact_cross_book_is_404_not_403(client):
    # H13: a foreign artifact must be indistinguishable from a missing one — one 404, never a
    # 403 that would confirm the id exists in another tenant (enumeration oracle).
    other_book = uuid.uuid4()
    r = client.get(f"/v1/composition/books/{other_book}/plan/runs/{RUN}/artifacts/{ART}")
    assert r.status_code == 404
    assert r.status_code != 403


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


def test_patch_novel_system_spec_200(client):
    r = client.patch(
        f"/v1/composition/books/{BOOK}/plan/runs/{RUN}/novel-system-spec",
        json={"title": "New title"},
    )
    assert r.status_code == 200
    assert r.json()["id"] == str(RUN)


def test_patch_no_spec_maps_to_422_not_409(client):
    # patch_spec raises ValueError ONLY for the no-spec-yet state — an edit-merge
    # (last-write-wins) has no OCC conflict, so the router must return 422
    # (unprocessable), never 409 (which would wrongly tell the client to
    # refetch-and-retry a conflict that doesn't exist). Review-impl fix (Wave P1).
    async def _raise(*a, **k):
        raise ValueError("no spec artifact to patch")

    stub = app.dependency_overrides[get_plan_forge_service]()
    stub.patch_spec = _raise
    r = client.patch(
        f"/v1/composition/books/{BOOK}/plan/runs/{RUN}/novel-system-spec",
        json={"title": "x"},
    )
    assert r.status_code == 422
    assert "spec" in r.json()["detail"]
