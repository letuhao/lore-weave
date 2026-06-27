"""W11 — motif publish/adopt SYNC tests (TestClient + a stub MotifRepo).

These exercise the SYNC ROUTER logic (upstream-diff + apply-merge) without a DB.
The two surfaces:

  GET  /v1/composition/motifs/{id}/upstream-diff  → per-field diff (ours vs theirs)
  POST /v1/composition/motifs/{id}/sync           → apply chosen merge on confirm

HONESTY (the central design fact, asserted below): the `motif` table retains ONLY
the CURRENT upstream row — `version` is a single in-place counter, there is NO
`motif_revision`/history table (see app/db/migrate.py §motif). So a true 3-way base
(upstream AT the pinned `source_version`) is NOT retrievable. The diff DEGRADES to a
**2-way** (ours vs theirs-current), labelled `diff_mode="two_way"` + `base_available=False`
in every response. We DO NOT fabricate a base. (Deferral: D-MOTIF-SYNC-3WAY-BASE.)

House style mirrors test_motif_router.py: app.dependency_overrides + a stub repo;
quotas toggled by monkeypatching settings.motif_max_public.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import settings as _settings
from app.db.models import Motif

USER = uuid.uuid4()
OTHER = uuid.uuid4()


def _motif(**kw) -> Motif:
    base = dict(
        id=kw.pop("id", uuid.uuid4()),
        owner_user_id=kw.pop("owner_user_id", USER),
        code=kw.pop("code", "cult.fortuitous"),
        name=kw.pop("name", "Lucky Break"),
    )
    base.update(kw)
    return Motif(**base)


class StubMotifRepo:
    """Honors only the F0/W1 MotifRepo surface the SYNC router calls (read-only:
    get_visible + patch). source_lookup is a hand map src_id → upstream Motif."""

    def __init__(self) -> None:
        self.get_result: Motif | None = None          # the caller's local (adopted) motif
        self.upstream_result: Motif | None = None      # the CURRENT upstream by lineage
        self.patch_result: Motif | None = None
        self.patch_raises: Exception | None = None
        self.last_patch_args = None
        self.shared_count = 0

    async def get_visible(self, caller_id, motif_id):
        return self.get_result

    async def patch(self, caller_id, motif_id, args, *, expected_version):
        self.last_patch_args = (caller_id, motif_id, args, expected_version)
        if self.patch_raises:
            raise self.patch_raises
        return self.patch_result

    async def count_shared_by_owner(self, owner_id):
        return self.shared_count


class StubPool:
    """A fetchrow-only pool stub. The router issues TWO fetchrow shapes:
      1. the upstream-resolve SELECT (returns `upstream_row`)
      2. the source_version RE-PIN UPDATE...RETURNING (returns `repin_row`)
    Route by the SQL verb so each gets the right record."""

    def __init__(self) -> None:
        self.upstream_row: dict | None = None
        self.repin_row: dict | None = {"source_version": 0}
        self.calls: list = []

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        if query.strip().upper().startswith("UPDATE"):
            return self.repin_row
        return self.upstream_row


@pytest.fixture
def ctx(monkeypatch):
    """TestClient with the DB pool + /mcp session manager stubbed (mirrors
    test_motif_mcp.client). The sync router resolves the upstream row + re-pin via
    app.db.pool.get_pool → our StubPool. redis/reaper off so the real lifespan
    network paths stay inert (fast + no cross-file leak)."""
    pool = StubPool()

    @asynccontextmanager
    async def _noop_session_manager():
        yield

    _mcp_stub = MagicMock()
    _mcp_stub.session_manager.run = _noop_session_manager

    with (
        patch("app.db.pool.create_pool", new_callable=AsyncMock),
        patch("app.db.pool.close_pool", new_callable=AsyncMock),
        patch("app.db.pool.get_pool", return_value=pool),
        patch("app.main.create_pool", new_callable=AsyncMock),
        patch("app.main.close_pool", new_callable=AsyncMock),
        patch("app.main.get_pool", return_value=pool),
        patch("app.main.run_migrations", new_callable=AsyncMock),
        patch("app.main.mcp_server", _mcp_stub),
        patch("app.main.get_grant_client", MagicMock()),
    ):
        _settings.redis_url = ""
        _settings.job_reaper_sweep_secs = 0
        monkeypatch.setattr("app.config.settings.motif_max_public", 0, raising=False)
        from app.main import app
        from app.deps import get_motif_repo
        from app.middleware.jwt_auth import get_current_user

        repo = StubMotifRepo()
        app.dependency_overrides[get_current_user] = lambda: USER
        app.dependency_overrides[get_motif_repo] = lambda: repo
        with TestClient(app) as c:
            yield c, repo, pool, monkeypatch
        app.dependency_overrides.clear()


# ── app wiring (proves the router includes + the app builds) ──────────────────


def test_app_builds_and_router_wired():
    """Importing app.main must not raise and the sync routes must be registered."""
    from app.main import app
    paths = {r.path for r in app.routes}
    assert "/v1/composition/motifs/{motif_id}/upstream-diff" in paths
    assert "/v1/composition/motifs/{motif_id}/sync" in paths


# ── upstream-diff (the 2-way degrade) ─────────────────────────────────────────


def test_diff_two_way_labelled_and_no_fabricated_base(ctx):
    """An adopted motif with local edits + a changed upstream → a per-field diff,
    HONESTLY labelled two_way with base_available=False (no fabricated base)."""
    c, repo, pool, _ = ctx
    src_id = uuid.uuid4()
    repo.get_result = _motif(
        owner_user_id=USER, source="adopted", source_ref=f"lineage:{src_id}",
        source_version=1, version=3, summary="my local summary",
        genre_tags=["wuxia"],
    )
    # theirs (upstream CURRENT), version moved to 4, summary changed.
    pool.upstream_row = {
        "id": src_id, "summary": "upstream new summary", "genre_tags": ["xianxia"],
        "beats": [], "roles": [], "preconditions": [], "effects": [], "version": 4,
        "visibility": "public", "owner_user_id": OTHER,
    }
    r = c.get(f"/v1/composition/motifs/{uuid.uuid4()}/upstream-diff")
    assert r.status_code == 200
    body = r.json()
    assert body["diff_mode"] == "two_way"
    assert body["base_available"] is False
    # the pinned + current upstream versions surface for the "update available" signal.
    assert body["pinned_source_version"] == 1
    assert body["upstream_version"] == 4
    assert body["update_available"] is True
    # per-field changes (summary + genre_tags differ; beats/roles do not).
    fields = body["fields"]
    assert fields["summary"]["changed"] is True
    assert fields["summary"]["ours"] == "my local summary"
    assert fields["summary"]["theirs"] == "upstream new summary"
    assert fields["genre_tags"]["changed"] is True
    assert fields["beats"]["changed"] is False
    # NO 'base' key anywhere — we never fabricate one.
    assert "base" not in fields["summary"]


def test_diff_no_update_when_versions_match(ctx):
    """Pinned == upstream current version → update_available False (still two_way)."""
    c, repo, pool, _ = ctx
    src_id = uuid.uuid4()
    repo.get_result = _motif(
        owner_user_id=USER, source="adopted", source_ref=f"lineage:{src_id}",
        source_version=2, version=2, summary="same",
    )
    pool.upstream_row = {
        "id": src_id, "summary": "same", "genre_tags": [], "beats": [],
        "roles": [], "preconditions": [], "effects": [], "version": 2,
        "visibility": "public", "owner_user_id": OTHER,
    }
    r = c.get(f"/v1/composition/motifs/{uuid.uuid4()}/upstream-diff")
    assert r.status_code == 200
    assert r.json()["update_available"] is False


def test_diff_local_motif_not_visible_404(ctx):
    """A foreign/missing local motif → uniform H13 not-found (no oracle)."""
    c, repo, pool, _ = ctx
    repo.get_result = None
    r = c.get(f"/v1/composition/motifs/{uuid.uuid4()}/upstream-diff")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "MOTIF_NOT_FOUND"


def test_diff_not_adopted_409(ctx):
    """A motif with no lineage (authored/system) has no upstream → 409, not a 500."""
    c, repo, pool, _ = ctx
    repo.get_result = _motif(owner_user_id=USER, source="authored", source_ref=None)
    r = c.get(f"/v1/composition/motifs/{uuid.uuid4()}/upstream-diff")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "MOTIF_NOT_ADOPTED"


def test_diff_upstream_gone_410(ctx):
    """The upstream source was archived/deleted since adopt → 410 gone, not a 500."""
    c, repo, pool, _ = ctx
    src_id = uuid.uuid4()
    repo.get_result = _motif(
        owner_user_id=USER, source="adopted", source_ref=f"lineage:{src_id}",
        source_version=1,
    )
    pool.upstream_row = None  # upstream no longer visible
    r = c.get(f"/v1/composition/motifs/{uuid.uuid4()}/upstream-diff")
    assert r.status_code == 410
    assert r.json()["detail"]["code"] == "MOTIF_UPSTREAM_GONE"


# ── sync apply (the merge on confirm) ─────────────────────────────────────────


def test_sync_accepts_theirs_and_repins(ctx):
    """accept=['summary'] applies theirs for summary via patch (with the local
    expected_version = optimistic lock), then re-pins source_version to the upstream
    CURRENT version via a direct owner-scoped UPDATE (NOT through patch — W1's
    MotifPatchArgs deliberately excludes source_version)."""
    c, repo, pool, _ = ctx
    src_id = uuid.uuid4()
    repo.get_result = _motif(
        owner_user_id=USER, source="adopted", source_ref=f"lineage:{src_id}",
        source_version=1, version=3, summary="mine",
    )
    pool.upstream_row = {
        "id": src_id, "summary": "theirs", "genre_tags": ["xianxia"], "beats": [],
        "roles": [], "preconditions": [], "effects": [], "version": 5,
        "visibility": "public", "owner_user_id": OTHER,
    }
    pool.repin_row = {"source_version": 5}
    repo.patch_result = _motif(owner_user_id=USER, summary="theirs", version=4,
                               source_version=5)
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/sync",
               json={"accept": ["summary"]})
    assert r.status_code == 200
    body = r.json()
    assert body["synced"] is True
    assert body["repinned_source_version"] == 5
    # patch received ONLY the accepted content field + the local expected_version
    # (source_version is NOT a patch arg → it re-pins via the direct UPDATE).
    _, _, args, expected_version = repo.last_patch_args
    assert args.summary == "theirs"
    assert not hasattr(args, "source_version")
    assert expected_version == 3
    # the re-pin UPDATE carried the upstream version.
    update_calls = [q for q, a in pool.calls if q.strip().upper().startswith("UPDATE")]
    assert len(update_calls) == 1


def test_sync_empty_accept_repins_only(ctx):
    """accept=[] (keep all local) skips patch entirely (no content edit) but STILL
    re-pins source_version to current upstream (acknowledging the user reviewed)."""
    c, repo, pool, _ = ctx
    src_id = uuid.uuid4()
    repo.get_result = _motif(
        owner_user_id=USER, source="adopted", source_ref=f"lineage:{src_id}",
        source_version=1, version=3, summary="mine",
    )
    pool.upstream_row = {
        "id": src_id, "summary": "theirs", "genre_tags": [], "beats": [],
        "roles": [], "preconditions": [], "effects": [], "version": 7,
        "visibility": "public", "owner_user_id": OTHER,
    }
    pool.repin_row = {"source_version": 7}
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/sync", json={"accept": []})
    assert r.status_code == 200
    assert r.json()["repinned_source_version"] == 7
    # accept=[] → patch was never called (no content change), only the re-pin UPDATE.
    assert repo.last_patch_args is None
    update_calls = [q for q, a in pool.calls if q.strip().upper().startswith("UPDATE")]
    assert len(update_calls) == 1


def test_sync_unknown_field_422(ctx):
    """A field not in the mergeable allow-list → 422 (ForbidExtra/validation)."""
    c, repo, pool, _ = ctx
    src_id = uuid.uuid4()
    repo.get_result = _motif(owner_user_id=USER, source="adopted",
                             source_ref=f"lineage:{src_id}", source_version=1)
    pool.upstream_row = {
        "id": src_id, "summary": "t", "genre_tags": [], "beats": [], "roles": [],
        "preconditions": [], "effects": [], "version": 2,
        "visibility": "public", "owner_user_id": OTHER,
    }
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/sync",
               json={"accept": ["owner_user_id"]})
    assert r.status_code == 422


def test_sync_not_adopted_409(ctx):
    c, repo, pool, _ = ctx
    repo.get_result = _motif(owner_user_id=USER, source="authored", source_ref=None)
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/sync", json={"accept": []})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "MOTIF_NOT_ADOPTED"


def test_sync_version_conflict_412(ctx):
    """A stale local row (someone edited it since the diff) → 412, surfaced from
    the repo's optimistic-lock raise (no silent overwrite)."""
    from app.db.repositories import VersionMismatchError
    c, repo, pool, _ = ctx
    src_id = uuid.uuid4()
    repo.get_result = _motif(
        owner_user_id=USER, source="adopted", source_ref=f"lineage:{src_id}",
        source_version=1, version=3, summary="mine",
    )
    pool.upstream_row = {
        "id": src_id, "summary": "theirs", "genre_tags": [], "beats": [], "roles": [],
        "preconditions": [], "effects": [], "version": 5,
        "visibility": "public", "owner_user_id": OTHER,
    }
    repo.patch_raises = VersionMismatchError(_motif(version=9))
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/sync",
               json={"accept": ["summary"]})
    assert r.status_code == 412
    assert r.json()["detail"]["code"] == "MOTIF_VERSION_CONFLICT"


# ── tenancy / auth ────────────────────────────────────────────────────────────


def test_sync_local_not_owned_404(ctx):
    """get_visible returns None for a foreign/missing local → uniform H13 404."""
    c, repo, pool, _ = ctx
    repo.get_result = None
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/sync", json={"accept": []})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "MOTIF_NOT_FOUND"


def test_sync_publish_quota_not_charged_on_private_sync(ctx):
    """Sync of a PRIVATE adopted motif touches no shareable-visibility, so the
    publish ceiling is never consulted even when at the cap."""
    c, repo, pool, mp = ctx
    mp.setattr("app.config.settings.motif_max_public", 1, raising=False)
    repo.shared_count = 1  # at the cap
    src_id = uuid.uuid4()
    repo.get_result = _motif(
        owner_user_id=USER, source="adopted", source_ref=f"lineage:{src_id}",
        source_version=1, version=3, visibility="private", summary="mine",
    )
    pool.upstream_row = {
        "id": src_id, "summary": "theirs", "genre_tags": [], "beats": [], "roles": [],
        "preconditions": [], "effects": [], "version": 5,
        "visibility": "public", "owner_user_id": OTHER,
    }
    repo.patch_result = _motif(owner_user_id=USER, summary="theirs", version=4,
                               visibility="private", source_version=5)
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/sync",
               json={"accept": ["summary"]})
    assert r.status_code == 200


def test_requires_auth(ctx):
    c, _, _, _ = ctx
    from app.main import app
    from app.middleware.jwt_auth import get_current_user
    app.dependency_overrides.pop(get_current_user, None)
    mid = uuid.uuid4()
    assert c.get(f"/v1/composition/motifs/{mid}/upstream-diff").status_code in (401, 403)
    assert c.post(f"/v1/composition/motifs/{mid}/sync",
                  json={"accept": []}).status_code in (401, 403)
