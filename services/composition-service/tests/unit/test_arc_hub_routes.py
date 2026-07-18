"""24 H5/H1 — the arc routes the Plan Hub drives: the E0 grant gate on each, and the
PH9/OQ-2 derived block the arc shell (read surface #1) must carry.

Why these exist (both are enforcement gaps a review caught, not new behaviour):

  * GRANT GATE — `POST /arcs/{id}/move` and `POST /books/{id}/arcs/assign-chapters` became
    live user write surface in H5. Both DO gate (`_gate_arc` → `_gate_book`, EDIT), but no
    test issued a request to either: deleting the `await _gate_book(...)` line left the whole
    suite green. Tenancy is LOCKED — a rule with no test that goes red is drift waiting to
    happen. The by-id move gates on the ROW's book (`gate-must-derive-scope-from-the-loaded-row`),
    and a missing node returns the SAME uniform 404 as a denied grant (no oracle).

  * DERIVED BLOCK — the Hub renders NO lanes without `span`/`is_contiguous`/`chapter_count` on
    each shell node. This attach already regressed once (the repo had the data; the router
    didn't attach it — the Hub came up empty against the real backend while every unit test
    passed, because the FE mocks returned the enriched shape). The repo function is covered
    only under an env-gated DB skip, so the ATTACH itself needs a runnable guard.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest
from fastapi.testclient import TestClient

from app.db.models import StructureNode
from app.grant_client import GrantLevel

USER, BOOK, ARC, SAGA = uuid4(), uuid4(), uuid4(), uuid4()


class _Grant:
    def __init__(self, level):
        self._level = level

    async def resolve_grant(self, book_id, user_id):
        return self._level

    async def resolve_access(self, book_id, user_id):
        return self._level, "active"


def _node(node_id, *, kind="arc", parent_id=None, rank="0m", title="Arc") -> StructureNode:
    return StructureNode(
        id=node_id, book_id=BOOK, parent_id=parent_id, kind=kind,
        depth=0 if parent_id is None else 1, rank=rank, title=title,
    )


@pytest.fixture
def client(monkeypatch):
    """TestClient factory: `mk(level, structures=...)` → (client, structures_mock).

    `_structures()` is a plain module function (not a Depends), so it is monkeypatched
    rather than dependency-overridden.
    """
    from app.main import app
    from app.deps import get_grant_client_dep
    from app.middleware.jwt_auth import get_bearer_token, get_current_user
    import app.routers.arc as arc_router

    def mk(level: GrantLevel, structures: AsyncMock | None = None):
        repo = structures or AsyncMock()
        monkeypatch.setattr(arc_router, "_structures", lambda: repo)
        # get_arc builds NarrativeThreadRepo(get_pool()) for open_promises; the repo is
        # mocked, so the pool is never used — stub get_pool so it doesn't raise.
        monkeypatch.setattr(arc_router, "get_pool", lambda: None)
        app.dependency_overrides[get_current_user] = lambda: USER
        app.dependency_overrides[get_bearer_token] = lambda: "jwt"
        app.dependency_overrides[get_grant_client_dep] = lambda: _Grant(level)
        return TestClient(app), repo

    yield mk
    app.dependency_overrides.clear()


# ── the grant gate on the H5 write routes ──────────────────────────────────────


def test_assign_chapters_view_grantee_403_and_never_writes(client):
    c, repo = client(GrantLevel.VIEW)
    r = c.post(
        f"/v1/composition/books/{BOOK}/arcs/assign-chapters",
        json={"structure_node_id": str(ARC), "chapter_node_ids": [str(uuid4())]},
    )
    assert r.status_code == 403
    repo.assign_chapters.assert_not_called()


def test_assign_chapters_null_unassigns_and_returns_null(client):
    # BE-A3: structure_node_id null UNASSIGNS (returns chapters to the pool). The route must
    # pass None through and echo structure_node_id: null, never coerce it to the string "None".
    repo = AsyncMock()
    repo.assign_chapters = AsyncMock(return_value=2)
    c, repo = client(GrantLevel.EDIT, structures=repo)
    ch = [str(uuid4()), str(uuid4())]
    r = c.post(
        f"/v1/composition/books/{BOOK}/arcs/assign-chapters",
        json={"structure_node_id": None, "chapter_node_ids": ch},
    )
    assert r.status_code == 200
    assert r.json() == {"assigned": 2, "structure_node_id": None}
    assert repo.assign_chapters.call_args.args[1] is None  # None, not the string "None"


def test_assign_chapters_non_grantee_404_and_never_writes(client):
    c, repo = client(GrantLevel.NONE)
    r = c.post(
        f"/v1/composition/books/{BOOK}/arcs/assign-chapters",
        json={"structure_node_id": str(ARC), "chapter_node_ids": [str(uuid4())]},
    )
    assert r.status_code == 404
    repo.assign_chapters.assert_not_called()


def test_arc_move_view_grantee_403_and_never_writes(client):
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(ARC))
    c, repo = client(GrantLevel.VIEW, structures=repo)
    r = c.post(f"/v1/composition/arcs/{ARC}/move", json={"new_parent_arc_id": None, "after_id": None})
    assert r.status_code == 403
    repo.move.assert_not_called()


def test_arc_move_non_grantee_404_and_never_writes(client):
    # The row EXISTS and its book resolves — but the caller holds no grant on that book.
    # 404 (not 403) so a non-grantee cannot use the status code as an existence oracle.
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(ARC))
    c, repo = client(GrantLevel.NONE, structures=repo)
    r = c.post(f"/v1/composition/arcs/{ARC}/move", json={"new_parent_arc_id": None, "after_id": None})
    assert r.status_code == 404
    repo.move.assert_not_called()


def test_arc_move_missing_node_is_the_same_404_as_a_denied_grant(client):
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    c, repo = client(GrantLevel.OWNER, structures=repo)
    r = c.post(f"/v1/composition/arcs/{ARC}/move", json={"new_parent_arc_id": None, "after_id": None})
    assert r.status_code == 404
    repo.move.assert_not_called()


def test_arc_list_non_grantee_404(client):
    c, repo = client(GrantLevel.NONE)
    r = c.get(f"/v1/composition/books/{BOOK}/arcs")
    assert r.status_code == 404
    repo.list_tree.assert_not_called()


# ── BE-A2: PATCH /arcs/{id} REQUIRES If-Match (no blind clobber) ────────────────


def test_patch_arc_without_if_match_is_428_and_never_writes(client):
    # The MCP door requires expected_version; the REST door used to make If-Match OPTIONAL,
    # so a missing header skipped the version clause AND the version bump — a legal blind
    # clobber on the object that steers generation. BE-A2: absent ⇒ 428, update untouched.
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(ARC))
    c, repo = client(GrantLevel.EDIT, structures=repo)
    r = c.patch(f"/v1/composition/arcs/{ARC}", json={"title": "New title"})
    assert r.status_code == 428
    assert r.json()["detail"]["code"] == "IF_MATCH_REQUIRED"
    repo.update.assert_not_called()


def test_patch_arc_with_if_match_passes_expected_version(client):
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(ARC))
    repo.update = AsyncMock(return_value=_node(ARC, title="New title"))
    c, repo = client(GrantLevel.EDIT, structures=repo)
    r = c.patch(
        f"/v1/composition/arcs/{ARC}", json={"title": "New title"}, headers={"If-Match": "7"},
    )
    assert r.status_code == 200
    assert repo.update.call_args.kwargs["expected_version"] == 7


def test_patch_arc_missing_if_match_gates_before_precondition(client):
    # Auth before precondition: a non-grantee with no If-Match still gets the uniform 404
    # (no existence oracle), never a 428 that would confirm the row exists.
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(ARC))
    c, repo = client(GrantLevel.NONE, structures=repo)
    r = c.patch(f"/v1/composition/arcs/{ARC}", json={"title": "New title"})
    assert r.status_code == 404
    repo.update.assert_not_called()


# ── D-ARC-TRACKS-ROSTER-SCHEMA: the key invariant, both doors (spec 32a §A) ─────


def test_create_arc_track_missing_key_is_422_and_never_writes(client):
    repo = AsyncMock()
    c, repo = client(GrantLevel.EDIT, structures=repo)
    r = c.post(f"/v1/composition/books/{BOOK}/arcs", json={"title": "A", "tracks": [{"label": "no key"}]})
    assert r.status_code == 422
    repo.create_node.assert_not_called()


def test_create_arc_empty_key_is_422(client):
    c, _ = client(GrantLevel.EDIT)
    r = c.post(f"/v1/composition/books/{BOOK}/arcs", json={"title": "A", "tracks": [{"key": ""}]})
    assert r.status_code == 422


def test_create_arc_duplicate_track_key_is_422(client):
    c, _ = client(GrantLevel.EDIT)
    r = c.post(
        f"/v1/composition/books/{BOOK}/arcs",
        json={"title": "A", "tracks": [{"key": "revenge"}, {"key": "revenge"}]},
    )
    assert r.status_code == 422
    assert "ARC_ENTRY_KEY_DUPLICATE" in r.text


def test_patch_arc_duplicate_roster_key_is_422(client):
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(ARC))
    c, repo = client(GrantLevel.EDIT, structures=repo)
    r = c.patch(
        f"/v1/composition/arcs/{ARC}",
        json={"roster": [{"key": "hero"}, {"key": "hero"}]},
        headers={"If-Match": "3"},
    )
    assert r.status_code == 422
    assert "ARC_ENTRY_KEY_DUPLICATE" in r.text
    repo.update.assert_not_called()


def test_mcp_arc_create_enforces_the_same_key_invariant():
    # The AGENT door (MCP) must reject the same corruption as REST — otherwise the agent can
    # still write an un-overridable/empty/duplicate key into the cascade (3-schema-source law).
    import pydantic
    from app.mcp.server import _ArcCreateArgs, _ArcUpdateArgs

    with pytest.raises(pydantic.ValidationError, match="ARC_ENTRY_KEY_DUPLICATE"):
        _ArcCreateArgs(book_id="b", tracks=[{"key": "a"}, {"key": "a"}])
    with pytest.raises(pydantic.ValidationError):
        _ArcCreateArgs(book_id="b", tracks=[{"key": ""}])
    with pytest.raises(pydantic.ValidationError):
        _ArcUpdateArgs(node_id="n", expected_version=1, roster=[{"key": "h"}, {"key": "h"}])
    # valid + extra preserved (dict form, extra="allow" on the entry model)
    ok = _ArcCreateArgs(book_id="b", tracks=[{"key": "revenge", "weight": 0.5}])
    assert ok.tracks[0]["weight"] == 0.5


def test_arc_track_allows_and_preserves_extra_fields():
    # extra="allow": the bug is the KEY; a richer agent write must round-trip losslessly,
    # never 422 (forbid) and never silently dropped (ignore).
    from app.routers.arc import ArcTrack

    t = ArcTrack.model_validate({"key": "revenge", "label": "Revenge line", "weight": 0.7})
    dumped = t.model_dump()
    assert dumped["key"] == "revenge"
    assert dumped["weight"] == 0.7  # preserved, not dropped


# ── BE-A1: the arc DETAIL door serves the dense-ranked block, never raw span() ──


def _detail_repo(block):
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(ARC))
    repo.resolve_tracks = AsyncMock(return_value=[])
    repo.resolve_roster = AsyncMock(return_value=[])
    repo.resolve_roster_bindings = AsyncMock(return_value={})
    repo.open_promises = AsyncMock(return_value=[])
    repo.derived_blocks = AsyncMock(return_value=block)
    return repo


def test_arc_get_serves_derived_block_span_not_raw_span(client):
    # The list route returns dense-ranked ORDINAL span; span() returns RAW strided story_order.
    # Serving span() here made the inspector render "Chapters 41000-58000". BE-A1: read
    # derived_blocks, never span(), so detail == list == MCP.
    repo = _detail_repo({ARC: {"span": {"from_order": 41, "to_order": 58}, "is_contiguous": False, "chapter_count": 18}})
    c, repo = client(GrantLevel.VIEW, structures=repo)
    r = c.get(f"/v1/composition/arcs/{ARC}")
    assert r.status_code == 200
    body = r.json()
    assert body["span"] == {"from_order": 41, "to_order": 58}
    assert body["chapter_count"] == 18
    assert body["is_contiguous"] is False
    repo.span.assert_not_called()  # the raw-unit door is dead


def test_arc_get_archived_node_absent_from_blocks_is_null_not_zero(client):
    # An archived node is absent from derived_blocks (live-only). Detail must render a NULL
    # block ("not computed"), never a computed chapter_count: 0 (the absent!=zero trap).
    repo = _detail_repo({})  # node not in the map
    c, repo = client(GrantLevel.VIEW, structures=repo)
    body = c.get(f"/v1/composition/arcs/{ARC}").json()
    assert body["span"] is None
    assert body["chapter_count"] is None
    assert body["is_contiguous"] is None
    repo.span.assert_not_called()


# ── BE-7a: extract-template — VIEW gate + the 409 duplicate-code map (spec 34) ──


def test_extract_template_non_grantee_is_404(client):
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(ARC))
    c, repo = client(GrantLevel.NONE, structures=repo)
    r = c.post(f"/v1/composition/arcs/{ARC}/extract-template", json={"code": "c", "name": "n"})
    assert r.status_code == 404


def test_extract_template_duplicate_code_is_409(client, monkeypatch):
    import app.routers.arc as arc_router

    async def _boom(*a, **k):
        raise asyncpg.UniqueViolationError("dup")
    monkeypatch.setattr(arc_router, "extract_template_from_arc", _boom)
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(ARC))
    c, repo = client(GrantLevel.EDIT, structures=repo)
    r = c.post(f"/v1/composition/arcs/{ARC}/extract-template", json={"code": "dup", "name": "n"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ARC_TEMPLATE_CODE_EXISTS"


def test_extract_template_success_201(client, monkeypatch):
    import app.routers.arc as arc_router

    async def _ok(*a, **k):
        return {"success": True, "outcome": "extracted", "template_id": "t1"}
    monkeypatch.setattr(arc_router, "extract_template_from_arc", _ok)
    repo = AsyncMock()
    repo.get = AsyncMock(return_value=_node(ARC))
    c, repo = client(GrantLevel.VIEW, structures=repo)
    r = c.post(f"/v1/composition/arcs/{ARC}/extract-template", json={"code": "c", "name": "My Arc"})
    assert r.status_code == 201
    assert r.json()["template_id"] == "t1"


# ── BE-7b: suggest — the B-3 privacy projection (a non-owner candidate strips source_ref) ──


class _FakeArc:
    def __init__(self, owner, source_ref="secret-source"):
        self.id = uuid4()
        self.code = "revenge-arc"
        self.name = "Revenge Arc"
        self.owner_user_id = owner
        self.chapter_span = 12
        self.genre_tags = ["xianxia"]
        self._source_ref = source_ref

    def model_dump(self, mode="json"):
        return {
            "id": str(self.id), "code": self.code, "name": self.name,
            "owner_user_id": str(self.owner_user_id) if self.owner_user_id else None,
            "chapter_span": self.chapter_span, "genre_tags": self.genre_tags,
            "source_ref": self._source_ref, "embedding": [0.1, 0.2], "threads": [{"key": "t1"}],
        }


class _Cand:
    def __init__(self, arc):
        self.arc_template = arc
        self.score = 0.9
        self.match_reason = {"genre": 1.0, "cosine": 0.8}


def _wire_suggest(monkeypatch, candidates):
    import app.routers.arc as arc_router

    class _Works:
        def __init__(self, pool): ...
        async def get(self, pid):
            from types import SimpleNamespace
            return SimpleNamespace(book_id=BOOK, project_id=pid)

    class _Retr:
        def __init__(self, pool): ...
        async def retrieve_arcs(self, caller, **k): return candidates
    monkeypatch.setattr(arc_router, "WorksRepo", _Works)
    monkeypatch.setattr(arc_router, "MotifRetriever", _Retr)


def test_suggest_strips_source_ref_from_a_non_owned_candidate(client, monkeypatch):
    other = uuid4()
    _wire_suggest(monkeypatch, [_Cand(_FakeArc(owner=other))])   # NOT the caller
    c, repo = client(GrantLevel.VIEW, structures=AsyncMock())
    r = c.post("/v1/composition/arc-templates/suggest", json={"project_id": str(uuid4()), "detail": "full"})
    assert r.status_code == 200
    tmpl = r.json()["candidates"][0]["arc_template"]
    # B-3: another user's imported-source reference + embedding + owner are STRIPPED.
    assert "source_ref" not in tmpl
    assert "embedding" not in tmpl
    assert "owner_user_id" not in tmpl
    # the shareable STRUCTURE survives.
    assert tmpl["threads"] == [{"key": "t1"}]


def test_suggest_owner_sees_their_own_source_ref(client, monkeypatch):
    _wire_suggest(monkeypatch, [_Cand(_FakeArc(owner=USER))])    # the caller owns it
    c, repo = client(GrantLevel.VIEW, structures=AsyncMock())
    r = c.post("/v1/composition/arc-templates/suggest", json={"project_id": str(uuid4()), "detail": "full"})
    assert r.json()["candidates"][0]["arc_template"]["source_ref"] == "secret-source"


def test_suggest_non_grantee_is_404(client, monkeypatch):
    _wire_suggest(monkeypatch, [])
    c, repo = client(GrantLevel.NONE, structures=AsyncMock())
    r = c.post("/v1/composition/arc-templates/suggest", json={"project_id": str(uuid4())})
    assert r.status_code == 404


# ── S-10 O6c: decompile REST twin — EDIT gate + deterministic engine passthrough ──


def test_decompile_non_grantee_is_404(client):
    c, _ = client(GrantLevel.NONE, structures=AsyncMock())
    r = c.post(f"/v1/composition/books/{BOOK}/arcs/decompile", json={})
    assert r.status_code == 404


def test_decompile_view_grantee_is_403(client):
    c, _ = client(GrantLevel.VIEW, structures=AsyncMock())
    r = c.post(f"/v1/composition/books/{BOOK}/arcs/decompile", json={"chapters_per_arc": 5})
    assert r.status_code == 403


def test_decompile_edit_runs_and_passes_through_the_engine_result(client, monkeypatch):
    seen: dict = {}

    async def _fake(pool, book_id, *, created_by, chapters_per_arc):
        seen.update(book_id=str(book_id), created_by=str(created_by), per=chapters_per_arc)
        return {"arcs": 3, "chapters_assigned": 24, "arc_ids": ["a1", "a2", "a3"]}

    monkeypatch.setattr("app.engine.arc_decompile.decompile_arcs", _fake)
    c, _ = client(GrantLevel.EDIT, structures=AsyncMock())
    r = c.post(f"/v1/composition/books/{BOOK}/arcs/decompile", json={"chapters_per_arc": 8})
    assert r.status_code == 200
    assert r.json() == {"arcs": 3, "chapters_assigned": 24, "arc_ids": ["a1", "a2", "a3"]}
    # the route threads the book, the acting caller as created_by, and the requested grouping.
    assert seen == {"book_id": str(BOOK), "created_by": str(USER), "per": 8}


def test_arc_public_drop_set_matches_the_mcp_twin():
    # The privacy allow-list is duplicated in arc.py + mcp/server.py `_arc_public_projection`.
    # Pin it here so a drift on either side is caught (they must stay identical).
    from app.routers.arc import _ARC_PUBLIC_DROP
    assert _ARC_PUBLIC_DROP == {
        "embedding", "embedding_model", "embedding_dim", "source_ref", "owner_user_id", "source_version",
    }


# ── D-ARC-TEMPLATE-BOOK-TIER: the route EDIT-gates a book_shared create/patch ──


def test_create_book_shared_requires_edit_on_the_book(client):
    from app.main import app
    from app.deps import get_arc_template_repo
    repo = AsyncMock()
    app.dependency_overrides[get_arc_template_repo] = lambda: repo
    try:
        c, _ = client(GrantLevel.NONE)   # no grant on the book
        r = c.post(
            f"/v1/composition/arc-templates?target=book_shared&book_id={BOOK}",
            json={"code": "shared.arc", "name": "Shared"},
        )
        assert r.status_code == 404          # gated (no oracle) BEFORE any write
        repo.create.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_arc_template_repo, None)


def test_create_book_shared_without_book_id_is_400(client):
    from app.main import app
    from app.deps import get_arc_template_repo
    repo = AsyncMock()
    app.dependency_overrides[get_arc_template_repo] = lambda: repo
    try:
        c, _ = client(GrantLevel.EDIT)
        r = c.post("/v1/composition/arc-templates?target=book_shared",
                   json={"code": "x", "name": "y"})
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "BOOK_ID_REQUIRED"
        repo.create.assert_not_called()
    finally:
        app.dependency_overrides.pop(get_arc_template_repo, None)


# ── read surface #1: the derived block MUST ride on every shell node ───────────


def test_arc_list_attaches_the_derived_block_to_every_node(client):
    repo = AsyncMock()
    repo.list_tree = AsyncMock(return_value=[_node(SAGA, kind="saga", title="Saga"), _node(ARC, parent_id=SAGA)])
    repo.derived_blocks = AsyncMock(return_value={
        SAGA: {"span": {"from_order": 1, "to_order": 7}, "is_contiguous": False, "chapter_count": 5},
        ARC: {"span": {"from_order": 1, "to_order": 3}, "is_contiguous": True, "chapter_count": 3},
    })
    c, _ = client(GrantLevel.VIEW, structures=repo)

    r = c.get(f"/v1/composition/books/{BOOK}/arcs")
    assert r.status_code == 200
    nodes = {n["id"]: n for n in r.json()["nodes"]}

    assert nodes[str(SAGA)]["span"] == {"from_order": 1, "to_order": 7}
    assert nodes[str(SAGA)]["is_contiguous"] is False
    assert nodes[str(SAGA)]["chapter_count"] == 5
    assert nodes[str(ARC)]["chapter_count"] == 3
    # The raw node fields are untouched — the block is ADDITIVE (the Chapter Browser shares
    # this route and reads only the raw fields).
    assert nodes[str(ARC)]["kind"] == "arc"
    assert nodes[str(ARC)]["parent_id"] == str(SAGA)


def test_arc_list_node_with_no_chapters_gets_the_empty_block_not_a_missing_key(client):
    # An arc absent from the derived map holds no chapters. It must still carry the block —
    # a MISSING key would make the FE read `undefined` and fall back to a wrong default
    # (`fe-status-default-fallback-signals-backend-field-omission`).
    repo = AsyncMock()
    repo.list_tree = AsyncMock(return_value=[_node(ARC)])
    repo.derived_blocks = AsyncMock(return_value={})
    c, _ = client(GrantLevel.VIEW, structures=repo)

    node = c.get(f"/v1/composition/books/{BOOK}/arcs").json()["nodes"][0]
    assert node["span"] is None
    assert node["is_contiguous"] is True
    assert node["chapter_count"] == 0
