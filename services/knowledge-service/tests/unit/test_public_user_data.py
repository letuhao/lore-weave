"""Unit tests for K7.5 + K7.6 — /v1/knowledge/user-data endpoints.

Same pattern as test_public_summaries: mount the real router on a
fresh FastAPI app, override repo deps + get_current_user with
in-memory fakes. No Postgres required.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models import Project, ScopeType, Summary
from app.db.repositories.projects import ProjectsRepo
from app.db.repositories.summaries import SummariesRepo
from app.deps import get_projects_repo, get_summaries_repo, get_user_data_repo
from app.middleware.jwt_auth import get_current_user
from app.routers.public.user_data import router as user_data_router


# ── fakes ────────────────────────────────────────────────────────────────


def _make_project(
    user_id: UUID,
    *,
    name: str = "p",
    is_archived: bool = False,
) -> Project:
    now = datetime.now(timezone.utc)
    return Project(
        project_id=uuid4(),
        user_id=user_id,
        name=name,
        description="",
        project_type="general",
        book_id=None,
        instructions="",
        extraction_enabled=False,
        extraction_status="disabled",
        embedding_model=None,
        extraction_config={},
        last_extracted_at=None,
        estimated_cost_usd=Decimal("0"),
        actual_cost_usd=Decimal("0"),
        is_archived=is_archived,
        version=1,
        created_at=now,
        updated_at=now,
    )


def _make_summary(
    user_id: UUID,
    scope_type: ScopeType,
    scope_id: UUID | None,
    content: str = "x",
) -> Summary:
    now = datetime.now(timezone.utc)
    return Summary(
        summary_id=uuid4(),
        user_id=user_id,
        scope_type=scope_type,
        scope_id=scope_id,
        content=content,
        token_count=1,
        version=1,
        created_at=now,
        updated_at=now,
    )


class FakeProjectsRepo:
    def __init__(self) -> None:
        self._rows: list[Project] = []

    def seed(self, p: Project) -> None:
        self._rows.append(p)

    async def list_all_for_user(self, user_id: UUID) -> list[Project]:
        rows = [p for p in self._rows if p.user_id == user_id]
        # Cap+1 mirror so the overflow path in the route is testable.
        return rows[: ProjectsRepo.EXPORT_HARD_CAP + 1]


class FakeSummariesRepo:
    def __init__(self) -> None:
        self._rows: list[Summary] = []

    def seed(self, s: Summary) -> None:
        self._rows.append(s)

    async def list_for_user(self, user_id: UUID) -> list[Summary]:
        return [s for s in self._rows if s.user_id == user_id]

    async def list_all_for_user(self, user_id: UUID) -> list[Summary]:
        rows = [s for s in self._rows if s.user_id == user_id]
        return rows[: SummariesRepo.EXPORT_HARD_CAP + 1]


class FakeUserDataRepo:
    def __init__(
        self,
        projects: FakeProjectsRepo,
        summaries: FakeSummariesRepo,
    ) -> None:
        self._projects = projects
        self._summaries = summaries
        self.fail_mode: str | None = None

    async def delete_all_for_user(self, user_id: UUID) -> dict[str, int]:
        if self.fail_mode == "raise":
            # Simulate a DB error — router should NOT swallow, rows stay.
            raise RuntimeError("boom")
        s_before = len(self._summaries._rows)
        p_before = len(self._projects._rows)
        self._summaries._rows = [
            s for s in self._summaries._rows if s.user_id != user_id
        ]
        self._projects._rows = [
            p for p in self._projects._rows if p.user_id != user_id
        ]
        return {
            "summaries": s_before - len(self._summaries._rows),
            "projects": p_before - len(self._projects._rows),
        }


# ── fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def projects_repo() -> FakeProjectsRepo:
    return FakeProjectsRepo()


@pytest.fixture
def summaries_repo() -> FakeSummariesRepo:
    return FakeSummariesRepo()


@pytest.fixture
def user_data_repo(
    projects_repo: FakeProjectsRepo,
    summaries_repo: FakeSummariesRepo,
) -> FakeUserDataRepo:
    return FakeUserDataRepo(projects_repo, summaries_repo)


@pytest.fixture
def auth_user_id() -> UUID:
    return uuid4()


@pytest.fixture
def client(
    projects_repo: FakeProjectsRepo,
    summaries_repo: FakeSummariesRepo,
    user_data_repo: FakeUserDataRepo,
    auth_user_id: UUID,
) -> TestClient:
    app = FastAPI()
    app.include_router(user_data_router)
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo
    app.dependency_overrides[get_summaries_repo] = lambda: summaries_repo
    app.dependency_overrides[get_user_data_repo] = lambda: user_data_repo
    app.dependency_overrides[get_current_user] = lambda: auth_user_id
    return TestClient(app)


# ── GET /v1/knowledge/user-data/export ───────────────────────────────────


def test_export_empty_user(
    client: TestClient, auth_user_id: UUID, caplog: pytest.LogCaptureFixture
):
    import logging
    with caplog.at_level(logging.INFO, logger="app.routers.public.user_data"):
        resp = client.get("/v1/knowledge/user-data/export")
    assert resp.status_code == 200
    body = resp.json()
    assert body["schema_version"] == 1
    assert body["user_id"] == str(auth_user_id)
    assert body["projects"] == []
    assert body["summaries"] == []
    assert "exported_at" in body
    # I2: GDPR audit trail — every export is logged with user_id + counts.
    assert any(
        "gdpr.export" in rec.message and str(auth_user_id) in rec.message
        for rec in caplog.records
    )


def test_export_content_disposition_header(
    client: TestClient, auth_user_id: UUID
):
    resp = client.get("/v1/knowledge/user-data/export")
    cd = resp.headers["content-disposition"]
    assert "attachment" in cd
    assert f"loreweave-knowledge-export-{auth_user_id}" in cd
    assert ".json" in cd


def test_export_includes_projects_and_summaries(
    client: TestClient,
    projects_repo: FakeProjectsRepo,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    p = _make_project(auth_user_id, name="alpha")
    projects_repo.seed(p)
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "bio"))
    summaries_repo.seed(_make_summary(auth_user_id, "project", p.project_id, "ps"))
    body = client.get("/v1/knowledge/user-data/export").json()
    assert len(body["projects"]) == 1
    assert body["projects"][0]["name"] == "alpha"
    assert len(body["summaries"]) == 2
    contents = {s["content"] for s in body["summaries"]}
    assert contents == {"bio", "ps"}


def test_export_includes_archived_projects(
    client: TestClient,
    projects_repo: FakeProjectsRepo,
    auth_user_id: UUID,
):
    projects_repo.seed(_make_project(auth_user_id, name="active"))
    projects_repo.seed(
        _make_project(auth_user_id, name="archived", is_archived=True)
    )
    body = client.get("/v1/knowledge/user-data/export").json()
    names = {p["name"] for p in body["projects"]}
    assert names == {"active", "archived"}


def test_export_isolates_other_users(
    client: TestClient,
    projects_repo: FakeProjectsRepo,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    other = uuid4()
    projects_repo.seed(_make_project(auth_user_id, name="mine"))
    projects_repo.seed(_make_project(other, name="theirs"))
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "mine"))
    summaries_repo.seed(_make_summary(other, "global", None, "theirs"))
    body = client.get("/v1/knowledge/user-data/export").json()
    assert [p["name"] for p in body["projects"]] == ["mine"]
    assert [s["content"] for s in body["summaries"]] == ["mine"]


def test_export_overflow_returns_507(
    client: TestClient,
    projects_repo: FakeProjectsRepo,
    auth_user_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
):
    """Lower the cap so the test doesn't have to seed 10k rows."""
    monkeypatch.setattr(ProjectsRepo, "EXPORT_HARD_CAP", 3)
    for _ in range(4):  # cap + 1
        projects_repo.seed(_make_project(auth_user_id))
    resp = client.get("/v1/knowledge/user-data/export")
    assert resp.status_code == 507
    assert "exceeds 3" in resp.json()["detail"]


def test_export_summaries_overflow_returns_507(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
):
    """I1 fix: summaries overflow must hard-fail, not silently truncate
    — a partial GDPR export would violate the 'complete copy' rule."""
    monkeypatch.setattr(SummariesRepo, "EXPORT_HARD_CAP", 2)
    for _ in range(3):
        summaries_repo.seed(_make_summary(auth_user_id, "global", None))
    resp = client.get("/v1/knowledge/user-data/export")
    assert resp.status_code == 507
    assert "exceeds 2" in resp.json()["detail"]


def test_export_exactly_at_cap_returns_200(
    client: TestClient,
    projects_repo: FakeProjectsRepo,
    auth_user_id: UUID,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(ProjectsRepo, "EXPORT_HARD_CAP", 3)
    for _ in range(3):
        projects_repo.seed(_make_project(auth_user_id))
    resp = client.get("/v1/knowledge/user-data/export")
    assert resp.status_code == 200
    assert len(resp.json()["projects"]) == 3


# ── DELETE /v1/knowledge/user-data ───────────────────────────────────────


def test_delete_empty_user(
    client: TestClient, auth_user_id: UUID, caplog: pytest.LogCaptureFixture
):
    import logging
    with caplog.at_level(logging.INFO, logger="app.routers.public.user_data"):
        resp = client.delete("/v1/knowledge/user-data")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": {"summaries": 0, "projects": 0}}
    # I2: GDPR audit trail — erasure is logged with user_id + counts.
    assert any(
        "gdpr.erasure" in rec.message and str(auth_user_id) in rec.message
        for rec in caplog.records
    )


def test_delete_returns_counts(
    client: TestClient,
    projects_repo: FakeProjectsRepo,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    p = _make_project(auth_user_id)
    projects_repo.seed(p)
    projects_repo.seed(_make_project(auth_user_id))
    summaries_repo.seed(_make_summary(auth_user_id, "global", None))
    summaries_repo.seed(_make_summary(auth_user_id, "project", p.project_id))
    summaries_repo.seed(_make_summary(auth_user_id, "project", uuid4()))
    resp = client.delete("/v1/knowledge/user-data")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": {"summaries": 3, "projects": 2}}
    # And the fakes are actually empty for this user now.
    assert summaries_repo._rows == []
    assert projects_repo._rows == []


def test_delete_isolates_other_users(
    client: TestClient,
    projects_repo: FakeProjectsRepo,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    other = uuid4()
    projects_repo.seed(_make_project(auth_user_id))
    projects_repo.seed(_make_project(other, name="safe"))
    summaries_repo.seed(_make_summary(auth_user_id, "global", None))
    summaries_repo.seed(_make_summary(other, "global", None, "safe"))
    resp = client.delete("/v1/knowledge/user-data")
    assert resp.json() == {"deleted": {"summaries": 1, "projects": 1}}
    # Other user's rows survive.
    assert len(projects_repo._rows) == 1
    assert projects_repo._rows[0].name == "safe"
    assert len(summaries_repo._rows) == 1
    assert summaries_repo._rows[0].content == "safe"


def test_delete_repo_failure_propagates_as_500(
    projects_repo: FakeProjectsRepo,
    summaries_repo: FakeSummariesRepo,
    user_data_repo: FakeUserDataRepo,
    auth_user_id: UUID,
):
    """If the repo raises (simulating a rolled-back transaction), the
    route must not return 200 — the user needs to know the delete
    didn't succeed so they can retry."""
    projects_repo.seed(_make_project(auth_user_id))
    summaries_repo.seed(_make_summary(auth_user_id, "global", None))
    user_data_repo.fail_mode = "raise"
    app = FastAPI()
    app.include_router(user_data_router)
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo
    app.dependency_overrides[get_summaries_repo] = lambda: summaries_repo
    app.dependency_overrides[get_user_data_repo] = lambda: user_data_repo
    app.dependency_overrides[get_current_user] = lambda: auth_user_id
    c = TestClient(app, raise_server_exceptions=False)
    resp = c.delete("/v1/knowledge/user-data")
    assert resp.status_code == 500
    # Rows still present — rollback semantics preserved.
    assert len(projects_repo._rows) == 1
    assert len(summaries_repo._rows) == 1


# ── auth ─────────────────────────────────────────────────────────────────


def test_no_jwt_returns_401_on_all_routes(
    projects_repo: FakeProjectsRepo,
    summaries_repo: FakeSummariesRepo,
    user_data_repo: FakeUserDataRepo,
):
    app = FastAPI()
    app.include_router(user_data_router)
    app.dependency_overrides[get_projects_repo] = lambda: projects_repo
    app.dependency_overrides[get_summaries_repo] = lambda: summaries_repo
    app.dependency_overrides[get_user_data_repo] = lambda: user_data_repo
    raw = TestClient(app)
    assert raw.get("/v1/knowledge/user-data/export").status_code == 401
    assert raw.delete("/v1/knowledge/user-data").status_code == 401
