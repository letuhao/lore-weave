"""Unit tests for K7.3 — /v1/knowledge/summaries endpoints.

Same pattern as test_public_projects: mount the real router on a
fresh FastAPI app, override get_*_repo + get_current_user with
in-memory fakes. No Postgres required.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.db.models import ScopeType, Summary
from app.deps import get_summaries_repo
from app.middleware.jwt_auth import get_current_user
from app.routers.public.summaries import router as summaries_router


# ── fakes ────────────────────────────────────────────────────────────────


def _make_summary(
    user_id: UUID,
    scope_type: ScopeType,
    scope_id: UUID | None,
    content: str = "hello",
) -> Summary:
    now = datetime.now(timezone.utc)
    return Summary(
        summary_id=uuid4(),
        user_id=user_id,
        scope_type=scope_type,
        scope_id=scope_id,
        content=content,
        token_count=max(1, len(content) // 4),
        version=1,
        created_at=now,
        updated_at=now,
    )


class FakeSummariesRepo:
    """In-memory SummariesRepo stand-in.

    Holds an `_owned_projects` set the project-scoped tests use to
    declare which (user_id, project_id) pairs are valid — mirrors the
    real CTE's ownership check without needing a real Postgres.
    """

    # Mirror the real repo's public constant so the router can read
    # it without the fake overriding it to something unexpected.
    VERSIONS_LIST_HARD_CAP = 200

    def __init__(self) -> None:
        # Key: (user_id, scope_type, scope_id) — mirrors the unique index.
        self._rows: dict[tuple[UUID, ScopeType, UUID | None], Summary] = {}
        self._owned_projects: set[tuple[UUID, UUID]] = set()
        self.invalidations: list[tuple[UUID, ScopeType, UUID | None]] = []
        # D-K8-01: history rows keyed by (user_id, scope_type, scope_id)
        # and sorted newest-first.
        self._history: dict[
            tuple[UUID, ScopeType, UUID | None], list
        ] = {}

    def seed(self, s: Summary) -> None:
        self._rows[(s.user_id, s.scope_type, s.scope_id)] = s

    def own_project(self, user_id: UUID, project_id: UUID) -> None:
        self._owned_projects.add((user_id, project_id))

    async def list_for_user(self, user_id: UUID) -> list[Summary]:
        rows = [s for k, s in self._rows.items() if k[0] == user_id]
        # Mirror the real repo's CASE-based scope ordering so router
        # iteration is exercised in the realistic order.
        scope_order = {"global": 0, "project": 1, "session": 2, "entity": 3}
        rows.sort(key=lambda s: (scope_order.get(s.scope_type, 4), -s.updated_at.timestamp()))
        return rows

    async def get(
        self, user_id: UUID, scope_type: ScopeType, scope_id: UUID | None
    ) -> Summary | None:
        return self._rows.get((user_id, scope_type, scope_id))

    async def upsert(
        self,
        user_id: UUID,
        scope_type: ScopeType,
        scope_id: UUID | None,
        content: str,
        expected_version: int | None = None,
    ) -> Summary:
        existing = self._rows.get((user_id, scope_type, scope_id))
        if existing is None:
            # INSERT path — expected_version is ignored; the row didn't
            # exist so there was nothing for the client to race against.
            row = _make_summary(user_id, scope_type, scope_id, content=content)
        else:
            # UPDATE path — D-K8-03: if expected_version is set and
            # doesn't match, raise just like the real repo does.
            if expected_version is not None and existing.version != expected_version:
                from app.db.repositories import VersionMismatchError
                raise VersionMismatchError(existing)
            # D-K8-01: capture the pre-update state to history.
            self._push_history(
                user_id, scope_type, scope_id, existing, edit_source="manual"
            )
            row = existing.model_copy(update={
                "content": content,
                "token_count": max(1, len(content) // 4),
                "version": existing.version + 1,
                "updated_at": datetime.now(timezone.utc),
            })
        self._rows[(user_id, scope_type, scope_id)] = row
        self.invalidations.append((user_id, scope_type, scope_id))
        return row

    def _push_history(
        self,
        user_id: UUID,
        scope_type: ScopeType,
        scope_id: UUID | None,
        pre: Summary,
        *,
        edit_source: str,
    ) -> None:
        from app.db.models import SummaryVersion
        from uuid import uuid4
        row = SummaryVersion(
            version_id=uuid4(),
            summary_id=pre.summary_id,
            user_id=user_id,
            version=pre.version,
            content=pre.content,
            token_count=pre.token_count,
            created_at=datetime.now(timezone.utc),
            edit_source=edit_source,
        )
        key = (user_id, scope_type, scope_id)
        self._history.setdefault(key, []).append(row)

    async def upsert_project_scoped(
        self,
        user_id: UUID,
        project_id: UUID,
        content: str,
        expected_version: int | None = None,
    ) -> Summary | None:
        # Mirror the CTE: zero rows if the user doesn't own the project.
        if (user_id, project_id) not in self._owned_projects:
            return None
        return await self.upsert(
            user_id, "project", project_id, content, expected_version=expected_version
        )

    # ── D-K8-01: version history ──────────────────────────────────────

    async def list_versions(
        self,
        user_id: UUID,
        scope_type: ScopeType,
        scope_id: UUID | None,
        *,
        limit: int = 50,
    ) -> list:
        rows = list(self._history.get((user_id, scope_type, scope_id), []))
        # Newest first.
        rows.sort(key=lambda r: r.version, reverse=True)
        effective = max(1, min(limit, self.VERSIONS_LIST_HARD_CAP))
        return rows[:effective]

    async def get_version(
        self,
        user_id: UUID,
        scope_type: ScopeType,
        scope_id: UUID | None,
        version: int,
    ):
        for r in self._history.get((user_id, scope_type, scope_id), []):
            if r.version == version:
                return r
        return None

    async def rollback_to(
        self,
        user_id: UUID,
        scope_type: ScopeType,
        scope_id: UUID | None,
        target_version: int,
        expected_version: int,
    ) -> Summary:
        current = self._rows.get((user_id, scope_type, scope_id))
        if current is None:
            raise LookupError("summary_not_found")
        if current.version != expected_version:
            from app.db.repositories import VersionMismatchError
            raise VersionMismatchError(current)
        target = await self.get_version(user_id, scope_type, scope_id, target_version)
        if target is None:
            raise LookupError("target_version_not_found")
        # Archive current as rollback history.
        self._push_history(
            user_id, scope_type, scope_id, current, edit_source="rollback"
        )
        rolled = current.model_copy(update={
            "content": target.content,
            "token_count": target.token_count,
            "version": current.version + 1,
            "updated_at": datetime.now(timezone.utc),
        })
        self._rows[(user_id, scope_type, scope_id)] = rolled
        self.invalidations.append((user_id, scope_type, scope_id))
        return rolled


class _ExplodingSummariesRepo(FakeSummariesRepo):
    """upsert / upsert_project_scoped raise CheckViolationError — for the 422 path."""

    def __init__(self) -> None:
        super().__init__()

    def _explode(self) -> "asyncpg.CheckViolationError":
        exc = asyncpg.CheckViolationError("oversize")
        exc.constraint_name = "knowledge_summaries_content_len"  # type: ignore[attr-defined]
        return exc

    async def upsert(self, *args, **kwargs):  # type: ignore[override]
        raise self._explode()

    async def upsert_project_scoped(self, *args, **kwargs):  # type: ignore[override]
        raise self._explode()


# ── fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def summaries_repo() -> FakeSummariesRepo:
    return FakeSummariesRepo()


@pytest.fixture
def auth_user_id() -> UUID:
    return uuid4()


@pytest.fixture
def client(
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
) -> TestClient:
    app = FastAPI()
    app.include_router(summaries_router)
    app.dependency_overrides[get_summaries_repo] = lambda: summaries_repo
    app.dependency_overrides[get_current_user] = lambda: auth_user_id
    return TestClient(app)


# ── GET /v1/knowledge/summaries ──────────────────────────────────────────


def test_list_empty(client: TestClient):
    resp = client.get("/v1/knowledge/summaries")
    assert resp.status_code == 200
    body = resp.json()
    assert body["global"] is None
    assert body["projects"] == []


def test_list_returns_global_only(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "bio"))
    body = client.get("/v1/knowledge/summaries").json()
    assert body["global"]["content"] == "bio"
    assert body["projects"] == []


def test_list_returns_projects_only(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    p1, p2 = uuid4(), uuid4()
    summaries_repo.seed(_make_summary(auth_user_id, "project", p1, "one"))
    summaries_repo.seed(_make_summary(auth_user_id, "project", p2, "two"))
    body = client.get("/v1/knowledge/summaries").json()
    assert body["global"] is None
    assert {p["content"] for p in body["projects"]} == {"one", "two"}


def test_list_returns_global_and_projects(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "bio"))
    summaries_repo.seed(_make_summary(auth_user_id, "project", uuid4(), "p"))
    body = client.get("/v1/knowledge/summaries").json()
    assert body["global"]["content"] == "bio"
    assert len(body["projects"]) == 1


def test_list_isolates_other_users(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    other = uuid4()
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "mine"))
    summaries_repo.seed(_make_summary(other, "global", None, "theirs"))
    summaries_repo.seed(_make_summary(other, "project", uuid4(), "theirs-p"))
    body = client.get("/v1/knowledge/summaries").json()
    assert body["global"]["content"] == "mine"
    assert body["projects"] == []


def test_list_global_appears_first_regardless_of_seed_order(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    """K7c-R2: defends the CASE-based ORDER BY in
    SummariesRepo.list_for_user. The router relies on globals
    appearing before projects so its 'first global wins' loop is
    correct even if the global row was inserted after project rows.
    The fake repo mirrors the real CASE ordering — this test would
    fail if either the SQL ordering or the fake's mirror drifts.
    """
    # Seed projects FIRST, global LAST — opposite of insertion order.
    summaries_repo.seed(_make_summary(auth_user_id, "project", uuid4(), "p1"))
    summaries_repo.seed(_make_summary(auth_user_id, "project", uuid4(), "p2"))
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "bio"))
    body = client.get("/v1/knowledge/summaries").json()
    assert body["global"]["content"] == "bio"
    assert len(body["projects"]) == 2


def test_list_skips_session_and_entity_scopes(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    """Track 1 only writes global/project, but if a Track 2 row sneaks
    in we silently skip it instead of crashing."""
    summaries_repo.seed(_make_summary(auth_user_id, "session", uuid4(), "s"))
    summaries_repo.seed(_make_summary(auth_user_id, "entity", uuid4(), "e"))
    body = client.get("/v1/knowledge/summaries").json()
    assert body["global"] is None
    assert body["projects"] == []


# ── PATCH /v1/knowledge/summaries/global ─────────────────────────────────


# D-K8-03 helper: every subsequent PATCH needs an If-Match header under
# the new strict contract. First save (no prior row) is the one exception.
def _im(version: int) -> dict[str, str]:
    return {"If-Match": f'W/"{version}"'}


def test_patch_global_creates(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    # D-K8-03: first save is allowed without If-Match because the client
    # couldn't have obtained an ETag for a row that didn't exist.
    resp = client.patch(
        "/v1/knowledge/summaries/global", json={"content": "hello"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "hello"
    assert body["version"] == 1  # K7c-R6: assert clean create version
    assert resp.headers.get("etag") == 'W/"1"'
    assert (auth_user_id, "global", None) in summaries_repo._rows
    assert summaries_repo.invalidations[-1] == (auth_user_id, "global", None)


def test_patch_global_updates_existing(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "v1"))
    resp = client.patch(
        "/v1/knowledge/summaries/global",
        json={"content": "v2"},
        headers=_im(1),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "v2"
    assert body["version"] == 2
    assert resp.headers.get("etag") == 'W/"2"'


def test_patch_global_empty_content_allowed(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    """K7.3 spec: empty content keeps the row, does NOT delete."""
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "old"))
    resp = client.patch(
        "/v1/knowledge/summaries/global",
        json={"content": ""},
        headers=_im(1),
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == ""
    # Row still present.
    assert (auth_user_id, "global", None) in summaries_repo._rows


def test_patch_global_update_without_if_match_returns_428(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    """D-K8-03: update path (row exists) requires If-Match."""
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "v1"))
    resp = client.patch(
        "/v1/knowledge/summaries/global", json={"content": "v2"}
    )
    assert resp.status_code == 428
    # Row unchanged.
    assert summaries_repo._rows[(auth_user_id, "global", None)].content == "v1"


def test_patch_global_stale_if_match_returns_412(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    """D-K8-03: stale If-Match returns the current row in the 412 body."""
    existing = _make_summary(auth_user_id, "global", None, "v3")
    existing = existing.model_copy(update={"version": 3})
    summaries_repo.seed(existing)
    resp = client.patch(
        "/v1/knowledge/summaries/global",
        json={"content": "loser"},
        headers=_im(1),  # stale — real version is 3
    )
    assert resp.status_code == 412
    body = resp.json()
    assert body["version"] == 3
    assert body["content"] == "v3"
    assert resp.headers.get("etag") == 'W/"3"'
    assert summaries_repo._rows[(auth_user_id, "global", None)].content == "v3"


def test_patch_global_oversize_returns_422(client: TestClient):
    too_big = "x" * 50_001
    resp = client.patch(
        "/v1/knowledge/summaries/global", json={"content": too_big}
    )
    assert resp.status_code == 422


def test_patch_global_check_violation_maps_to_422(auth_user_id: UUID):
    """Defense-in-depth: even if Pydantic somehow lets oversize through,
    the DB CheckViolation is mapped to 422 not 500."""
    app = FastAPI()
    app.include_router(summaries_router)
    exploding = _ExplodingSummariesRepo()
    app.dependency_overrides[get_summaries_repo] = lambda: exploding
    app.dependency_overrides[get_current_user] = lambda: auth_user_id
    c = TestClient(app)
    resp = c.patch("/v1/knowledge/summaries/global", json={"content": "ok"})
    assert resp.status_code == 422
    assert "knowledge_summaries_content_len" in resp.json()["detail"]


# ── D-K8-01: global summary version history ─────────────────────────────


def test_list_global_versions_empty(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    """No prior updates → no history rows."""
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "only"))
    resp = client.get("/v1/knowledge/summaries/global/versions")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


def test_list_global_versions_returns_newest_first(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    """Two updates → two history rows, newest version first."""
    # Seed v1, update to v2, update to v3. Each update archives the
    # previous state so history has [v1, v2]; the API returns newest
    # (v2) first.
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "a"))
    # First update: v1 "a" → v2 "b" (archives "a"@1)
    client.patch(
        "/v1/knowledge/summaries/global",
        json={"content": "b"},
        headers=_im(1),
    )
    # Second update: v2 "b" → v3 "c" (archives "b"@2)
    client.patch(
        "/v1/knowledge/summaries/global",
        json={"content": "c"},
        headers=_im(2),
    )
    resp = client.get("/v1/knowledge/summaries/global/versions")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    assert items[0]["version"] == 2
    assert items[0]["content"] == "b"
    assert items[0]["edit_source"] == "manual"
    assert items[1]["version"] == 1
    assert items[1]["content"] == "a"


def test_list_global_versions_cross_user_isolation(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    """User B's history is not visible to user A even though the
    fake repo is keyed by user_id — defense-in-depth."""
    other = uuid4()
    # Give user B a history entry.
    summaries_repo.seed(_make_summary(other, "global", None, "other-v1"))
    summaries_repo._push_history(
        other,
        "global",
        None,
        summaries_repo._rows[(other, "global", None)],
        edit_source="manual",
    )
    resp = client.get("/v1/knowledge/summaries/global/versions")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_get_global_version_ok(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    """Fetch a specific archived version."""
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "a"))
    client.patch(
        "/v1/knowledge/summaries/global",
        json={"content": "b"},
        headers=_im(1),
    )
    resp = client.get("/v1/knowledge/summaries/global/versions/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 1
    assert body["content"] == "a"


def test_get_global_version_not_found(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "a"))
    resp = client.get("/v1/knowledge/summaries/global/versions/99")
    assert resp.status_code == 404


def test_rollback_global_creates_new_version(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    """Rollback copies the target content to the live row as a NEW
    version (not a rewind). The pre-rollback row goes to history
    with edit_source='rollback'."""
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "a"))
    # v1 "a" → v2 "b" → v3 "c"
    client.patch("/v1/knowledge/summaries/global", json={"content": "b"}, headers=_im(1))
    client.patch("/v1/knowledge/summaries/global", json={"content": "c"}, headers=_im(2))

    # Roll back to v1 from current v3 — must carry If-Match.
    resp = client.post(
        "/v1/knowledge/summaries/global/versions/1/rollback",
        headers=_im(3),
    )
    assert resp.status_code == 200
    body = resp.json()
    # NEW version (3 + 1 = 4), NOT a rewind.
    assert body["version"] == 4
    assert body["content"] == "a"
    assert resp.headers.get("etag") == 'W/"4"'

    # History should now have [v1 manual, v2 manual, v3 rollback].
    list_resp = client.get("/v1/knowledge/summaries/global/versions")
    items = list_resp.json()["items"]
    versions = [(i["version"], i["edit_source"]) for i in items]
    assert (3, "rollback") in versions
    assert (2, "manual") in versions
    assert (1, "manual") in versions


def test_rollback_requires_if_match(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    """Rollback is a mutating operation — honours the same strict
    If-Match contract as PATCH."""
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "a"))
    client.patch("/v1/knowledge/summaries/global", json={"content": "b"}, headers=_im(1))
    resp = client.post("/v1/knowledge/summaries/global/versions/1/rollback")
    assert resp.status_code == 428


def test_rollback_stale_if_match_returns_412(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    """Stale If-Match on rollback returns the current row in the
    412 body — same contract as PATCH."""
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "a"))
    client.patch("/v1/knowledge/summaries/global", json={"content": "b"}, headers=_im(1))
    # Current version is 2, send stale version 1.
    resp = client.post(
        "/v1/knowledge/summaries/global/versions/1/rollback",
        headers=_im(1),
    )
    assert resp.status_code == 412


def test_rollback_target_version_not_found(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    """Rolling back to a version that was never archived → 404."""
    summaries_repo.seed(_make_summary(auth_user_id, "global", None, "a"))
    resp = client.post(
        "/v1/knowledge/summaries/global/versions/99/rollback",
        headers=_im(1),
    )
    assert resp.status_code == 404


# ── PATCH /v1/knowledge/projects/{id}/summary ────────────────────────────


def test_patch_project_summary_creates(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    project_id = uuid4()
    summaries_repo.own_project(auth_user_id, project_id)
    # First save — no If-Match needed (same as global).
    resp = client.patch(
        f"/v1/knowledge/projects/{project_id}/summary",
        json={"content": "project summary"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "project summary"
    assert body["scope_type"] == "project"
    assert body["scope_id"] == str(project_id)
    assert body["version"] == 1
    assert (auth_user_id, "project", project_id) in summaries_repo._rows


def test_patch_project_summary_updates(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    project_id = uuid4()
    summaries_repo.own_project(auth_user_id, project_id)
    summaries_repo.seed(
        _make_summary(auth_user_id, "project", project_id, "v1")
    )
    resp = client.patch(
        f"/v1/knowledge/projects/{project_id}/summary",
        json={"content": "v2"},
        headers=_im(1),
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == "v2"
    assert resp.json()["version"] == 2


def test_patch_project_summary_empty_allowed(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    project_id = uuid4()
    summaries_repo.own_project(auth_user_id, project_id)
    resp = client.patch(
        f"/v1/knowledge/projects/{project_id}/summary",
        json={"content": ""},
    )
    assert resp.status_code == 200
    assert resp.json()["content"] == ""


def test_patch_project_summary_cross_user_returns_404(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
):
    """The project belongs to another user — the CTE's EXISTS clause
    finds no matching row, so the upsert inserts zero rows and returns
    None, which the router maps to 404. Critical: no orphan summary
    planted, no cache invalidation fired."""
    other = uuid4()
    project_id = uuid4()
    summaries_repo.own_project(other, project_id)  # owned by someone else
    resp = client.patch(
        f"/v1/knowledge/projects/{project_id}/summary",
        json={"content": "leak attempt"},
    )
    assert resp.status_code == 404
    assert summaries_repo._rows == {}
    assert summaries_repo.invalidations == []


def test_patch_project_summary_nonexistent_returns_404(
    client: TestClient, summaries_repo: FakeSummariesRepo
):
    resp = client.patch(
        f"/v1/knowledge/projects/{uuid4()}/summary",
        json={"content": "x"},
    )
    assert resp.status_code == 404
    assert summaries_repo._rows == {}
    assert summaries_repo.invalidations == []


def test_patch_project_summary_update_without_if_match_returns_428(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    """D-K8-03: project-scoped summary update path requires If-Match."""
    project_id = uuid4()
    summaries_repo.own_project(auth_user_id, project_id)
    summaries_repo.seed(
        _make_summary(auth_user_id, "project", project_id, "v1")
    )
    resp = client.patch(
        f"/v1/knowledge/projects/{project_id}/summary",
        json={"content": "v2"},
    )
    assert resp.status_code == 428


def test_patch_project_summary_oversize_returns_422(
    client: TestClient,
    summaries_repo: FakeSummariesRepo,
    auth_user_id: UUID,
):
    project_id = uuid4()
    summaries_repo.own_project(auth_user_id, project_id)
    too_big = "x" * 50_001
    resp = client.patch(
        f"/v1/knowledge/projects/{project_id}/summary",
        json={"content": too_big},
    )
    assert resp.status_code == 422


def test_patch_project_summary_check_violation_maps_to_422(auth_user_id: UUID):
    app = FastAPI()
    app.include_router(summaries_router)
    exploding = _ExplodingSummariesRepo()
    project_id = uuid4()
    exploding.own_project(auth_user_id, project_id)
    app.dependency_overrides[get_summaries_repo] = lambda: exploding
    app.dependency_overrides[get_current_user] = lambda: auth_user_id
    c = TestClient(app)
    resp = c.patch(
        f"/v1/knowledge/projects/{project_id}/summary",
        json={"content": "ok"},
    )
    assert resp.status_code == 422
    assert "knowledge_summaries_content_len" in resp.json()["detail"]


# ── auth ─────────────────────────────────────────────────────────────────


def test_no_jwt_returns_401_on_all_routes(summaries_repo: FakeSummariesRepo):
    """Router-level Depends(get_current_user) returns 401 before the
    route runs when the JWT is missing entirely."""
    app = FastAPI()
    app.include_router(summaries_router)
    app.dependency_overrides[get_summaries_repo] = lambda: summaries_repo
    raw = TestClient(app)
    assert raw.get("/v1/knowledge/summaries").status_code == 401
    assert raw.patch(
        "/v1/knowledge/summaries/global", json={"content": "x"}
    ).status_code == 401
    assert raw.patch(
        f"/v1/knowledge/projects/{uuid4()}/summary", json={"content": "x"}
    ).status_code == 401
