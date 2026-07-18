"""W1 — motif router tests (TestClient + a stub MotifRepo).

These exercise the ROUTER logic (status-code mapping, tenancy redaction, the
quota pre-checks, ForbidExtra, the idempotent 200-vs-201 adopt routing) without a
DB. The SQL-level guards (catalog allow-list no-leak, adopt suffix/idempotency,
advisory-lock per-owner, the publish-strip trigger) are proven against a real
Postgres in tests/integration/db/test_motif_w1.py.

House style: app.dependency_overrides + a stub repo (mirrors test_outline_canon_
routers.py). Quotas are toggled by monkeypatching settings (motif_max_* are vars,
like book-service's maxBooksPerUser).
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

from app.db.models import Motif
from app.db.repositories import VersionMismatchError

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
    """A hand stub honoring the F0 + W1 MotifRepo surface the router calls."""

    def __init__(self) -> None:
        self.list_result: list[Motif] = []
        self.get_result: Motif | None = _motif()
        self.create_result: Motif | None = _motif()
        self.create_raises: Exception | None = None
        self.patch_result: Motif | None = _motif(version=2)
        self.patch_raises: Exception | None = None
        self.archive_calls: list = []
        self.restore_calls: list = []
        self.restore_result: Motif | None = _motif(status="active")
        self.adopt_result: tuple[Motif, bool] = (_motif(source="adopted", version=1), True)
        self.adopt_raises: Exception | None = None
        self.catalog_result: tuple[list[dict], int] = ([], 0)
        self.shared_count = 0
        self.adopted_count = 0
        self.pattern_members_adopted = 0
        self.last_patch_args = None
        self.last_create_args = None
        self.last_adopt = None
        # motif graph (BE-M3)
        self.links_result: list = []
        self.create_link_result = None
        self.create_link_raises: Exception | None = None
        self.delete_link_result = True

    async def list_for_caller(self, caller_id, **kw):
        self.last_list = (caller_id, kw)
        return self.list_result

    async def get_visible(self, caller_id, motif_id):
        return self.get_result

    async def create(self, user_id, args, **kw):
        self.last_create_args = args
        self.last_create_kw = kw
        if self.create_raises:
            raise self.create_raises
        return self.create_result

    async def patch(self, caller_id, motif_id, args, *, expected_version, **kw):
        self.last_patch_args = (args, expected_version)
        if self.patch_raises:
            raise self.patch_raises
        return self.patch_result

    async def patch_shared(self, caller_id, motif_id, book_id, args, *, expected_version):
        self.last_patch_shared = (caller_id, motif_id, book_id, args, expected_version)
        if self.patch_raises:
            raise self.patch_raises
        return self.patch_result

    async def archive(self, caller_id, motif_id):
        self.archive_calls.append((caller_id, motif_id))

    async def archive_shared(self, caller_id, motif_id, book_id):
        self.archive_calls.append((caller_id, motif_id, book_id))

    async def restore(self, caller_id, motif_id):
        self.restore_calls.append((caller_id, motif_id))
        return self.restore_result

    async def restore_shared(self, caller_id, motif_id, book_id):
        self.restore_calls.append((caller_id, motif_id, book_id))
        return self.restore_result

    async def list_in_book(self, caller_id, book_id, **kw):
        self.last_list_in_book = (caller_id, book_id, kw)
        return self.list_result

    async def adopt(self, caller_id, src_motif_id, *, retag_genres=None,
                    book_id=None, book_shared=False):
        self.last_adopt = (caller_id, src_motif_id, retag_genres, book_id, book_shared)
        if self.adopt_raises:
            raise self.adopt_raises
        return self.adopt_result

    async def adopt_pattern_members(self, caller_id, src_motif_id, cloned_root_id):
        return self.pattern_members_adopted

    async def list_public(self, **kw):
        self.last_public = kw
        return self.catalog_result

    async def count_shared_by_owner(self, owner_id):
        return self.shared_count

    async def count_adopted_by_owner(self, owner_id):
        return self.adopted_count

    # ── motif graph (BE-M3) ──────────────────────────────────────────────────
    async def list_links(self, caller_id, motif_id, *, direction="both", kinds=None,
                         limit=200, book_id=None):
        self.last_list_links = (caller_id, motif_id, direction, kinds, book_id)
        return self.links_result

    async def create_link(self, caller_id, from_motif_id, to_motif_id, kind, *,
                          ord=None, book_id=None):
        self.last_create_link = (caller_id, from_motif_id, to_motif_id, kind, ord, book_id)
        if self.create_link_raises:
            raise self.create_link_raises
        return self.create_link_result

    async def delete_link(self, caller_id, link_id, *, book_id=None):
        self.last_delete_link = (caller_id, link_id, book_id)
        return self.delete_link_result


def _unique_violation() -> asyncpg.UniqueViolationError:
    return asyncpg.UniqueViolationError("dup")


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    # quotas OFF by default (0 = unlimited); individual tests raise them.
    monkeypatch.setattr("app.config.settings.motif_max_public", 0, raising=False)
    monkeypatch.setattr("app.config.settings.motif_max_adopt", 0, raising=False)
    from app.main import app
    from app.deps import get_grant_client_dep, get_motif_repo
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_current_user

    repo = StubMotifRepo()

    class _FakeGrant:
        """Stub GrantClient: `level` drives authorize_book (NONE→404, < need→403)."""
        def __init__(self) -> None:
            self.level = GrantLevel.EDIT
            self.calls: list = []

        async def resolve_grant(self, book_id, caller):
            self.calls.append((book_id, caller))
            return self.level

    grant = _FakeGrant()
    repo.grant = grant  # expose to tests via the repo handle
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_motif_repo] = lambda: repo
    app.dependency_overrides[get_grant_client_dep] = lambda: grant
    with TestClient(app) as c:
        yield c, repo, monkeypatch
    app.dependency_overrides.clear()


# ── create / stamp / ForbidExtra / dup ───────────────────────────────────────


def test_create_stamps_owner_and_201(ctx):
    c, repo, _ = ctx
    repo.create_result = _motif(owner_user_id=USER, code="x")
    r = c.post("/v1/composition/motifs", json={"code": "x", "name": "X"})
    assert r.status_code == 201
    assert r.json()["owner_user_id"] == str(USER)
    # the args the router built carry NO owner field (server stamps it).
    assert not hasattr(repo.last_create_args, "owner_user_id")


def test_create_forbids_owner_arg_422(ctx):
    c, _, _ = ctx
    # _ForbidExtra rejects a smuggled owner_user_id → 422 before the repo.
    r = c.post("/v1/composition/motifs",
               json={"code": "x", "name": "X", "owner_user_id": str(OTHER)})
    assert r.status_code == 422


def test_create_duplicate_code_409(ctx):
    c, repo, _ = ctx
    repo.create_raises = _unique_violation()
    r = c.post("/v1/composition/motifs", json={"code": "dup", "name": "D"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "MOTIF_CODE_EXISTS"


# ── get / IDOR redaction ──────────────────────────────────────────────────────


def test_get_owner_full_view(ctx):
    c, repo, _ = ctx
    repo.get_result = _motif(owner_user_id=USER, examples=[{"text": "mine"}],
                             source_ref="lineage:abc")
    r = c.get(f"/v1/composition/motifs/{uuid.uuid4()}")
    assert r.status_code == 200
    body = r.json()
    assert body["examples"] == [{"text": "mine"}]      # owner sees examples
    assert body["owner_user_id"] == str(USER)


def test_get_public_detail_redacts_examples_and_owner(ctx):
    c, repo, _ = ctx
    # a PUBLIC motif owned by OTHER → visible, but redacted for the non-owner.
    repo.get_result = _motif(owner_user_id=OTHER, visibility="public",
                             roles=[{"key": "hero"}], examples=[{"text": "x"}],
                             source_ref="lineage:abc")
    r = c.get(f"/v1/composition/motifs/{uuid.uuid4()}")
    assert r.status_code == 200
    body = r.json()
    assert body["roles"] == [{"key": "hero"}]          # meso content stays (public)
    assert body["examples"] == []                       # stripped for non-owner
    assert body["owner_user_id"] is None                # author not leaked
    assert body["source_ref"] == "lineage:abc"          # opaque token form ok


def test_get_not_visible_404(ctx):
    c, repo, _ = ctx
    repo.get_result = None
    r = c.get(f"/v1/composition/motifs/{uuid.uuid4()}")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "MOTIF_NOT_FOUND"


# ── patch / archive ───────────────────────────────────────────────────────────


def test_patch_not_owned_404(ctx):
    c, repo, _ = ctx
    repo.patch_result = None  # repo returns None for a foreign/system/missing row
    r = c.patch(f"/v1/composition/motifs/{uuid.uuid4()}", json={"name": "x"})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "MOTIF_NOT_FOUND"


def test_patch_if_match_stale_412(ctx):
    c, repo, _ = ctx
    repo.patch_raises = VersionMismatchError(_motif(version=5))
    r = c.patch(f"/v1/composition/motifs/{uuid.uuid4()}", json={"name": "x"},
                headers={"If-Match": "1"})
    assert r.status_code == 412
    assert r.json()["detail"]["current"]["version"] == 5
    # the parsed If-Match reached the repo as expected_version=1.
    assert repo.last_patch_args[1] == 1


def test_archive_returns_uniform_ok(ctx):
    c, repo, _ = ctx
    mid = uuid.uuid4()
    r = c.delete(f"/v1/composition/motifs/{mid}")
    assert r.status_code == 200 and r.json() == {"id": str(mid), "archived": True}
    assert repo.archive_calls == [(USER, mid)]


def test_restore_returns_the_row(ctx):
    # S-08: POST /restore un-archives (owner) and returns the row so the library refreshes.
    c, repo, _ = ctx
    mid = uuid.uuid4()
    r = c.post(f"/v1/composition/motifs/{mid}/restore")
    assert r.status_code == 200 and r.json()["status"] == "active"
    assert repo.restore_calls == [(USER, mid)]


def test_restore_not_restorable_404(ctx):
    # missing / not-owned / not-archived → repo returns None → 404 (no oracle).
    c, repo, _ = ctx
    repo.restore_result = None
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/restore")
    assert r.status_code == 404


def test_restore_shared_tier_edit_gated(ctx):
    # with book_id → EDIT-gated restore_shared (the fake grant defaults to EDIT).
    c, repo, _ = ctx
    mid, book = uuid.uuid4(), uuid.uuid4()
    r = c.post(f"/v1/composition/motifs/{mid}/restore?book_id={book}")
    assert r.status_code == 200
    assert repo.restore_calls == [(USER, mid, book)]


# ── publish quota (B-4) ───────────────────────────────────────────────────────


def test_create_public_over_quota_409(ctx):
    c, repo, mp = ctx
    mp.setattr("app.config.settings.motif_max_public", 2, raising=False)
    repo.shared_count = 2  # already at the cap
    r = c.post("/v1/composition/motifs",
               json={"code": "x", "name": "X", "visibility": "public"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "MOTIF_PUBLISH_LIMIT_REACHED"
    assert r.json()["detail"]["limit"] == 2


def test_create_private_ignores_publish_quota(ctx):
    c, repo, mp = ctx
    mp.setattr("app.config.settings.motif_max_public", 0, raising=False)
    repo.shared_count = 999
    r = c.post("/v1/composition/motifs", json={"code": "x", "name": "X"})  # private
    assert r.status_code == 201


def test_patch_publish_over_quota_409(ctx):
    c, repo, mp = ctx
    mp.setattr("app.config.settings.motif_max_public", 1, raising=False)
    repo.shared_count = 1
    # the current row is private+owned → flipping to public DOES charge quota.
    repo.get_result = _motif(owner_user_id=USER, visibility="private")
    r = c.patch(f"/v1/composition/motifs/{uuid.uuid4()}", json={"visibility": "public"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "MOTIF_PUBLISH_LIMIT_REACHED"


def test_patch_already_public_no_quota_recharge(ctx):
    c, repo, mp = ctx
    mp.setattr("app.config.settings.motif_max_public", 1, raising=False)
    repo.shared_count = 1  # at the cap, but the row is ALREADY shared
    repo.get_result = _motif(owner_user_id=USER, visibility="public")
    repo.patch_result = _motif(owner_user_id=USER, visibility="public", version=2)
    # patching an already-public row (e.g. editing the name while it stays public)
    # must NOT be refused by the publish ceiling.
    r = c.patch(f"/v1/composition/motifs/{uuid.uuid4()}", json={"visibility": "public"})
    assert r.status_code == 200


# ── adopt (idempotent 200 vs 201; quota; not-visible) ────────────────────────


def test_adopt_fresh_201(ctx):
    c, repo, _ = ctx
    adopted = _motif(owner_user_id=USER, source="adopted", version=1)
    repo.adopt_result = (adopted, True)
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/adopt", json={})
    assert r.status_code == 201
    assert r.json()["source"] == "adopted"
    assert r.json()["members_adopted"] == 0


def test_adopt_idempotent_returns_200(ctx):
    c, repo, _ = ctx
    existing = _motif(owner_user_id=USER, source="adopted", version=1)
    repo.adopt_result = (existing, False)  # already adopted → not created
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/adopt", json={})
    assert r.status_code == 200


def test_adopt_retag_passes_through(ctx):
    c, repo, _ = ctx
    src = uuid.uuid4()
    r = c.post(f"/v1/composition/motifs/{src}/adopt", json={"retag_genres": ["wuxia"]})
    assert r.status_code == 201
    # default target='user' → no book context (book_id None, book_shared False).
    assert repo.last_adopt == (USER, src, ["wuxia"], None, False)


def test_adopt_source_not_visible_404(ctx):
    c, repo, _ = ctx
    repo.adopt_raises = LookupError("not visible")
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/adopt", json={})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "MOTIF_NOT_FOUND"


def test_adopt_over_quota_409(ctx):
    c, repo, mp = ctx
    mp.setattr("app.config.settings.motif_max_adopt", 3, raising=False)
    repo.adopted_count = 3
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/adopt", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "MOTIF_ADOPT_LIMIT_REACHED"


def test_adopt_pattern_reports_members(ctx):
    c, repo, _ = ctx
    repo.adopt_result = (_motif(owner_user_id=USER, source="adopted",
                                kind="pattern", version=1), True)
    repo.pattern_members_adopted = 2
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/adopt", json={})
    assert r.status_code == 201 and r.json()["members_adopted"] == 2


def test_adopt_forbids_target_arg_422(ctx):
    c, _, _ = ctx
    # MotifAdopt forbids extras — no owner smuggling (target/book_id ARE legit now).
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/adopt",
               json={"target_owner": str(OTHER)})
    assert r.status_code == 422


# ── D-MOTIF-HTTP-ADOPT-BOOK + -BOOK-COLLAB-TIER: HTTP book/shared paths ─────────


def test_adopt_book_target_requires_book_id_400(ctx):
    c, _, _ = ctx
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/adopt", json={"target": "book"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "MOTIF_BOOK_REQUIRED"


def test_adopt_book_label_edit_gated_threads_book_id(ctx):
    c, repo, _ = ctx
    from app.grant_client import GrantLevel
    repo.grant.level = GrantLevel.EDIT
    book = uuid.uuid4()
    src = uuid.uuid4()
    r = c.post(f"/v1/composition/motifs/{src}/adopt",
               json={"target": "book", "book_id": str(book)})
    assert r.status_code == 201
    # EDIT-gated on the book + book_id threaded, book_shared False (model A label).
    assert repo.grant.calls and repo.grant.calls[0][0] == book
    assert repo.last_adopt[3] == book and repo.last_adopt[4] is False


def test_adopt_book_shared_edit_gated_threads_flag(ctx):
    c, repo, _ = ctx
    from app.grant_client import GrantLevel
    repo.grant.level = GrantLevel.EDIT
    book = uuid.uuid4()
    repo.adopt_result = (_motif(owner_user_id=USER, source="adopted",
                                book_id=book, book_shared=True, version=1), True)
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/adopt",
               json={"target": "book_shared", "book_id": str(book)})
    assert r.status_code == 201
    assert repo.last_adopt[3] == book and repo.last_adopt[4] is True


def test_adopt_book_shared_under_tier_403(ctx):
    c, repo, _ = ctx
    from app.grant_client import GrantLevel
    repo.grant.level = GrantLevel.VIEW   # below EDIT
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/adopt",
               json={"target": "book_shared", "book_id": str(uuid.uuid4())})
    assert r.status_code == 403


def test_adopt_book_no_grant_404(ctx):
    c, repo, _ = ctx
    from app.grant_client import GrantLevel
    repo.grant.level = GrantLevel.NONE
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/adopt",
               json={"target": "book", "book_id": str(uuid.uuid4())})
    assert r.status_code == 404


def test_adopt_book_shared_skips_pattern_member_adopt(ctx):
    """A shared pattern root does NOT auto-adopt its members into the adopter's private tier
    (the half-shared-pattern guard) — members_adopted stays 0."""
    c, repo, _ = ctx
    from app.grant_client import GrantLevel
    repo.grant.level = GrantLevel.EDIT
    book = uuid.uuid4()
    repo.adopt_result = (_motif(owner_user_id=USER, source="adopted", kind="pattern",
                                book_id=book, book_shared=True, version=1), True)
    repo.pattern_members_adopted = 5  # would be used if member-adopt ran
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/adopt",
               json={"target": "book_shared", "book_id": str(book)})
    assert r.status_code == 201 and r.json()["members_adopted"] == 0


def test_patch_shared_edit_gated(ctx):
    c, repo, _ = ctx
    from app.grant_client import GrantLevel
    repo.grant.level = GrantLevel.EDIT
    book = uuid.uuid4()
    mid = uuid.uuid4()
    repo.patch_result = _motif(owner_user_id=OTHER, book_id=book, book_shared=True, version=2)
    r = c.patch(f"/v1/composition/motifs/{mid}?book_id={book}", json={"name": "Edited"})
    assert r.status_code == 200
    assert repo.last_patch_shared[1] == mid and repo.last_patch_shared[2] == book
    assert repo.grant.calls and repo.grant.calls[0][0] == book


def test_patch_shared_under_tier_403(ctx):
    c, repo, _ = ctx
    from app.grant_client import GrantLevel
    repo.grant.level = GrantLevel.VIEW
    r = c.patch(f"/v1/composition/motifs/{uuid.uuid4()}?book_id={uuid.uuid4()}",
                json={"name": "x"})
    assert r.status_code == 403


def test_delete_shared_edit_gated(ctx):
    c, repo, _ = ctx
    from app.grant_client import GrantLevel
    repo.grant.level = GrantLevel.EDIT
    book = uuid.uuid4()
    mid = uuid.uuid4()
    r = c.delete(f"/v1/composition/motifs/{mid}?book_id={book}")
    assert r.status_code == 200 and r.json()["archived"] is True
    # archive_shared recorded a 3-tuple (caller, motif, book); owner archive is a 2-tuple.
    assert (USER, mid, book) in repo.archive_calls


def test_list_book_view_gated(ctx):
    c, repo, _ = ctx
    from app.grant_client import GrantLevel
    repo.grant.level = GrantLevel.VIEW   # VIEW is enough to read
    book = uuid.uuid4()
    own = _motif(owner_user_id=USER, code="own")
    shared = _motif(owner_user_id=OTHER, book_id=book, book_shared=True, code="shared")
    repo.list_result = [own, shared]
    r = c.get(f"/v1/composition/motifs/book/{book}")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2 and body["book_id"] == str(book)
    by_code = {m["code"]: m for m in body["motifs"]}
    assert by_code["shared"]["book_shared"] is True
    assert by_code["shared"]["book_id"] == str(book)
    assert repo.last_list_in_book[1] == book


def test_list_book_no_grant_404(ctx):
    c, repo, _ = ctx
    from app.grant_client import GrantLevel
    repo.grant.level = GrantLevel.NONE
    r = c.get(f"/v1/composition/motifs/book/{uuid.uuid4()}")
    assert r.status_code == 404


# ── catalog (router serialization; allow-list no-leak proven in the DB test) ──


def test_catalog_serializes_allowlist_and_adopt_hint(ctx):
    c, repo, _ = ctx
    mid = uuid.uuid4()
    # the repo returns ONLY the allow-list cols (no embedding/examples/source_ref).
    repo.catalog_result = ([{
        "id": mid, "code": "c", "language": "en", "kind": "sequence",
        "category": None, "name": "N", "summary": "s", "genre_tags": ["xianxia"],
        "tension_target": 3, "emotion_target": None, "source": "authored",
        "abstraction_confidence": None, "judge_score": None, "version": 1,
        "updated_at": None,
    }], 1)
    r = c.get("/v1/composition/motifs/catalog")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == str(mid)
    assert item["adopt_target"] == "user"
    # the never-leak fields are structurally absent from the allow-list row.
    assert "embedding" not in item
    assert "examples" not in item
    assert "source_ref" not in item


def test_list_scope_mine_maps_to_user(ctx):
    c, repo, _ = ctx
    repo.list_result = [_motif()]
    r = c.get("/v1/composition/motifs?scope=mine")
    assert r.status_code == 200
    assert repo.last_list[1]["scope"] == "user"  # router maps mine→user for the repo


# ── auth ──────────────────────────────────────────────────────────────────────


def test_requires_auth(ctx):
    """With the auth override REMOVED, every motif route is 401/403 (the real
    get_current_user runs and there is no bearer token)."""
    c, _, _ = ctx
    from app.main import app
    from app.middleware.jwt_auth import get_current_user
    app.dependency_overrides.pop(get_current_user, None)
    assert c.get("/v1/composition/motifs").status_code in (401, 403)
    assert c.get("/v1/composition/motifs/catalog").status_code in (401, 403)
    assert c.post("/v1/composition/motifs", json={"code": "x", "name": "X"}).status_code in (401, 403)


# ── motif graph (BE-M3) — links list / create / delete ────────────────────────


def _motif_link(**kw):
    from app.db.models import MotifLink
    base = dict(
        id=kw.pop("id", uuid.uuid4()),
        from_motif_id=kw.pop("from_motif_id", uuid.uuid4()),
        to_motif_id=kw.pop("to_motif_id", uuid.uuid4()),
        kind=kw.pop("kind", "precedes"),
    )
    base.update(kw)
    return MotifLink(**base)


def _check_violation() -> asyncpg.CheckViolationError:
    return asyncpg.CheckViolationError("motif_link_guard")


def test_list_links_returns_edges_and_count(ctx):
    c, repo, _ = ctx
    mid = uuid.uuid4()
    repo.links_result = [{"kind": "precedes", "direction": "out",
                          "neighbor": {"id": str(uuid.uuid4()), "code": "x", "name": "X"}}]
    r = c.get(f"/v1/composition/motifs/{mid}/links")
    assert r.status_code == 200
    body = r.json()
    assert body["motif_id"] == str(mid)
    assert body["count"] == 1 and len(body["links"]) == 1
    # default direction is 'both'; no book gate on the user-tier read
    assert repo.last_list_links[2] == "both" and repo.last_list_links[4] is None


def test_list_links_rejects_bad_direction(ctx):
    c, _, _ = ctx
    r = c.get(f"/v1/composition/motifs/{uuid.uuid4()}/links?direction=sideways")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "MOTIF_LINK_DIRECTION"


def test_list_links_not_visible_anchor_is_empty_not_404(ctx):
    """IDOR-safe: an anchor you can't see returns [] (no existence oracle), never 404."""
    c, repo, _ = ctx
    repo.links_result = []
    r = c.get(f"/v1/composition/motifs/{uuid.uuid4()}/links")
    assert r.status_code == 200 and r.json()["count"] == 0


def test_list_links_shared_book_graph_is_view_gated(ctx):
    c, repo, _ = ctx
    book = uuid.uuid4()
    r = c.get(f"/v1/composition/motifs/{uuid.uuid4()}/links?book_id={book}")
    assert r.status_code == 200
    # the VIEW grant was resolved for the book, and book_id rode through to the repo
    assert repo.grant.calls and repo.grant.calls[-1][0] == book
    assert repo.last_list_links[4] == book


def test_create_link_201(ctx):
    c, repo, _ = ctx
    frm, to = uuid.uuid4(), uuid.uuid4()
    repo.create_link_result = _motif_link(from_motif_id=frm, to_motif_id=to, kind="precedes")
    r = c.post(f"/v1/composition/motifs/{frm}/links",
               json={"to_motif_id": str(to), "kind": "precedes"})
    assert r.status_code == 201
    assert r.json()["kind"] == "precedes"
    # the path motif is the FROM endpoint; the body carries only TO
    assert repo.last_create_link[1] == frm and repo.last_create_link[2] == to


def test_create_link_cycle_or_selflink_is_409_with_the_trigger_message(ctx):
    """The DB motif_link_guard is the spec — a self-link/cycle surfaces as an inline 409,
    NOT a swallowed toast (plan 33 §3.1)."""
    c, repo, _ = ctx
    repo.create_link_raises = _check_violation()
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/links",
               json={"to_motif_id": str(uuid.uuid4()), "kind": "precedes"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "MOTIF_LINK_INVALID"


def test_create_link_duplicate_is_409(ctx):
    c, repo, _ = ctx
    repo.create_link_raises = _unique_violation()
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/links",
               json={"to_motif_id": str(uuid.uuid4()), "kind": "variant_of"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "MOTIF_LINK_EXISTS"


def test_create_link_endpoint_out_of_scope_is_404(ctx):
    """LookupError from the repo (an endpoint isn't yours / not in the book's shared tier)
    → a uniform 404, no oracle."""
    c, repo, _ = ctx
    repo.create_link_raises = LookupError("both endpoints must be motifs you own")
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/links",
               json={"to_motif_id": str(uuid.uuid4()), "kind": "composed_of"})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "MOTIF_NOT_FOUND"


def test_create_link_forbids_extra_fields(ctx):
    c, _, _ = ctx
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/links",
               json={"to_motif_id": str(uuid.uuid4()), "kind": "precedes",
                     "from_motif_id": str(uuid.uuid4())})  # from is the PATH, not the body
    assert r.status_code == 422


def test_create_link_shared_book_is_edit_gated(ctx):
    c, repo, _ = ctx
    from app.grant_client import GrantLevel
    book = uuid.uuid4()
    repo.grant.level = GrantLevel.VIEW  # below EDIT → 403
    r = c.post(f"/v1/composition/motifs/{uuid.uuid4()}/links",
               json={"to_motif_id": str(uuid.uuid4()), "kind": "precedes", "book_id": str(book)})
    assert r.status_code == 403


def test_delete_link_200(ctx):
    c, repo, _ = ctx
    repo.delete_link_result = True
    lid = uuid.uuid4()
    r = c.delete(f"/v1/composition/motif-links/{lid}")
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert repo.last_delete_link[1] == lid


def test_delete_link_missing_or_foreign_is_404(ctx):
    c, repo, _ = ctx
    repo.delete_link_result = False
    r = c.delete(f"/v1/composition/motif-links/{uuid.uuid4()}")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "MOTIF_NOT_FOUND"
