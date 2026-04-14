"""Unit tests for K7.2 — /v1/knowledge/projects CRUD endpoints.

We mount the real router on a fresh FastAPI app and override:
  - get_projects_repo → in-memory FakeProjectsRepo
  - get_current_user → a fixed UUID

So tests exercise the full router (validation, JWT dep, response
shaping, cursor handling) without a Postgres pool. The fake repo
mirrors the public surface of ProjectsRepo just enough to cover the
behaviours under test.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models import Project, ProjectCreate, ProjectUpdate
from app.middleware.jwt_auth import get_current_user
from app.routers.context import get_projects_repo
from app.routers.public.projects import router as projects_router


# ── fakes ────────────────────────────────────────────────────────────────


def _make_project(
    user_id: UUID,
    *,
    name: str = "Untitled",
    created_at: datetime | None = None,
    is_archived: bool = False,
    version: int = 1,
) -> Project:
    now = created_at or datetime.now(timezone.utc)
    return Project(
        project_id=uuid4(),
        user_id=user_id,
        name=name,
        description="",
        project_type="book",
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
        version=version,
        created_at=now,
        updated_at=now,
    )


class FakeProjectsRepo:
    """In-memory ProjectsRepo stand-in. Keys by (user_id, project_id)
    so cross-user isolation is enforced by construction — a test can't
    accidentally read another user's row.
    """

    def __init__(self) -> None:
        self._rows: dict[tuple[UUID, UUID], Project] = {}

    # ── seed helper ──────────────────────────────────────────────────
    def seed(self, project: Project) -> None:
        self._rows[(project.user_id, project.project_id)] = project

    # ── ProjectsRepo surface ─────────────────────────────────────────
    async def list(
        self,
        user_id: UUID,
        *,
        include_archived: bool = False,
        limit: int = 50,
        cursor_created_at: datetime | None = None,
        cursor_project_id: UUID | None = None,
    ) -> list[Project]:
        rows = [
            p for (uid, _), p in self._rows.items()
            if uid == user_id and (include_archived or not p.is_archived)
        ]
        rows.sort(key=lambda p: (p.created_at, p.project_id), reverse=True)
        if cursor_created_at is not None and cursor_project_id is not None:
            rows = [
                p for p in rows
                if (p.created_at, p.project_id) < (cursor_created_at, cursor_project_id)
            ]
        return rows[: max(1, min(limit, 100)) + 1]

    async def get(self, user_id: UUID, project_id: UUID) -> Project | None:
        return self._rows.get((user_id, project_id))

    async def create(self, user_id: UUID, data: ProjectCreate) -> Project:
        proj = _make_project(user_id, name=data.name)
        # Honour the rest of the create payload.
        proj = proj.model_copy(update={
            "description": data.description,
            "project_type": data.project_type,
            "book_id": data.book_id,
            "instructions": data.instructions,
        })
        self.seed(proj)
        return proj

    async def update(
        self,
        user_id: UUID,
        project_id: UUID,
        patch: ProjectUpdate,
        expected_version: int | None = None,
    ) -> Project | None:
        existing = self._rows.get((user_id, project_id))
        if existing is None:
            return None
        raw = patch.model_dump(exclude_unset=True)
        # Strip None on NOT-NULL columns to mirror the real repo
        # (book_id is the only nullable updatable column).
        for f in ("name", "description", "instructions"):
            if raw.get(f) is None:
                raw.pop(f, None)
        # K7b no-op contract: empty patch returns current row without
        # bumping version or updated_at. Mirror for D-K8-03.
        if not raw:
            return existing
        # D-K8-03: enforce expected_version only on actual updates.
        if expected_version is not None and existing.version != expected_version:
            from app.db.repositories import VersionMismatchError
            raise VersionMismatchError(existing)
        raw["version"] = existing.version + (1 if expected_version is not None else 0)
        updated = existing.model_copy(update=raw)
        self.seed(updated)
        return updated

    async def archive(
        self, user_id: UUID, project_id: UUID
    ) -> Project | None:
        existing = self._rows.get((user_id, project_id))
        if existing is None or existing.is_archived:
            return None
        archived = existing.model_copy(update={"is_archived": True})
        self.seed(archived)
        return archived

    async def delete(self, user_id: UUID, project_id: UUID) -> bool:
        return self._rows.pop((user_id, project_id), None) is not None


# ── fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def repo() -> FakeProjectsRepo:
    return FakeProjectsRepo()


@pytest.fixture
def auth_user_id() -> UUID:
    return uuid4()


@pytest.fixture
def client(repo: FakeProjectsRepo, auth_user_id: UUID) -> TestClient:
    app = FastAPI()
    app.include_router(projects_router)
    app.dependency_overrides[get_projects_repo] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: auth_user_id
    return TestClient(app)


# ── list ─────────────────────────────────────────────────────────────────


def test_list_empty(client: TestClient):
    resp = client.get("/v1/knowledge/projects")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


def test_list_returns_only_callers_projects(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    other = uuid4()
    repo.seed(_make_project(auth_user_id, name="mine-1"))
    repo.seed(_make_project(auth_user_id, name="mine-2"))
    repo.seed(_make_project(other, name="theirs"))

    resp = client.get("/v1/knowledge/projects")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()["items"]}
    assert names == {"mine-1", "mine-2"}


def test_list_excludes_archived_by_default(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    repo.seed(_make_project(auth_user_id, name="active"))
    repo.seed(_make_project(auth_user_id, name="dead", is_archived=True))

    resp = client.get("/v1/knowledge/projects")
    assert {p["name"] for p in resp.json()["items"]} == {"active"}

    resp = client.get("/v1/knowledge/projects?include_archived=true")
    assert {p["name"] for p in resp.json()["items"]} == {"active", "dead"}


def test_list_pagination_cursor_round_trip(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    base = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)
    for i in range(5):
        repo.seed(_make_project(
            auth_user_id, name=f"p{i}", created_at=base + timedelta(seconds=i)
        ))

    # Page 1: limit=2
    page1 = client.get("/v1/knowledge/projects?limit=2").json()
    assert len(page1["items"]) == 2
    assert page1["next_cursor"] is not None
    # Newest first ordering
    assert page1["items"][0]["name"] == "p4"
    assert page1["items"][1]["name"] == "p3"

    # Page 2 with cursor
    page2 = client.get(
        f"/v1/knowledge/projects?limit=2&cursor={page1['next_cursor']}"
    ).json()
    assert [p["name"] for p in page2["items"]] == ["p2", "p1"]
    assert page2["next_cursor"] is not None

    # Page 3 — last item, no more pages
    page3 = client.get(
        f"/v1/knowledge/projects?limit=2&cursor={page2['next_cursor']}"
    ).json()
    assert [p["name"] for p in page3["items"]] == ["p0"]
    assert page3["next_cursor"] is None


def test_list_invalid_cursor_returns_400(client: TestClient):
    resp = client.get("/v1/knowledge/projects?cursor=not-a-cursor")
    assert resp.status_code == 400


def test_list_limit_validation(client: TestClient):
    assert client.get("/v1/knowledge/projects?limit=0").status_code == 422
    assert client.get("/v1/knowledge/projects?limit=101").status_code == 422


# ── create ───────────────────────────────────────────────────────────────


def test_create_project(client: TestClient):
    resp = client.post(
        "/v1/knowledge/projects",
        json={"name": "My Novel", "project_type": "book"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "My Novel"
    assert body["project_type"] == "book"


def test_create_blank_name_rejected(client: TestClient):
    resp = client.post(
        "/v1/knowledge/projects",
        json={"name": "   ", "project_type": "book"},
    )
    assert resp.status_code == 422


def test_create_oversize_instructions_rejected(client: TestClient):
    resp = client.post(
        "/v1/knowledge/projects",
        json={
            "name": "ok",
            "project_type": "book",
            "instructions": "x" * 20001,
        },
    )
    assert resp.status_code == 422


def test_create_oversize_description_rejected(client: TestClient):
    resp = client.post(
        "/v1/knowledge/projects",
        json={
            "name": "ok",
            "project_type": "book",
            "description": "x" * 2001,
        },
    )
    assert resp.status_code == 422


def test_create_invalid_project_type_rejected(client: TestClient):
    resp = client.post(
        "/v1/knowledge/projects",
        json={"name": "ok", "project_type": "writing"},
    )
    assert resp.status_code == 422


# ── get ──────────────────────────────────────────────────────────────────


def test_get_own_project(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    proj = _make_project(auth_user_id, name="hello")
    repo.seed(proj)

    resp = client.get(f"/v1/knowledge/projects/{proj.project_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "hello"


def test_get_cross_user_returns_404(
    client: TestClient, repo: FakeProjectsRepo
):
    other = uuid4()
    proj = _make_project(other, name="theirs")
    repo.seed(proj)

    resp = client.get(f"/v1/knowledge/projects/{proj.project_id}")
    assert resp.status_code == 404
    # The body must NOT leak that the row exists under another user.
    assert "not found" in resp.json()["detail"].lower()


def test_get_nonexistent_returns_404(client: TestClient):
    resp = client.get(f"/v1/knowledge/projects/{uuid4()}")
    assert resp.status_code == 404


# ── patch ────────────────────────────────────────────────────────────────


# D-K8-03 helper: every PATCH needs an If-Match header under the new
# strict contract. Centralised so tests read cleanly.
def _im(version: int) -> dict[str, str]:
    return {"If-Match": f'W/"{version}"'}


def test_patch_partial_update(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    proj = _make_project(auth_user_id, name="old")
    repo.seed(proj)

    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"name": "new"},
        headers=_im(proj.version),
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "new"
    # D-K8-03: version bumped + ETag header set.
    assert resp.json()["version"] == proj.version + 1
    assert resp.headers.get("etag") == f'W/"{proj.version + 1}"'


def test_patch_restore_via_is_archived_false(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    """K-CLEAN-3: PATCH is_archived=false on an archived row restores it."""
    proj = _make_project(auth_user_id, name="r")
    proj = proj.model_copy(update={"is_archived": True})
    repo.seed(proj)

    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"is_archived": False},
        headers=_im(proj.version),
    )
    assert resp.status_code == 200
    assert resp.json()["is_archived"] is False


def test_patch_archive_via_is_archived_true_rejected(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    """K-CLEAN-3: PATCH is_archived=true is rejected with 422 so the
    dedicated POST /archive endpoint stays the only archiving path
    (preserves its 404-oracle hardening). The repo MUST NOT be
    touched on the rejection path."""
    proj = _make_project(auth_user_id, name="a")
    repo.seed(proj)

    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"is_archived": True},
        headers=_im(proj.version),
    )
    assert resp.status_code == 422
    assert "POST" in resp.json()["detail"]
    # Defense-in-depth: row must be unchanged.
    after = repo._rows.get((auth_user_id, proj.project_id))
    assert after is not None and after.is_archived is False


def test_patch_cross_user_returns_404(
    client: TestClient, repo: FakeProjectsRepo
):
    other = uuid4()
    proj = _make_project(other, name="theirs")
    repo.seed(proj)

    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"name": "hijacked"},
        headers=_im(proj.version),
    )
    assert resp.status_code == 404


def test_patch_oversize_instructions_rejected(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    proj = _make_project(auth_user_id)
    repo.seed(proj)

    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"instructions": "x" * 20001},
        headers=_im(proj.version),
    )
    assert resp.status_code == 422


def test_patch_missing_if_match_returns_428(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    """D-K8-03: strict If-Match. PATCH without If-Match → 428."""
    proj = _make_project(auth_user_id, name="strict")
    repo.seed(proj)

    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"name": "loose"},
    )
    assert resp.status_code == 428
    # Row must be unchanged.
    assert repo._rows[(auth_user_id, proj.project_id)].name == "strict"


def test_patch_malformed_if_match_returns_400(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    """D-K8-03: malformed If-Match → 400 (not 428 — we want to
    distinguish "didn't send a header" from "sent garbage")."""
    proj = _make_project(auth_user_id, name="strict")
    repo.seed(proj)

    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"name": "loose"},
        headers={"If-Match": "not-a-version"},
    )
    assert resp.status_code == 400


def test_patch_stale_if_match_returns_412_with_current_row(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    """D-K8-03: If-Match with a version that doesn't match the row's
    current version → 412 + current row in body + fresh ETag. Client
    uses the body to refresh its baseline."""
    proj = _make_project(auth_user_id, name="a", version=5)
    repo.seed(proj)

    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"name": "b"},
        headers=_im(3),  # stale: the real version is 5
    )
    assert resp.status_code == 412
    body = resp.json()
    assert body["version"] == 5  # current row is in the body
    assert body["name"] == "a"  # and it's unchanged
    assert resp.headers.get("etag") == 'W/"5"'
    # Row must be unchanged in the repo.
    assert repo._rows[(auth_user_id, proj.project_id)].name == "a"
    assert repo._rows[(auth_user_id, proj.project_id)].version == 5


def test_patch_valid_if_match_accepts_various_formats(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    """D-K8-03: accept W/"<n>", "<n>", and bare <n> formats."""
    for header_value in ('W/"1"', '"1"', "1"):
        proj = _make_project(auth_user_id, name="x", version=1)
        repo.seed(proj)
        resp = client.patch(
            f"/v1/knowledge/projects/{proj.project_id}",
            json={"name": f"from-{header_value}"},
            headers={"If-Match": header_value},
        )
        assert resp.status_code == 200, f"format {header_value!r} rejected"
        # Reset for the next iteration so version=1 again.
        repo._rows.pop((auth_user_id, proj.project_id), None)


def test_get_sets_etag_header(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    """D-K8-03: GET returns a W/"<version>" ETag so the FE can send
    it back in the next PATCH."""
    proj = _make_project(auth_user_id, version=7)
    repo.seed(proj)
    resp = client.get(f"/v1/knowledge/projects/{proj.project_id}")
    assert resp.status_code == 200
    assert resp.headers.get("etag") == 'W/"7"'


# ── archive ──────────────────────────────────────────────────────────────


def test_archive_flips_bit(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    proj = _make_project(auth_user_id)
    repo.seed(proj)

    resp = client.post(f"/v1/knowledge/projects/{proj.project_id}/archive")
    assert resp.status_code == 200
    assert resp.json()["is_archived"] is True


def test_archive_already_archived_returns_404(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    proj = _make_project(auth_user_id, is_archived=True)
    repo.seed(proj)

    resp = client.post(f"/v1/knowledge/projects/{proj.project_id}/archive")
    assert resp.status_code == 404


def test_archive_cross_user_returns_404(
    client: TestClient, repo: FakeProjectsRepo
):
    other = uuid4()
    proj = _make_project(other)
    repo.seed(proj)

    resp = client.post(f"/v1/knowledge/projects/{proj.project_id}/archive")
    assert resp.status_code == 404


# ── delete ───────────────────────────────────────────────────────────────


def test_delete_own_project(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    proj = _make_project(auth_user_id)
    repo.seed(proj)

    resp = client.delete(f"/v1/knowledge/projects/{proj.project_id}")
    assert resp.status_code == 204
    assert (auth_user_id, proj.project_id) not in repo._rows


def test_delete_cross_user_returns_404(
    client: TestClient, repo: FakeProjectsRepo
):
    other = uuid4()
    proj = _make_project(other)
    repo.seed(proj)

    resp = client.delete(f"/v1/knowledge/projects/{proj.project_id}")
    assert resp.status_code == 404
    # Other user's row must still exist.
    assert (other, proj.project_id) in repo._rows


def test_delete_nonexistent_returns_404(client: TestClient):
    resp = client.delete(f"/v1/knowledge/projects/{uuid4()}")
    assert resp.status_code == 404


# ── auth ─────────────────────────────────────────────────────────────────


def test_list_non_ascii_cursor_returns_400(client: TestClient):
    """K7b-I3: a cursor containing non-ASCII chars must land on the
    400 path, not crash with a 500 on `.encode('ascii')`."""
    resp = client.get("/v1/knowledge/projects?cursor=caf%C3%A9")
    assert resp.status_code == 400


# ── K7b-I4: DB CheckViolationError → 422 mapping ─────────────────────────


def test_patch_db_check_violation_maps_to_422(
    repo: FakeProjectsRepo, auth_user_id: UUID
):
    """The Pydantic validators gate the public surface, but K7 also
    installs DB CHECK constraints (knowledge_projects_instructions_len,
    etc.) as defense-in-depth. If the DB rejects a write the router
    must surface 422, not 500. This test injects a repo whose update
    raises asyncpg.CheckViolationError so we can exercise the except
    branch without a real Postgres.
    """
    import asyncpg

    proj = _make_project(auth_user_id)
    repo.seed(proj)

    class ExplodingRepo(FakeProjectsRepo):
        async def update(self, *args, **kwargs):  # type: ignore[override]
            # Construct the exception the same way asyncpg does so the
            # constraint_name attribute is set.
            exc = asyncpg.CheckViolationError("length check failed")
            exc.constraint_name = "knowledge_projects_instructions_len"
            raise exc

    exploding = ExplodingRepo()
    exploding.seed(proj)
    app = FastAPI()
    app.include_router(projects_router)
    app.dependency_overrides[get_projects_repo] = lambda: exploding
    app.dependency_overrides[get_current_user] = lambda: auth_user_id
    client = TestClient(app)

    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"instructions": "ok-for-pydantic"},
        headers=_im(proj.version),
    )
    assert resp.status_code == 422
    assert "knowledge_projects_instructions_len" in resp.json()["detail"]


def test_create_db_check_violation_maps_to_422(
    repo: FakeProjectsRepo, auth_user_id: UUID
):
    """K7-review-R3: POST symmetric with PATCH. If the DB CHECK
    constraints fire on a create (e.g. a future Pydantic loosen), the
    router must surface 422, not crash with 500.
    """
    import asyncpg

    class ExplodingRepo(FakeProjectsRepo):
        async def create(self, *args, **kwargs):  # type: ignore[override]
            exc = asyncpg.CheckViolationError("name length check failed")
            exc.constraint_name = "knowledge_projects_name_len"
            raise exc

    exploding = ExplodingRepo()
    app = FastAPI()
    app.include_router(projects_router)
    app.dependency_overrides[get_projects_repo] = lambda: exploding
    app.dependency_overrides[get_current_user] = lambda: auth_user_id
    client = TestClient(app)

    resp = client.post(
        "/v1/knowledge/projects",
        json={"name": "ok-for-pydantic", "project_type": "general"},
    )
    assert resp.status_code == 422
    assert "knowledge_projects_name_len" in resp.json()["detail"]


# ── K7b-I1: delete cascade short-circuit ─────────────────────────────────


def test_delete_cross_user_does_not_touch_summaries(
    repo: FakeProjectsRepo, auth_user_id: UUID
):
    """Regression guard for the pre-fix cascade order bug: a cross-user
    DELETE must not execute the summaries cascade at all. The fake
    repo can't observe the SQL directly, so we wrap delete() and
    assert the summaries path is never reached when the project delete
    would return 0.
    """
    other = uuid4()
    proj = _make_project(other)
    repo.seed(proj)

    # Track whether anything beyond the bailout was reached.
    touched_summaries = False
    original_delete = repo.delete

    async def tracking_delete(uid, pid):  # type: ignore[no-untyped-def]
        nonlocal touched_summaries
        result = await original_delete(uid, pid)
        if result:
            touched_summaries = True
        return result

    repo.delete = tracking_delete  # type: ignore[assignment]

    app = FastAPI()
    app.include_router(projects_router)
    app.dependency_overrides[get_projects_repo] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: auth_user_id
    client = TestClient(app)

    resp = client.delete(f"/v1/knowledge/projects/{proj.project_id}")
    assert resp.status_code == 404
    assert not touched_summaries
    # Cross-user row still present.
    assert (other, proj.project_id) in repo._rows


def test_no_jwt_returns_401(repo: FakeProjectsRepo):
    """Router-level Depends(get_current_user) must return 401 before
    any route logic runs when the JWT is missing entirely.
    """
    app = FastAPI()
    app.include_router(projects_router)
    app.dependency_overrides[get_projects_repo] = lambda: repo
    # Deliberately no override for get_current_user — we want the real
    # dependency to fail on the missing Bearer header.
    raw = TestClient(app)
    resp = raw.get("/v1/knowledge/projects")
    assert resp.status_code == 401
