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
    extraction_status: str = "disabled",
    embedding_model: str | None = None,
    book_id: UUID | None = None,
) -> Project:
    now = created_at or datetime.now(timezone.utc)
    return Project(
        project_id=uuid4(),
        user_id=user_id,
        name=name,
        description="",
        project_type="book",
        book_id=book_id,
        instructions="",
        extraction_enabled=False,
        extraction_status=extraction_status,
        embedding_model=embedding_model,
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
        book_id: UUID | None = None,
    ) -> list[Project]:
        rows = [
            p for (uid, _), p in self._rows.items()
            if uid == user_id and (include_archived or not p.is_archived)
            and (book_id is None or p.book_id == book_id)
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

    async def create_or_get(
        self, user_id: UUID, data: ProjectCreate
    ) -> tuple[Project, bool]:
        """Mirror the real repo's idempotent book-binding create
        (D-COMP-POST-WORK-RACE). Delegates to ``create`` so an ``ExplodingRepo``
        that overrides ``create`` still surfaces its error here. For a
        ``project_type='book'`` WITH a ``book_id``, return an existing
        non-archived book project for (user, book) if one is already seeded
        (created=False); otherwise insert (created=True)."""
        if data.project_type == "book" and data.book_id is not None:
            for proj in self._rows.values():
                if (
                    proj.user_id == user_id
                    and proj.project_type == "book"
                    and proj.book_id == data.book_id
                    and getattr(proj, "archived_at", None) is None
                ):
                    return proj, False
        return await self.create(user_id, data), True

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
        # (book_id is the only nullable updatable column;
        # tool_calling_enabled + memory_remember_confirm are NOT NULL —
        # design D9 / K21-C D4).
        for f in ("name", "description", "instructions",
                  "tool_calling_enabled", "memory_remember_confirm"):
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

    async def update_extraction_config(
        self, user_id: UUID, project_id: UUID, config: dict, expected_version: int,
    ) -> Project | None:
        existing = self._rows.get((user_id, project_id))
        if existing is None:
            return None
        if existing.version != expected_version:
            from app.db.repositories import VersionMismatchError
            raise VersionMismatchError(existing)
        updated = existing.model_copy(update={
            "extraction_config": config, "version": existing.version + 1,
        })
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


def test_list_filters_by_book_id(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    """C5 (ARCH-1): the editor AI panel resolves a book's project via
    ?book_id=. Returns only the matching project; empty when none."""
    book = uuid4()
    repo.seed(_make_project(auth_user_id, name="linked", book_id=book))
    repo.seed(_make_project(auth_user_id, name="other", book_id=uuid4()))
    repo.seed(_make_project(auth_user_id, name="unlinked"))

    resp = client.get(f"/v1/knowledge/projects?book_id={book}")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [p["name"] for p in items] == ["linked"]

    # a book with no project → empty
    resp = client.get(f"/v1/knowledge/projects?book_id={uuid4()}")
    assert resp.json()["items"] == []


def test_list_book_id_invalid_uuid_returns_422(client: TestClient):
    resp = client.get("/v1/knowledge/projects?book_id=not-a-uuid")
    assert resp.status_code == 422


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


# ── K21.12-BE (design D9): tool_calling_enabled ──────────────────────────


def test_project_defaults_tool_calling_enabled_true():
    """A Project built without tool_calling_enabled reads back true —
    this is the model-default half of the 'a row that predates the
    column reads back enabled' contract (the DB DEFAULT true is the
    other half)."""
    proj = _make_project(uuid4())
    assert proj.tool_calling_enabled is True


def test_get_project_surfaces_tool_calling_enabled(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    """The field is on the Project response model, so GET carries it."""
    proj = _make_project(auth_user_id).model_copy(
        update={"tool_calling_enabled": False}
    )
    repo.seed(proj)
    resp = client.get(f"/v1/knowledge/projects/{proj.project_id}")
    assert resp.status_code == 200
    assert resp.json()["tool_calling_enabled"] is False


def test_patch_toggles_tool_calling_enabled(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    """D9 — ProjectUpdate accepts the field and PATCH round-trips it
    through the repo (the Cycle C settings UI drives this same path)."""
    proj = _make_project(auth_user_id)  # defaults tool_calling_enabled=True
    repo.seed(proj)

    # Turn it off.
    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"tool_calling_enabled": False},
        headers=_im(proj.version),
    )
    assert resp.status_code == 200
    assert resp.json()["tool_calling_enabled"] is False
    assert repo._rows[(auth_user_id, proj.project_id)].tool_calling_enabled is False

    # Turn it back on.
    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"tool_calling_enabled": True},
        headers=_im(proj.version + 1),
    )
    assert resp.status_code == 200
    assert resp.json()["tool_calling_enabled"] is True


def test_patch_omitting_tool_calling_enabled_leaves_it_unchanged(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    """ProjectUpdate uses exclude_unset — a PATCH that doesn't mention
    tool_calling_enabled must not reset it."""
    proj = _make_project(auth_user_id).model_copy(
        update={"tool_calling_enabled": False}
    )
    repo.seed(proj)

    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"name": "renamed"},
        headers=_im(proj.version),
    )
    assert resp.status_code == 200
    assert resp.json()["tool_calling_enabled"] is False


def test_project_update_model_accepts_tool_calling_enabled():
    """D9 — the field is settable on ProjectUpdate, omittable (so an
    untouched PATCH leaves it alone), and absent from a default
    instance (exclude_unset must drop it)."""
    assert ProjectUpdate(tool_calling_enabled=False).tool_calling_enabled is False
    assert ProjectUpdate(tool_calling_enabled=True).tool_calling_enabled is True
    # Omitted → not in the exclude_unset dump → repo treats as no-op.
    assert "tool_calling_enabled" not in ProjectUpdate().model_dump(
        exclude_unset=True
    )
    assert ProjectUpdate().tool_calling_enabled is None


async def test_repo_update_skips_none_tool_calling_enabled(
    repo: FakeProjectsRepo, auth_user_id: UUID
):
    """tool_calling_enabled is NOT NULL — explicitly passing None must
    be skipped (treated as a no-op for that field), mirroring the real
    repo's exclusion from _NULLABLE_UPDATE_COLUMNS. An explicit-None
    patch must not flip the stored true to NULL."""
    proj = _make_project(auth_user_id)  # tool_calling_enabled=True
    repo.seed(proj)
    result = await repo.update(
        auth_user_id, proj.project_id,
        ProjectUpdate(tool_calling_enabled=None),
    )
    assert result is not None
    assert result.tool_calling_enabled is True


# ── K21-C (design D4): memory_remember_confirm ───────────────────────────


def test_project_defaults_memory_remember_confirm_false():
    """A Project built without memory_remember_confirm reads back false
    — the model-default half of the 'a row that predates the column
    reads back OFF' contract (the DB DEFAULT false is the other half).
    The setting is opt-in: default off preserves today's write-directly
    behaviour."""
    proj = _make_project(uuid4())
    assert proj.memory_remember_confirm is False


def test_get_project_surfaces_memory_remember_confirm(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    """The field is on the Project response model, so GET carries it."""
    proj = _make_project(auth_user_id).model_copy(
        update={"memory_remember_confirm": True}
    )
    repo.seed(proj)
    resp = client.get(f"/v1/knowledge/projects/{proj.project_id}")
    assert resp.status_code == 200
    assert resp.json()["memory_remember_confirm"] is True


def test_patch_toggles_memory_remember_confirm(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    """K21-C D4 — ProjectUpdate accepts the field and PATCH round-trips
    it through the repo (the Cycle C settings UI drives this path)."""
    proj = _make_project(auth_user_id)  # defaults memory_remember_confirm=False
    repo.seed(proj)

    # Turn it on.
    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"memory_remember_confirm": True},
        headers=_im(proj.version),
    )
    assert resp.status_code == 200
    assert resp.json()["memory_remember_confirm"] is True
    assert (
        repo._rows[(auth_user_id, proj.project_id)].memory_remember_confirm
        is True
    )

    # Turn it back off.
    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"memory_remember_confirm": False},
        headers=_im(proj.version + 1),
    )
    assert resp.status_code == 200
    assert resp.json()["memory_remember_confirm"] is False


def test_patch_omitting_memory_remember_confirm_leaves_it_unchanged(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    """ProjectUpdate uses exclude_unset — a PATCH that doesn't mention
    memory_remember_confirm must not reset it."""
    proj = _make_project(auth_user_id).model_copy(
        update={"memory_remember_confirm": True}
    )
    repo.seed(proj)

    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"name": "renamed"},
        headers=_im(proj.version),
    )
    assert resp.status_code == 200
    assert resp.json()["memory_remember_confirm"] is True


def test_project_update_model_accepts_memory_remember_confirm():
    """K21-C D4 — the field is settable on ProjectUpdate, omittable (so
    an untouched PATCH leaves it alone), and absent from a default
    instance (exclude_unset must drop it)."""
    assert (
        ProjectUpdate(memory_remember_confirm=True).memory_remember_confirm
        is True
    )
    assert (
        ProjectUpdate(memory_remember_confirm=False).memory_remember_confirm
        is False
    )
    # Omitted → not in the exclude_unset dump → repo treats as no-op.
    assert "memory_remember_confirm" not in ProjectUpdate().model_dump(
        exclude_unset=True
    )
    assert ProjectUpdate().memory_remember_confirm is None


async def test_repo_update_skips_none_memory_remember_confirm(
    repo: FakeProjectsRepo, auth_user_id: UUID
):
    """memory_remember_confirm is NOT NULL — explicitly passing None
    must be skipped, mirroring the real repo's exclusion from
    _NULLABLE_UPDATE_COLUMNS. An explicit-None patch must not flip the
    stored value to NULL."""
    proj = _make_project(auth_user_id).model_copy(
        update={"memory_remember_confirm": True}
    )
    repo.seed(proj)
    result = await repo.update(
        auth_user_id, proj.project_id,
        ProjectUpdate(memory_remember_confirm=None),
    )
    assert result is not None
    assert result.memory_remember_confirm is True


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


# ── D-EMB-MODEL-REF-04: PATCH embedding_model dual-path guard ────────────


def test_patch_embedding_model_rejected_on_project_with_graph(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID
):
    """D-EMB-MODEL-REF-04: PATCH /{id} cannot change embedding_model
    when the project already has a graph (extraction_status != 'disabled').
    Without this guard, the old vectors stay in Neo4j tagged with the
    old model UUID while Mode-3 retrieval queries the new model space —
    silent zero-recall."""
    old_uuid = "11111111-1111-1111-1111-111111111111"
    new_uuid = "22222222-2222-2222-2222-222222222222"
    proj = _make_project(
        auth_user_id,
        extraction_status="ready",
        embedding_model=old_uuid,
    )
    repo.seed(proj)

    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"embedding_model": new_uuid},
        headers=_im(proj.version),
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "embedding-model?confirm=true" in detail
    # Defense-in-depth: row must be unchanged + status sticks.
    after = repo._rows.get((auth_user_id, proj.project_id))
    assert after is not None
    assert after.embedding_model == old_uuid
    assert after.extraction_status == "ready"


def test_patch_embedding_model_allowed_first_time_setup_status_disabled(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID,
    monkeypatch,
):
    """First-time embedding-model setup goes through generic PATCH
    when the project has no graph yet (status='disabled'). This is the
    K12.4 picker flow on a fresh project."""
    from unittest.mock import AsyncMock

    new_uuid = "33333333-3333-3333-3333-333333333333"
    monkeypatch.setattr(
        "app.routers.public.projects.probe_embedding_dimension",
        AsyncMock(return_value=1024),
    )

    proj = _make_project(
        auth_user_id,
        extraction_status="disabled",
        embedding_model=None,
    )
    repo.seed(proj)

    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"embedding_model": new_uuid},
        headers=_im(proj.version),
    )
    assert resp.status_code == 200
    assert resp.json()["embedding_model"] == new_uuid


def test_patch_embedding_model_same_value_is_noop_even_when_status_ready(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID,
    monkeypatch,
):
    """A FE that re-sends the current embedding_model in a PATCH body
    (e.g. unchanged form submit) must NOT be rejected — the value is
    not actually changing, so no graph orphaning risk. The probe still
    runs since model_fields_set is set."""
    from unittest.mock import AsyncMock

    uuid_value = "44444444-4444-4444-4444-444444444444"
    monkeypatch.setattr(
        "app.routers.public.projects.probe_embedding_dimension",
        AsyncMock(return_value=1024),
    )

    proj = _make_project(
        auth_user_id,
        extraction_status="ready",
        embedding_model=uuid_value,
    )
    repo.seed(proj)

    resp = client.patch(
        f"/v1/knowledge/projects/{proj.project_id}",
        json={"embedding_model": uuid_value},
        headers=_im(proj.version),
    )
    assert resp.status_code == 200
    assert resp.json()["embedding_model"] == uuid_value


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


# ── B2-B-b1: PUT /{id}/extraction-config ──────────────────────────────────


@pytest.fixture
def captured_emits(monkeypatch):
    """Capture config_adjusted emits from the endpoint (the real emit is
    best-effort + needs a knowledge pool, absent in unit tests)."""
    calls: list[dict] = []

    async def _fake_emit(*, aggregate_id, payload):
        calls.append({"aggregate_id": aggregate_id, "payload": payload})

    monkeypatch.setattr(
        "app.routers.public.projects.emit_config_adjustment", _fake_emit
    )
    return calls


def test_put_extraction_config_requires_if_match(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID, captured_emits
):
    p = _make_project(auth_user_id)
    repo.seed(p)
    resp = client.put(
        f"/v1/knowledge/projects/{p.project_id}/extraction-config",
        json={"precision_filter": {"categories": ["relation"]}},
    )
    assert resp.status_code == 428
    assert captured_emits == []


def test_put_extraction_config_rejects_unknown_key(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID, captured_emits
):
    p = _make_project(auth_user_id)
    repo.seed(p)
    resp = client.put(
        f"/v1/knowledge/projects/{p.project_id}/extraction-config",
        headers={"If-Match": '"1"'},
        json={"bogus_key": {"x": 1}},
    )
    assert resp.status_code == 422


def test_put_extraction_config_rejects_invalid_category(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID, captured_emits
):
    p = _make_project(auth_user_id)
    repo.seed(p)
    resp = client.put(
        f"/v1/knowledge/projects/{p.project_id}/extraction-config",
        headers={"If-Match": '"1"'},
        json={"precision_filter": {"categories": ["nonsense"]}},
    )
    assert resp.status_code == 422


def test_put_extraction_config_version_mismatch(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID, captured_emits
):
    p = _make_project(auth_user_id, version=3)
    repo.seed(p)
    resp = client.put(
        f"/v1/knowledge/projects/{p.project_id}/extraction-config",
        headers={"If-Match": '"1"'},  # stale
        json={"precision_filter": {"categories": ["relation"]}},
    )
    assert resp.status_code == 412
    assert captured_emits == []


def test_put_extraction_config_persists_and_emits_changed_targets(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID, captured_emits
):
    p = _make_project(auth_user_id, version=1)
    repo.seed(p)
    resp = client.put(
        f"/v1/knowledge/projects/{p.project_id}/extraction-config",
        headers={"If-Match": '"1"'},
        json={
            "precision_filter": {"categories": ["relation"], "partial_policy": "drop"},
            "entity_recovery": {"enabled": True},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["extraction_config"]["precision_filter"]["categories"] == ["relation"]
    assert body["version"] == 2
    assert resp.headers["ETag"] == 'W/"2"'
    # one emit per changed top-level target (filter + recovery), not the others
    targets = sorted(c["payload"]["target"] for c in captured_emits)
    assert targets == ["entity_recovery", "precision_filter"]
    pf = next(c for c in captured_emits if c["payload"]["target"] == "precision_filter")
    assert pf["payload"]["before_structural"] is None
    assert pf["payload"]["after_structural"]["categories"] == ["relation"]
    assert pf["payload"]["op"] == "set"


def test_put_extraction_config_no_change_no_emit(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID, captured_emits
):
    p = _make_project(auth_user_id, version=1)
    p = p.model_copy(update={"extraction_config": {"entity_recovery": {"enabled": True}}})
    repo.seed(p)
    # re-PUT the identical config → no target changed → no emit
    resp = client.put(
        f"/v1/knowledge/projects/{p.project_id}/extraction-config",
        headers={"If-Match": '"1"'},
        json={"entity_recovery": {"enabled": True}},
    )
    assert resp.status_code == 200
    assert captured_emits == []


def test_put_extraction_config_empty_subobject_dropped(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID, captured_emits
):
    """An all-None sub-object (e.g. {}) is dropped from the stored config so a
    stray empty override doesn't get persisted."""
    p = _make_project(auth_user_id, version=1)
    repo.seed(p)
    resp = client.put(
        f"/v1/knowledge/projects/{p.project_id}/extraction-config",
        headers={"If-Match": '"1"'},
        json={"precision_filter": {}, "entity_recovery": {"enabled": True}},
    )
    assert resp.status_code == 200
    cfg = resp.json()["extraction_config"]
    assert "precision_filter" not in cfg
    assert cfg["entity_recovery"] == {"enabled": True}


def test_put_extraction_config_not_found(
    client: TestClient, auth_user_id: UUID, captured_emits
):
    resp = client.put(
        f"/v1/knowledge/projects/{uuid4()}/extraction-config",
        headers={"If-Match": '"1"'},
        json={"precision_filter": {"categories": ["relation"]}},
    )
    assert resp.status_code == 404


# ── B2-B-b2: raw-prompt override (security) ────────────────────────────────


def test_put_extraction_config_persists_prompts(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID, captured_emits
):
    p = _make_project(auth_user_id, version=1)
    repo.seed(p)
    resp = client.put(
        f"/v1/knowledge/projects/{p.project_id}/extraction-config",
        headers={"If-Match": '"1"'},
        json={"prompts": {"entity": {"system": "Extract only people and places."}}},
    )
    assert resp.status_code == 200
    cfg = resp.json()["extraction_config"]
    assert cfg["prompts"]["entity"]["system"] == "Extract only people and places."


def test_put_extraction_config_prompt_emits_content_hash_not_raw_text(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID, captured_emits
):
    """Privacy regression-lock (DESIGN Q5): the config_adjusted event for a
    prompt target carries a content-HASH, never the raw prompt text."""
    import hashlib

    secret = "MY PROPRIETARY GENRE-SPECIFIC EXTRACTION PROMPT"
    p = _make_project(auth_user_id, version=1)
    repo.seed(p)
    resp = client.put(
        f"/v1/knowledge/projects/{p.project_id}/extraction-config",
        headers={"If-Match": '"1"'},
        json={"prompts": {"entity": {"system": secret}}},
    )
    assert resp.status_code == 200
    emit = next(c for c in captured_emits if c["payload"]["target"] == "prompts.entity")
    pl = emit["payload"]
    assert pl["after_content_hash"] == hashlib.sha256(secret.encode()).hexdigest()
    assert pl["before_content_hash"] is None
    # the raw text must NOT appear anywhere in the emitted payload
    import json as _json
    assert secret not in _json.dumps(pl)
    assert pl["after_structural"] is None


def test_put_extraction_config_rejects_overlong_prompt(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID, captured_emits
):
    p = _make_project(auth_user_id, version=1)
    repo.seed(p)
    resp = client.put(
        f"/v1/knowledge/projects/{p.project_id}/extraction-config",
        headers={"If-Match": '"1"'},
        json={"prompts": {"entity": {"system": "x" * 16385}}},  # > 16384 cap
    )
    assert resp.status_code == 422
    assert captured_emits == []


def test_put_extraction_config_rejects_unknown_prompt_op(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID, captured_emits
):
    p = _make_project(auth_user_id, version=1)
    repo.seed(p)
    resp = client.put(
        f"/v1/knowledge/projects/{p.project_id}/extraction-config",
        headers={"If-Match": '"1"'},
        json={"prompts": {"bogus_op": {"system": "x"}}},
    )
    assert resp.status_code == 422


def test_put_extraction_config_rejects_unknown_prompt_field(
    client: TestClient, repo: FakeProjectsRepo, auth_user_id: UUID, captured_emits
):
    p = _make_project(auth_user_id, version=1)
    repo.seed(p)
    resp = client.put(
        f"/v1/knowledge/projects/{p.project_id}/extraction-config",
        headers={"If-Match": '"1"'},
        json={"prompts": {"entity": {"user": "not allowed"}}},  # only `system`
    )
    assert resp.status_code == 422
