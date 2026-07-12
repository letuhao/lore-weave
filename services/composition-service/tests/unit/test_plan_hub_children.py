"""24 Plan Hub v2 · H1.1/H1.4 — the book-keyed read surfaces (children + scene-links).

Covers, with a TestClient + fake repos (no DB — mirrors test_outline_children.py):
  • OQ-4 omitted-axis contract: exactly one of {structure_node_id, parent_id} is
    REQUIRED — neither / both → 400, and the repo is NEVER reached (so a
    parent_id-omitted / structure_node_id-absent call can never return chapter rows).
  • PH10 `detail=summary` projection shape (exact key set) + `detail=full` fallthrough.
  • PH23/PH10 present_entity_ids server-truncation to 3 + EXACT present_entity_count.
  • PH13/H1.4 book-keyed scene-links wire shape ({id,from,to,kind,label} only).

The live keyset SQL (rank COLLATE "C", the partial-index EXPLAIN) is exercised by the
DB-integration suite the orchestrator runs; here we pin the router contract + the pure
projection helper headless.
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.models import OutlineNode, SceneLink
from app.routers.outline import _encode_child_cursor, _summary_projection

USER = UUID("00000000-0000-0000-0000-0000000000aa")
PROJECT = UUID("00000000-0000-0000-0000-0000000000bb")
BOOK = UUID("00000000-0000-0000-0000-0000000000cc")

_SUMMARY_KEYS = {
    "id", "kind", "parent_id", "structure_node_id", "chapter_id", "title", "status",
    "version", "story_order", "rank", "beat_role", "tension", "pov_entity_id",
    "present_entity_ids", "present_entity_count",
    # SC11 amendment Phase 3 — the written verdict. PH10's field list is CLOSED, so this set IS
    # the contract: adding a field here is a deliberate amendment, and removing `written` by
    # accident turns this red instead of silently blanking the canvas's written/unwritten state.
    "written",
}


def _node(
    *,
    kind: str = "chapter",
    rank: str = "a0",
    nid: UUID | None = None,
    present: list[UUID] | None = None,
    structure_node_id: UUID | None = None,
    parent_id: UUID | None = None,
    chapter_id: UUID | None = None,
) -> OutlineNode:
    return OutlineNode.model_validate({
        "id": nid or uuid4(),
        "created_by": USER,
        "project_id": PROJECT,
        "book_id": BOOK,
        "kind": kind,
        "rank": rank,
        "title": "Ch",
        "status": "outline",
        "version": 2,
        "story_order": 3,
        "beat_role": "inciting" if kind == "scene" else None,
        "tension": 65,
        "pov_entity_id": uuid4(),
        "present_entity_ids": present if present is not None else [],
        "structure_node_id": structure_node_id,
        "parent_id": parent_id,
        # chapters/scenes need a chapter_id (outline_chapter_required), but the model
        # doesn't enforce it — keep it realistic anyway.
        "chapter_id": chapter_id or (uuid4() if kind in ("chapter", "scene") else None),
        # prose the summary projection must DROP:
        "synopsis": "a long synopsis that must never reach the canvas",
        "goal": "the chapter goal prose",
    })


def _link(kind: str = "setup_payoff", label: str = "", **anc) -> dict:
    """A raw `list_by_book` row. It is a DICT, not a SceneLink: the endpoint ancestry
    (`{from,to}_chapter_node_id` / `{from,to}_arc_id`) is a JOIN-derived projection, not a
    column of the row, so the repo returns the joined shape."""
    row = {
        "id": uuid4(),
        "created_by": USER,
        "project_id": PROJECT,
        "from_node_id": uuid4(),
        "to_node_id": uuid4(),
        "kind": kind,
        "label": label,
        "from_chapter_node_id": None,
        "to_chapter_node_id": None,
        "from_arc_id": None,
        "to_arc_id": None,
    }
    row.update(anc)
    return row


class _FakeOutline:
    def __init__(self, nodes: list[OutlineNode]) -> None:
        self.nodes = nodes
        self.structure_calls: list[dict] = []
        self.parent_calls: list[dict] = []
        self.unassigned_calls: list[dict] = []

    async def list_children_by_structure(self, book_id, structure_node_id, *, after=None, limit=100):
        self.structure_calls.append({
            "book_id": book_id, "structure_node_id": structure_node_id,
            "after": after, "limit": limit,
        })
        return self.nodes

    async def list_children_by_parent_book(self, book_id, parent_id, *, after=None, limit=100):
        self.parent_calls.append({
            "book_id": book_id, "parent_id": parent_id, "after": after, "limit": limit,
        })
        return self.nodes

    async def list_unassigned_chapters(self, book_id, *, after=None, limit=100):
        self.unassigned_calls.append({"book_id": book_id, "after": after, "limit": limit})
        return self.nodes

    @property
    def any_calls(self) -> list[dict]:
        return [*self.structure_calls, *self.parent_calls, *self.unassigned_calls]


class _FakeSceneLinks:
    def __init__(self, links: list[SceneLink]) -> None:
        self.links = links
        self.calls: list[UUID] = []

    async def list_by_book(self, book_id):
        self.calls.append(book_id)
        return self.links


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.main.create_pool", AsyncMock())
    monkeypatch.setattr("app.main.run_migrations", AsyncMock())
    monkeypatch.setattr("app.main.close_pool", AsyncMock())
    monkeypatch.setattr("app.main.get_pool", lambda: object())
    from app.main import app
    from app.deps import (get_grant_client_dep, get_outline_repo,
                          get_scene_links_repo)
    from app.grant_client import GrantLevel
    from app.middleware.jwt_auth import get_current_user

    # The book-keyed routes gate VIEW via authorize_book → grant.resolve_grant; a
    # stub at OWNER clears every read. No Work gate anywhere (PH9).
    class _StubGrant:
        async def resolve_grant(self, book_id, user_id):
            return GrantLevel.OWNER

    holder: dict = {"outline": None, "links": None}
    app.dependency_overrides[get_current_user] = lambda: USER
    app.dependency_overrides[get_outline_repo] = lambda: holder["outline"]
    app.dependency_overrides[get_scene_links_repo] = lambda: holder["links"]
    app.dependency_overrides[get_grant_client_dep] = lambda: _StubGrant()
    with TestClient(app) as c:
        yield c, holder
    app.dependency_overrides.clear()


# ── OQ-4 omitted-axis contract (must-400 / must-not-return-chapters) ─────────────

def test_neither_axis_is_400_and_never_hits_repo(client):
    c, holder = client
    repo = _FakeOutline([_node(kind="chapter")])
    holder["outline"] = repo
    r = c.get(f"/v1/composition/books/{BOOK}/outline/children")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "OUTLINE_CHILDREN_AXIS_REQUIRED"
    # the critical guard: an omitted-axis call NEVER reaches the repo, so it can
    # never return chapter-kind rows (the F-H1/OQ-4 root-semantics-flip bug).
    assert repo.any_calls == []


def test_both_axes_is_400(client):
    c, holder = client
    repo = _FakeOutline([_node(kind="chapter")])
    holder["outline"] = repo
    r = c.get(
        f"/v1/composition/books/{BOOK}/outline/children"
        f"?structure_node_id={uuid4()}&parent_id={uuid4()}"
    )
    assert r.status_code == 400
    assert repo.any_calls == []


# ── PH21 UNASSIGNED axis (arc-less chapters — the post-decompile state) ──────────

def test_unassigned_axis_serves_arcless_chapters(client):
    c, holder = client
    repo = _FakeOutline([_node(kind="chapter", structure_node_id=None)])
    holder["outline"] = repo
    r = c.get(f"/v1/composition/books/{BOOK}/outline/children?unassigned=true")
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1
    # it takes its OWN axis — neither sibling can reach an arc-less chapter.
    assert len(repo.unassigned_calls) == 1
    assert repo.unassigned_calls[0]["book_id"] == BOOK
    assert repo.structure_calls == [] and repo.parent_calls == []


def test_unassigned_is_still_exactly_one_axis(client):
    """`unassigned=true` is an EXPLICIT axis, not a modifier — combining it with another
    is the same 400 as naming two axes. This is what keeps OQ-4's "no silent whole-book
    fetch" law true as the axis count grows."""
    c, holder = client
    repo = _FakeOutline([_node(kind="chapter")])
    holder["outline"] = repo
    r = c.get(
        f"/v1/composition/books/{BOOK}/outline/children"
        f"?unassigned=true&structure_node_id={uuid4()}"
    )
    assert r.status_code == 400
    assert repo.any_calls == []


def test_unassigned_false_is_not_an_axis(client):
    """`unassigned=false` must not count as "an axis was given" — that would make a bare
    `?unassigned=false` a zero-axis call that somehow passed the guard."""
    c, holder = client
    repo = _FakeOutline([_node(kind="chapter")])
    holder["outline"] = repo
    r = c.get(f"/v1/composition/books/{BOOK}/outline/children?unassigned=false")
    assert r.status_code == 400
    assert repo.any_calls == []


# ── PH10 detail=summary projection ───────────────────────────────────────────────

def test_structure_axis_returns_summary_projection_shape(client):
    c, holder = client
    arc = uuid4()
    repo = _FakeOutline([_node(kind="chapter", structure_node_id=arc)])
    holder["outline"] = repo
    r = c.get(f"/v1/composition/books/{BOOK}/outline/children?structure_node_id={arc}")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    # exact key set — no prose (synopsis/goal) leaks onto the canvas wire (PH10).
    assert set(items[0].keys()) == _SUMMARY_KEYS
    assert "synopsis" not in items[0] and "goal" not in items[0]
    # the repo saw the ARC axis, book-scoped + clamped default limit.
    call = repo.structure_calls[0]
    assert call["structure_node_id"] == arc and call["book_id"] == BOOK
    assert call["limit"] == 100
    assert repo.parent_calls == []


def test_parent_axis_dispatches_to_scene_query(client):
    c, holder = client
    chapter = uuid4()
    repo = _FakeOutline([_node(kind="scene", parent_id=chapter)])
    holder["outline"] = repo
    r = c.get(f"/v1/composition/books/{BOOK}/outline/children?parent_id={chapter}")
    assert r.status_code == 200
    assert repo.parent_calls[0]["parent_id"] == chapter
    assert repo.parent_calls[0]["book_id"] == BOOK
    assert repo.structure_calls == []


def test_detail_full_returns_whole_node(client):
    c, holder = client
    arc = uuid4()
    holder["outline"] = _FakeOutline([_node(kind="chapter", structure_node_id=arc)])
    r = c.get(
        f"/v1/composition/books/{BOOK}/outline/children"
        f"?structure_node_id={arc}&detail=full"
    )
    assert r.status_code == 200
    item = r.json()["items"][0]
    # detail=full is the drawer's per-node payload → prose is present.
    assert "synopsis" in item and item["synopsis"].startswith("a long synopsis")


# ── PH23/PH10 present_entity truncation + exact count ────────────────────────────

def test_present_entities_truncated_to_three_count_exact_via_endpoint(client):
    c, holder = client
    arc = uuid4()
    five = [uuid4() for _ in range(5)]
    holder["outline"] = _FakeOutline([_node(kind="chapter", structure_node_id=arc, present=five)])
    r = c.get(f"/v1/composition/books/{BOOK}/outline/children?structure_node_id={arc}")
    item = r.json()["items"][0]
    assert len(item["present_entity_ids"]) == 3
    assert item["present_entity_ids"] == [str(e) for e in five[:3]]
    assert item["present_entity_count"] == 5  # EXACT full length, not the cap


def test_summary_projection_pure_helper():
    # headless unit of the pure projection: 2 present → no truncation, count 2.
    two = [uuid4(), uuid4()]
    proj = _summary_projection(_node(kind="chapter", present=two))
    assert set(proj.keys()) == _SUMMARY_KEYS
    assert proj["present_entity_ids"] == [str(e) for e in two]
    assert proj["present_entity_count"] == 2
    # 4 present → truncated to 3, count 4.
    four = [uuid4() for _ in range(4)]
    proj4 = _summary_projection(_node(kind="chapter", present=four))
    assert len(proj4["present_entity_ids"]) == 3
    assert proj4["present_entity_count"] == 4


# ── paging / cursor / clamp ──────────────────────────────────────────────────────

def test_next_cursor_trims_extra_row(client):
    c, holder = client
    arc = uuid4()
    # limit=3 → repo returns limit+1 rows; the endpoint trims + emits the cursor.
    nodes = [_node(kind="chapter", structure_node_id=arc, rank=f"a{i}", nid=uuid4()) for i in range(4)]
    holder["outline"] = _FakeOutline(nodes)
    r = c.get(
        f"/v1/composition/books/{BOOK}/outline/children?structure_node_id={arc}&limit=3"
    )
    body = r.json()
    assert len(body["items"]) == 3
    assert body["next_cursor"] is not None


def test_limit_clamped_to_200(client):
    c, holder = client
    arc = uuid4()
    repo = _FakeOutline([])
    holder["outline"] = repo
    c.get(f"/v1/composition/books/{BOOK}/outline/children?structure_node_id={arc}&limit=999")
    assert repo.structure_calls[0]["limit"] == 200


def test_bad_cursor_is_400(client):
    c, holder = client
    holder["outline"] = _FakeOutline([])
    r = c.get(
        f"/v1/composition/books/{BOOK}/outline/children"
        f"?structure_node_id={uuid4()}&cursor=%21%21bad"
    )
    assert r.status_code == 400


def test_cursor_decoded_and_passed_as_after(client):
    c, holder = client
    arc, nid = uuid4(), uuid4()
    repo = _FakeOutline([])
    holder["outline"] = repo
    cur = _encode_child_cursor("m5", nid)
    c.get(
        f"/v1/composition/books/{BOOK}/outline/children?structure_node_id={arc}&cursor={cur}"
    )
    assert repo.structure_calls[0]["after"] == ("m5", nid)


# ── PH13 / H1.4 book-keyed scene-links ───────────────────────────────────────────

def test_scene_links_book_wire_shape(client):
    c, holder = client
    links = [_link("setup_payoff", "seed"), _link("custom", "echo")]
    repo = _FakeSceneLinks(links)
    holder["links"] = repo
    r = c.get(f"/v1/composition/books/{BOOK}/scene-links")
    assert r.status_code == 200
    body = r.json()
    assert repo.calls == [BOOK]
    assert len(body["scene_links"]) == 2
    # exactly the PH13 wire keys — actor/scope columns stay off the canvas contract.
    for row in body["scene_links"]:
        assert set(row.keys()) == {
            "id", "from_node_id", "to_node_id", "kind", "label",
            "from_chapter_node_id", "to_chapter_node_id", "from_arc_id", "to_arc_id",
        }
    assert body["scene_links"][0]["kind"] == "setup_payoff"
    assert body["scene_links"][1]["label"] == "echo"


def test_scene_links_carry_endpoint_ancestry(client):
    """PH13's stub connectors are IMPOSSIBLE without this. A collapsed arc never loads its
    chapter window, so its scenes never arrive — the canvas cannot learn which lane an
    unloaded endpoint lives in, hands React Flow an edge naming a node that doesn't exist,
    and RF drops it silently. The ancestry is one join here and unknowable on the client."""
    c, holder = client
    chap, arc = uuid4(), uuid4()
    holder["links"] = _FakeSceneLinks([
        _link("setup_payoff", "", from_chapter_node_id=chap, from_arc_id=arc),
    ])
    row = c.get(f"/v1/composition/books/{BOOK}/scene-links").json()["scene_links"][0]
    assert row["from_chapter_node_id"] == str(chap)
    assert row["from_arc_id"] == str(arc)
    # a NULL endpoint stays null — the canvas must be able to tell "no lane" from a lane.
    assert row["to_arc_id"] is None


def test_scene_links_empty_book(client):
    c, holder = client
    holder["links"] = _FakeSceneLinks([])
    r = c.get(f"/v1/composition/books/{BOOK}/scene-links")
    assert r.status_code == 200
    assert r.json() == {"scene_links": []}


# ── SC11 amendment Phase 3 — the written verdict on the canvas payload ──────────────────────

def test_the_summary_payload_carries_the_WRITTEN_VERDICT():
    """The amendment's whole payoff, at the wire.

    `written` is a MAINTAINED column (reconciled from book-service's scenes.source_scene_id), so the
    canvas gets the verdict as a FIELD on a request it already makes — no sixth call, no client-side
    join, no page-walk of the scene index. PH9 caps the cold open at ≤5 requests; this REFUNDS one.
    """
    unwritten = _summary_projection(_node(kind="scene"))
    assert unwritten["written"] is False

    n = _node(kind="scene")
    n.written_scene_id = uuid4()
    assert _summary_projection(n)["written"] is True


def test_the_canvas_gets_a_BOOL_never_the_scene_id():
    """PH10's discipline is "L1 refs and badge scalars, never content". The canvas renders a STATE;
    shipping the manuscript's scene id onto a payload that paints thousands of nodes would put a
    foreign identifier on the hot wire for no one to use. The drawer's `detail=full` fetch carries
    the id for the ONE node that needs it."""
    n = _node(kind="scene")
    n.written_scene_id = uuid4()
    proj = _summary_projection(n)
    assert proj["written"] is True
    assert "written_scene_id" not in proj
    assert "written_at" not in proj


def test_written_is_INDEPENDENT_of_status():
    """PH16 locks a two-chip desired-vs-actual header, and this is why. `status` is the AUTHOR'S
    INTENT; `written` is a manuscript FACT. An author marking a scene 'done' must NOT make an
    unwritten scene render as written — that is the drift bug BPS-3 deleted structure_node.pacing
    to prevent."""
    n = _node(kind="scene")
    n.status = "done"           # the author says it is done…
    n.written_scene_id = None   # …but no prose exists
    proj = _summary_projection(n)
    assert proj["status"] == "done"
    assert proj["written"] is False, "author intent leaked into a manuscript fact"
