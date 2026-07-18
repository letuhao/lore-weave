"""Outline + Scene-Graph router (§5) — tree, nodes, scene-links.

Reuses the M2 OutlineRepo / SceneLinksRepo (incl. the M2-closure ownership +
reparent-cycle guards, which surface as ReferenceViolationError → 400 here, and
If-Match VersionMismatchError → 412). Access is the E0 book grant (25 PM-8):
the /works/{project_id}/* routes resolve the Work by project and gate the
caller's grant on its book (VIEW for reads, EDIT for writes) BEFORE any repo
call; by-id routes resolve the target row's scope first and gate on ITS book.
"""

from __future__ import annotations

import base64
from typing import Any, Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from loreweave_mcp.errors import NOT_ACCESSIBLE_MESSAGE

from app.config import settings
from app.db.models import LinkKind, NodeKind, NodeStatus
from app.db.pool import get_pool
from app.db.repositories import ReferenceViolationError, VersionMismatchError
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.scene_links import SceneLinksRepo
from app.db.repositories.works import WorksRepo
from app.deps import (get_grant_client_dep, get_outline_repo,
                      get_scene_links_repo, get_works_repo)
from app.engine.scene_decompile import (BookSceneFetchError, fetch_book_scenes,
                                        materialize_scenes, resolve_canonical_work)
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.mcp.service_bearer import mint_service_bearer
from app.middleware.internal_auth import require_internal_token
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.packer.pack import OwnershipError

router = APIRouter(prefix="/v1/composition")

# SC6/B4 — the decompiler's internal-token surface. A separate router (its path is
# `/internal/...`, not the `/v1/composition` public prefix); wired in main.py
# alongside the public `router`.
internal_router = APIRouter(
    prefix="/internal/books",
    tags=["internal"],
    dependencies=[Depends(require_internal_token)],
)


class NodeCreate(BaseModel):
    kind: NodeKind
    parent_id: UUID | None = None
    rank: str | None = None
    title: str = ""
    pov_entity_id: UUID | None = None
    present_entity_ids: list[UUID] = []
    goal: str = ""
    beat_role: str | None = None
    status: NodeStatus = "empty"
    chapter_id: UUID | None = None
    tension: int | None = None
    story_order: int | None = None
    synopsis: str = ""
    # 22 SC4 — authored scene craft/setting. These MUST be declared: Pydantic's default
    # extra='ignore' silently drops an undeclared key, so a REST create sending `conflict`/
    # `target_words`/`location_entity_id` would no-op while the MCP tool (which HAS them) works —
    # the "one repo method, two front doors" divergence (CF-9). `exit_state` stays MCP-only
    # (SC12 mandates a validated envelope, not a free-form REST blob).
    location_entity_id: UUID | None = None
    story_time: str | None = None
    conflict: str = ""
    outcome: str = ""
    stakes: str = ""
    value_shift: int | None = None
    target_words: int | None = None


class NodePatch(BaseModel):
    parent_id: UUID | None = None
    rank: str | None = None
    title: str | None = None
    pov_entity_id: UUID | None = None
    present_entity_ids: list[UUID] | None = None
    goal: str | None = None
    beat_role: str | None = None
    status: NodeStatus | None = None
    chapter_id: UUID | None = None
    tension: int | None = None
    story_order: int | None = None
    synopsis: str | None = None
    # 22 SC4 — the scene-inspector's Craft + Cast&Setting edits and the bulk retarget-words go
    # through THIS model; without these declarations they were silently dropped (extra='ignore')
    # and the GUI edit no-op'd. The repo's _UPDATABLE_COLUMNS already writes them; only the REST
    # mirror lagged. `exit_state` intentionally omitted (SC12 validated-envelope → MCP surface).
    location_entity_id: UUID | None = None
    story_time: str | None = None
    conflict: str | None = None
    outcome: str | None = None
    stakes: str | None = None
    value_shift: int | None = None
    target_words: int | None = None


class NodeReorder(BaseModel):
    new_parent_id: UUID | None = None  # None = move to top level (arcs)
    after_id: UUID | None = None       # the sibling to place AFTER; None = first child


class SceneLinkCreate(BaseModel):
    from_node_id: UUID
    to_node_id: UUID
    kind: LinkKind = "setup_payoff"   # Literal → bad value is 422, not a 500 CheckViolation
    label: str = ""


def _parse_if_match(if_match: str | None) -> int | None:
    if if_match is None:
        return None
    try:
        return int(if_match.strip().strip('"'))
    except ValueError:
        raise HTTPException(status_code=400, detail="If-Match must be an integer version")


async def _gate_book(grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel) -> None:
    """E0-4c book-grant chokepoint → HTTP (mirrors works._gate_book). none→404
    (no oracle), under-tier→403. The 404 uses the SAME uniform detail as every
    other not-found/not-accessible branch in this router (the MCP
    `uniform_not_accessible()` H13 message) so a by-id gate can't leak existence:
    "this row exists but isn't yours" reads identically to "no such row"."""
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


async def _require_work(
    works: WorksRepo, grant: GrantClient, user_id: UUID, project_id: UUID,
    need: GrantLevel,
) -> None:
    """Resolve the Work by project (un-user-scoped — 25 PM-9) and gate the
    caller's E0 grant on its book (PM-8: access is decided HERE, never in the
    repos — the repos no longer filter on the actor)."""
    work = await works.get(project_id)
    if work is None:
        # Uniform with the no-grant branch below (and every by-id gate) so a
        # missing project can't be told apart from an unauthorized one.
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    await _gate_book(grant, work.book_id, user_id, need)


async def _gate_node(
    outline: OutlineRepo, works: WorksRepo, grant: GrantClient,
    user_id: UUID, node_id: UUID, need: GrantLevel,
) -> None:
    """By-id routes: resolve the target node's scope from the ROW ITSELF, then
    gate the caller's grant on that book (`worker-loaded-id-needs-parent-scoping`
    — the gate can never check a different book than the row mutated).

    `get_node` is a bare-id read (no scope filter), so a node the caller may not
    see still resolves here — the grant is what gates. A missing node therefore
    returns the SAME uniform detail as a node the caller lacks a grant on (the
    MCP `uniform_not_accessible()` H13 message), never a distinct 'node not
    found' that would confirm the id exists."""
    node = await outline.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    await _require_work(works, grant, user_id, node.project_id, need)


@router.get("/works/{project_id}/outline")
async def get_outline(
    project_id: UUID,
    include_archived: bool = False,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    scene_links: SceneLinksRepo = Depends(get_scene_links_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    await _require_work(works, grant, user_id, project_id, GrantLevel.VIEW)
    nodes = await outline.list_tree(project_id, include_archived=include_archived)
    links = await scene_links.list_by_project(project_id)
    return {
        "nodes": [n.model_dump(mode="json") for n in nodes],
        "scene_links": [l.model_dump(mode="json") for l in links],
    }


def _encode_child_cursor(rank: str, node_id: UUID) -> str:
    """Opaque keyset cursor for the lazy-children endpoint: (rank, id). id is a UUID
    with no '|', so rpartition('|') recovers it even if a rank ever contained '|'."""
    return base64.urlsafe_b64encode(f"{rank}|{node_id}".encode()).decode()


def _decode_child_cursor(cursor: str) -> tuple[str, UUID]:
    """Decode a token from _encode_child_cursor. Malformed → 400 (never a silent
    reset to page 1, which would loop the client)."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        rank, sep, id_str = raw.rpartition("|")
        if not sep or not rank or not id_str:
            raise ValueError("missing separator")
        return rank, UUID(id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid cursor") from None


@router.get("/works/{project_id}/outline/children")
async def list_outline_children(
    project_id: UUID,
    parent_id: UUID | None = None,
    cursor: str | None = None,
    limit: int = 100,
    include_archived: bool = False,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Lazy-tree primitive for the manuscript navigator (#02): the direct children of
    `parent_id` (omitted → top-level arcs), keyset-paged by (rank, id). Fetch one level
    a page at a time so a 10k-chapter outline scales like the book-service chapter spine
    instead of the whole-tree `GET /outline`. Response: {items, next_cursor}."""
    await _require_work(works, grant, user_id, project_id, GrantLevel.VIEW)
    limit = max(1, min(limit, 200))
    after = _decode_child_cursor(cursor) if cursor else None
    nodes = await outline.list_children(
        project_id, parent_id,
        after=after, limit=limit, include_archived=include_archived,
    )
    next_cursor: str | None = None
    if len(nodes) > limit:
        nodes = nodes[:limit]
        last = nodes[-1]
        next_cursor = _encode_child_cursor(last.rank, last.id)
    return {
        "items": [n.model_dump(mode="json") for n in nodes],
        "next_cursor": next_cursor,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 24 Plan Hub v2 (H1) — the BOOK-KEYED read surfaces (BPS-8: keyed on book_id, gated
# VIEW on the book — NO Work gate, PH9). Distinct from the /works/{project_id}/*
# routes above: the Hub renders the whole package on the graph canvas and never
# resolves a Work (BPS-1/BA8). These are canvas reads, so the children route ships a
# `detail=summary` L1-ref projection (PH10) — prose (goal/synopsis) never reaches the
# canvas; the drawer's per-node full fetch loads it on selection.
# ══════════════════════════════════════════════════════════════════════════════

# PH23 chip cap — the canvas paints at most 3 cast chips; the wire mirrors that cap
# (a COUNT can render "+N", never a chip — so the first 3 ids ship too, PH10).
_PRESENT_ENTITY_CAP = 3

_ChildDetail = Literal["summary", "full"]


def _summary_projection(node: Any) -> dict[str, Any]:
    """PH10 canvas node payload = L1 ref + badge scalars; prose NEVER ships to the
    canvas (the 146K-token `composition_list_outline` lesson applied to the GUI wire —
    a canvas renders thousands of nodes, the drawer renders one). `present_entity_ids`
    is server-truncated to the first `_PRESENT_ENTITY_CAP` (the PH23 chip cap mirrored
    on the wire); `present_entity_count` stays EXACT (the full roster length) so the
    canvas can render a `+N` overflow. Pure over an OutlineNode → unit-testable
    headless."""
    present = list(node.present_entity_ids or [])
    return {
        "id": str(node.id),
        "kind": node.kind,
        "parent_id": str(node.parent_id) if node.parent_id else None,
        "structure_node_id": str(node.structure_node_id) if node.structure_node_id else None,
        "chapter_id": str(node.chapter_id) if node.chapter_id else None,
        "title": node.title,
        "status": node.status,
        "version": node.version,
        "story_order": node.story_order,
        "rank": node.rank,
        "beat_role": node.beat_role,
        "tension": node.tension,
        "pov_entity_id": str(node.pov_entity_id) if node.pov_entity_id else None,
        "present_entity_ids": [str(e) for e in present[:_PRESENT_ENTITY_CAP]],
        "present_entity_count": len(present),
        # AUTHORSHIP (Plan Hub redesign) — 'authored' (human) vs 'mined' (decompiler). It is the
        # sealed design's type/colour semantic (Lora+amber vs Mono+teal) and maps to this exact
        # column (`OutlineNode.source`; the decompiler never overwrites 'authored'). Additive scalar
        # on a request the Hub already makes — no new call, PH10 budget unaffected.
        "source": node.source,
        # ── SC11 amendment Phase 3 — the WRITTEN VERDICT rides the payload it already sends ──
        #
        # PH10's field list is CLOSED, so this is a deliberate amendment to it, and the reason it
        # is admissible is that it costs NOTHING at the read budget: it is a field on a request the
        # Hub already makes, not a sixth call. PH9 caps the cold open at ≤5 requests; this REFUNDS
        # one — `useActualState` used to page book-service's scene index per loaded chapter, and
        # that read is now gone entirely.
        #
        # A BOOL, not the scene id. The canvas renders a state, not a link: shipping the id would
        # put a manuscript identifier on a payload whose whole discipline (PH10) is "L1 refs and
        # badge scalars, never content". The drawer's `detail=full` fetch carries the id for the
        # one node that needs it.
        #
        # `written_scene_id` is a MAINTAINED COLUMN (Phase 1), not a join — so this is not the
        # cross-service read SC11 forbids. It is a column read, and it is the whole point of the
        # amendment: the fact is derived ONCE, on write, by the service that already knows it.
        "written": node.written_scene_id is not None,
    }


@router.get("/books/{book_id}/outline/children")
async def list_book_outline_children(
    book_id: UUID,
    structure_node_id: UUID | None = None,
    parent_id: UUID | None = None,
    unassigned: bool = False,
    cursor: str | None = None,
    limit: int = 100,
    detail: _ChildDetail = "summary",
    user_id: UUID = Depends(get_current_user),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """24 H1.1 — the Plan Hub's lazy children window, keyed on `book_id` (PH9/PH11).
    THREE axes, MUTUALLY EXCLUSIVE and exactly one REQUIRED (OQ-4, critical):

      • `structure_node_id` — the ARC axis: the chapters attached to an arc
        (`structure_node`). After the 25 M4 lift chapters carry `parent_id NULL`, so an
        omitted parent MUST NOT be read as "top-level" — that would return every chapter
        in the book. There is NO "omitted = all chapters" behavior anywhere here.
      • `parent_id` — the CHAPTER axis: the scenes under a chapter node.
      • `unassigned=true` — the UNASSIGNED axis (24 PH21): chapter nodes bound to NO arc
        (`structure_node_id IS NULL`). Neither other axis can reach these — the arc axis
        needs an arc and the parent axis needs a `parent_id` the M4 lift nulled — yet they
        are the NORMAL post-decompile state (`materialize-scenes` mints chapters with no
        arc; grouping them is the separate LLM step). Without this axis a freshly
        extracted plan renders as an empty canvas.

    Zero axes, or more than one, → 400 (never a silent whole-book fetch). Note
    `unassigned=true` is an EXPLICIT, named axis — the OQ-4 law it respects is "no silent
    whole-book fetch", and this returns only the arc-less subset, keyset-paged.

    Keyset-paged by (rank, id) via the shared opaque cursor codec (malformed → 400, never
    a page-1 reset); limit clamped 1..200. `detail=summary` (default) ships the PH10 L1-ref
    projection — prose stays off the canvas; `detail=full` returns the whole node (the
    drawer's per-node fetch). Gates VIEW on the book (BPS-8) BEFORE the repo."""
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    # Exactly one axis. Counting beats the old pairwise `(a is None) == (b is None)` — it
    # stays correct as axes are added, and it still guarantees the contract test's core
    # claim: a call naming NO axis can never return chapter-kind rows (it never reaches
    # the repo), so there is no path to a whole-book fetch.
    axes = sum([structure_node_id is not None, parent_id is not None, unassigned])
    if axes != 1:
        raise HTTPException(status_code=400, detail={
            "code": "OUTLINE_CHILDREN_AXIS_REQUIRED",
            "detail": "exactly one of structure_node_id (arc axis), parent_id "
                      "(chapter axis), or unassigned=true (arc-less chapters) is required",
        })
    limit = max(1, min(limit, 200))
    after = _decode_child_cursor(cursor) if cursor else None
    if structure_node_id is not None:
        nodes = await outline.list_children_by_structure(
            book_id, structure_node_id, after=after, limit=limit,
        )
    elif unassigned:
        nodes = await outline.list_unassigned_chapters(book_id, after=after, limit=limit)
    else:
        assert parent_id is not None  # exclusivity guard above guarantees it
        nodes = await outline.list_children_by_parent_book(
            book_id, parent_id, after=after, limit=limit,
        )
    next_cursor: str | None = None
    if len(nodes) > limit:
        nodes = nodes[:limit]
        last = nodes[-1]
        next_cursor = _encode_child_cursor(last.rank, last.id)
    if detail == "full":
        items = [n.model_dump(mode="json") for n in nodes]
    else:
        items = [_summary_projection(n) for n in nodes]
    return {"items": items, "next_cursor": next_cursor}


@router.get("/books/{book_id}/scene-links")
async def list_book_scene_links(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user),
    scene_links: SceneLinksRepo = Depends(get_scene_links_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """24 H1.4 / PH13 — every scene-link edge of the book in one call (read surface #4:
    the graph canvas's native edges). Sparse by design (F-H7), so a whole-book fetch is
    cheap. Gates VIEW on the book (BPS-8) BEFORE the repo.

    Wire shape `{id, from_node_id, to_node_id, kind, label}` PLUS each endpoint's ANCESTRY
    (`{from,to}_chapter_node_id`, `{from,to}_arc_id`). The actor/scope columns
    (`created_by`/`project_id`/`created_at`) stay off the canvas contract.

    The ancestry is what makes PH13's stub connectors possible AT ALL. An edge into a
    COLLAPSED arc has an endpoint the client never loaded (a collapsed arc doesn't fetch
    its chapter window, so its scenes never arrive) — so the canvas cannot know which lane
    to draw the stub into, hands React Flow an edge naming a node that doesn't exist, and
    RF drops it silently. That is the exact failure PH13 forbids. One join here; unknowable
    on the client.
    """
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    links = await scene_links.list_by_book(book_id)

    def _opt(v: Any) -> str | None:
        return str(v) if v is not None else None

    return {
        "scene_links": [
            {
                "id": str(link["id"]),
                "from_node_id": str(link["from_node_id"]),
                "to_node_id": str(link["to_node_id"]),
                "kind": link["kind"],
                "label": link["label"],
                # Ancestry — NULL when the endpoint node is gone or unparented. The canvas
                # then has no lane to stub into and counts the edge as unresolvable rather
                # than pretending it isn't there.
                "from_chapter_node_id": _opt(link.get("from_chapter_node_id")),
                "to_chapter_node_id": _opt(link.get("to_chapter_node_id")),
                "from_arc_id": _opt(link.get("from_arc_id")),
                "to_arc_id": _opt(link.get("to_arc_id")),
            }
            for link in links
        ]
    }


@router.get("/works/{project_id}/chapters/{chapter_id}/scenes")
async def list_chapter_scenes(
    project_id: UUID,
    chapter_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Studio #12 cycle-1 — the active scene nodes of one BOOK chapter in reading
    order (the manuscript-unit document's `scenes[]` source). Thin wrapper over the
    same `scenes_for_chapter` the assembly path uses, so the editor and the composer
    read one ordering. M-G: also returns `chapter_node_id` (the outline chapter node
    scenes parent under — the rail's Create needs it when the chapter has 0 scenes;
    null when the chapter was never outlined)."""
    await _require_work(works, grant, user_id, project_id, GrantLevel.VIEW)
    scenes = await outline.scenes_for_chapter(project_id, chapter_id)
    node_id = await outline.chapter_node_id(project_id, chapter_id)
    return {
        "items": [n.model_dump(mode="json") for n in scenes],
        "chapter_node_id": str(node_id) if node_id else None,
    }


@router.get("/works/{project_id}/outline/search")
async def search_outline(
    project_id: UUID,
    q: str = "",
    limit: int = 30,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Manuscript jump/search (#02 nav jump box + #06a Quick Open): title substring match
    across the WHOLE outline (arc/chapter/scene), not just the lazy-loaded tree window.
    Empty query → no items (the client shows the tree instead). Response: {items} where each
    item is {id, kind, title, chapter_id, status, story_order, path[]}."""
    await _require_work(works, grant, user_id, project_id, GrantLevel.VIEW)
    q = q.strip()
    if not q:
        return {"items": []}
    limit = max(1, min(limit, 50))
    items = await outline.search_nodes(project_id, q, limit=limit)
    return {"items": items}


@router.get("/works/{project_id}/outline/stats")
async def outline_stats(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, int]:
    """Whole-book totals for the navigator footer: {arcs, chapters, scenes} (non-archived).
    Not derivable from the lazy-loaded tree window — a single GROUP BY over the outline."""
    await _require_work(works, grant, user_id, project_id, GrantLevel.VIEW)
    return await outline.outline_stats(project_id)


@router.get("/works/{project_id}/chapters/{chapter_id}/publish-gate")
async def get_publish_gate(
    project_id: UUID,
    chapter_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """M9 chapter-gate: is the chapter publishable? `can_publish` is True only
    when ALL the chapter's composition scenes are status='done' (OI-1 — no
    unreviewed scene canonized). The FE gates the (CM-FE) Publish affordance on
    this. Gates the book grant (VIEW) first."""
    await _require_work(works, grant, user_id, project_id, GrantLevel.VIEW)
    return await outline.chapter_scene_gate(project_id, chapter_id)


@router.get("/works/{project_id}/canon-issues")
async def get_canon_issues(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Studio Quality tab (`quality-canon` panel): every scene in the book whose
    latest completed auto-generation left a CONFIRMED canon contradiction —
    itemized, not the `publish-gate`'s per-chapter count. Gates the book grant
    (VIEW) first."""
    await _require_work(works, grant, user_id, project_id, GrantLevel.VIEW)
    items = await outline.canon_issues(project_id)
    return {"items": items}


@router.get("/works/{project_id}/rule-violations")
async def get_rule_violations(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Studio Quality tab (`quality-canon` panel): every open violation of an
    author-declared CANON RULE, as judged by the critic — the lane that carries a
    `rule_id`, which is what the Plan Hub's canon badge deep-links on (24 PH18).

    DELIBERATELY a separate route from `/canon-issues`, not a second key on it:
    that endpoint is the ENTITY-continuity lane and carries no rule id. Two
    engines, two verdicts, two names — conflating them is what made the deep-link
    look impossible. Gates the book grant (VIEW) first.

    Bounded at `RULE_VIOLATIONS_CAP` with an EXACT `count` + a `capped` flag, so a
    truncation is never silent (OUT-5)."""
    await _require_work(works, grant, user_id, project_id, GrantLevel.VIEW)
    return await outline.rule_violations(project_id)


@router.post("/works/{project_id}/outline/nodes", status_code=201)
async def create_node(
    project_id: UUID,
    body: NodeCreate,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    try:
        node = await outline.create_node(
            project_id, kind=body.kind, parent_id=body.parent_id, rank=body.rank,
            title=body.title, pov_entity_id=body.pov_entity_id,
            present_entity_ids=body.present_entity_ids, goal=body.goal,
            beat_role=body.beat_role, status=body.status, chapter_id=body.chapter_id,
            tension=body.tension, story_order=body.story_order, synopsis=body.synopsis,
            # 22 SC4 — pass the craft/setting fields the REST mirror now accepts.
            location_entity_id=body.location_entity_id, story_time=body.story_time,
            conflict=body.conflict, outcome=body.outcome, stakes=body.stakes,
            value_shift=body.value_shift, target_words=body.target_words,
            created_by=user_id,
        )
    except ReferenceViolationError as exc:
        raise HTTPException(status_code=400, detail={"code": "BAD_REFERENCE", "detail": exc.message})
    except asyncpg.CheckViolationError as exc:
        raise HTTPException(status_code=400, detail={"code": "CONSTRAINT", "detail": str(exc)})
    return node.model_dump(mode="json")


@router.get("/outline/nodes/{node_id}")
async def get_node(
    node_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """22-C3 — the single-node read the scene-inspector needs (a detail-over-selection
    pane, SC10). VIEW-gated; the REST mirror of the MCP `composition_get_outline_node`
    (one repo method, two front doors — 23 Phase B). Scope is derived from the ROW, and a
    missing node returns the same uniform 404 as one the caller lacks a grant on."""
    await _gate_node(outline, works, grant, user_id, node_id, GrantLevel.VIEW)
    node = await outline.get_node(node_id)
    if node is None:  # raced with a delete between the gate and the read
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    return node.model_dump(mode="json")


@router.patch("/outline/nodes/{node_id}")
async def patch_node(
    node_id: UUID,
    body: NodePatch,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    await _gate_node(outline, works, grant, user_id, node_id, GrantLevel.EDIT)
    patch = body.model_dump(exclude_unset=True)
    expected_version = _parse_if_match(if_match)
    # A scene committing (status → 'done') routes through the commit-aware path,
    # which emits composition.scene_committed atomically with the status write
    # (M9 / §3.1). Every other patch keeps the plain self-acquiring update.
    try:
        if patch.get("status") == "done":
            node = await outline.update_node_commit_aware(
                node_id, patch, expected_version=expected_version,
            )
        else:
            node = await outline.update_node(
                node_id, patch, expected_version=expected_version,
            )
    except VersionMismatchError as exc:
        raise HTTPException(status_code=412, detail={"code": "NODE_VERSION_CONFLICT",
                                                     "current": exc.current.model_dump(mode="json")})
    except ReferenceViolationError as exc:
        raise HTTPException(status_code=400, detail={"code": "BAD_REFERENCE", "detail": exc.message})
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    return node.model_dump(mode="json")


@router.delete("/outline/nodes/{node_id}", status_code=200)
async def delete_node(
    node_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    await _gate_node(outline, works, grant, user_id, node_id, GrantLevel.EDIT)
    node = await outline.archive_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    return node.model_dump(mode="json")


@router.post("/outline/nodes/{node_id}/restore", status_code=200)
async def restore_node(
    node_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """T1.1b — un-archive a node (inverse of DELETE). Restores the node's archived
    subtree + archived ancestor chain so it reconnects to a visible root. 404 if
    the node doesn't exist / isn't grant-visible / wasn't archived."""
    await _gate_node(outline, works, grant, user_id, node_id, GrantLevel.EDIT)
    node = await outline.restore_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found or not archived")
    return node.model_dump(mode="json")


@router.post("/outline/nodes/{node_id}/reorder")
async def reorder_node(
    node_id: UUID,
    body: NodeReorder,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    """T1.1c — drag-reorder + reparent: place `node_id` under `new_parent_id`
    after `after_id` (None = first child). Computes the fractional rank +
    renumbers scene story_order server-side (atomic). 412 NODE_VERSION_CONFLICT on
    a stale If-Match; 400 BAD_REFERENCE on a reparent cycle / cross-scope parent /
    bad after_id."""
    await _gate_node(outline, works, grant, user_id, node_id, GrantLevel.EDIT)
    expected_version = _parse_if_match(if_match)
    try:
        node = await outline.reorder_node(
            node_id,
            new_parent_id=body.new_parent_id, after_id=body.after_id,
            expected_version=expected_version,
        )
    except VersionMismatchError as exc:
        raise HTTPException(status_code=412, detail={"code": "NODE_VERSION_CONFLICT",
                                                     "current": exc.current.model_dump(mode="json")})
    except ReferenceViolationError as exc:
        raise HTTPException(status_code=400, detail={"code": "BAD_REFERENCE", "detail": exc.message})
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    return node.model_dump(mode="json")


@router.post("/works/{project_id}/scene-links", status_code=201)
async def create_scene_link(
    project_id: UUID,
    body: SceneLinkCreate,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    scene_links: SceneLinksRepo = Depends(get_scene_links_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    try:
        link = await scene_links.create(project_id, body.from_node_id, body.to_node_id,
                                        kind=body.kind, label=body.label,
                                        created_by=user_id)
    except ReferenceViolationError as exc:
        raise HTTPException(status_code=400, detail={"code": "BAD_REFERENCE", "detail": exc.message})
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail={"code": "SCENE_LINK_EXISTS"})
    return link.model_dump(mode="json")


@router.post("/books/{book_id}/scene-links", status_code=201)
async def create_book_scene_link(
    book_id: UUID,
    body: SceneLinkCreate,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    scene_links: SceneLinksRepo = Depends(get_scene_links_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """24 PH20 Row-5 — draw a scene-link edge on the canvas (the BOOK-keyed create).

    The Work-keyed sibling above cannot serve the Hub: PH9 is explicit that the Hub keys
    on `book_id` and has **no Work gate anywhere**, so it never holds a `project_id` to
    put in that path. Same repo method, two front doors (PH20/F-H3) — this one resolves
    the book's CANONICAL Work itself (`source_work_id IS NULL`; derivatives are branches
    of the spec, 23 BA8) and gates EDIT on the book (BPS-8).

    Tenancy is the repo's own guard: both endpoints must be nodes of the resolved Work,
    so an EDIT grant on this book can never link a node belonging to another one.
    """
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    # `resolve_by_book` EXCLUDES the lazy/pending Work (`AND NOT pending_project_backfill`), so
    # the canonical lookup alone can never see one. The decompiler already falls back to it —
    # `materialize-scenes` during a knowledge outage mints its nodes under a PENDING Work — and
    # those nodes render on the canvas perfectly well. Without the same fallback here, drawing an
    # edge between two of them would 409 "this book has no plan yet" while the plan is on screen.
    work = resolve_canonical_work(await works.resolve_by_book(book_id))
    if work is None:
        work = await works.get_pending_for_book(book_id)
    if work is None:
        # Genuinely no Work ⇒ there is no spec to link INTO. Say so; a 500 or a silent empty
        # would both be lies (the book may simply never have been planned).
        raise HTTPException(status_code=409, detail={
            "code": "NO_CANONICAL_WORK",
            "detail": "this book has no plan yet — extract or create one before linking scenes",
        })
    # A pending Work carries a NULL project_id and is addressed by its surrogate id (C16, the same
    # fallback `create_node` uses). This branch is now REACHABLE — before the fallback above it was
    # dead code with a comment describing a case it could never see.
    scope = work.project_id or work.id
    try:
        link = await scene_links.create(
            scope, body.from_node_id, body.to_node_id,
            kind=body.kind, label=body.label, created_by=user_id,
        )
    except ReferenceViolationError as exc:
        raise HTTPException(status_code=400, detail={"code": "BAD_REFERENCE", "detail": exc.message})
    except asyncpg.UniqueViolationError:
        # UNIQUE(from,to,kind) — the edge already exists. Not an error the user can act on
        # differently, but it must not read as "created".
        raise HTTPException(status_code=409, detail={"code": "SCENE_LINK_EXISTS"})
    return link.model_dump(mode="json")


@router.delete("/scene-links/{link_id}", status_code=204)
async def delete_scene_link(
    link_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    scene_links: SceneLinksRepo = Depends(get_scene_links_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> None:
    # By-id route (`/scene-links/{link_id}` has no project in the path): resolve
    # the edge's scope from the ROW ITSELF via an ids-only read (PM-8 scope-
    # bootstrap, mirrors works.scope_meta's anti-oracle), gate the caller's grant
    # on ITS book, then delete under the same project constraint (the gate and
    # the mutation can never target different books).
    row = await get_pool().fetchrow(
        "SELECT project_id FROM scene_link WHERE id = $1", link_id,
    )
    if row is None:
        # Same uniform detail as the no-grant branch (_require_work below): a
        # by-id existence probe must not distinguish "no such link" from
        # "exists but not yours".
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    await _require_work(works, grant, user_id, row["project_id"], GrantLevel.EDIT)
    if not await scene_links.delete(row["project_id"], link_id):
        # Post-authorization (the caller cleared the EDIT grant above): a benign
        # race where the row vanished — keep the specific, non-leaking message.
        raise HTTPException(status_code=404, detail="scene-link not found")


# ─────────────────────────────────────────────────────────────────────────────
# 22 SC6 / B4 — the SCENE DECOMPILER (materialize-scenes).
#
# After a book is parsed, `book-service.scenes` is the INDEX (parse leaves) and the
# durable SPEC is `outline_node`. This upserts one kind='scene' spec node per parse
# leaf, keyed on the BOOK (23 BA8 — Per-book, no Work required conceptually; in the
# current schema it resolves the book's canonical Work to host the nodes and guards
# a Work-less book gracefully). Idempotent per `scene_decompile.materialize_scenes`.
#
# Two transports over ONE core:
#   • POST /internal/books/{book_id}/materialize-scenes — the import tail / worker-
#     infra (internal token). Mints a short-lived service bearer for the asserted
#     owner to read book-service's VIEW-gated scene list (the service_bearer seam).
#   • POST /v1/composition/books/{book_id}/materialize-scenes — the Hub's "Extract
#     the plan" CTA (24 OQ-9): a human GUI can call neither an internal-token route
#     nor an MCP tool. EDIT-gated; the caller's own bearer reads the scene list.
#     Plain scene materialization is DETERMINISTIC ($0, no LLM) — so this /v1 mirror
#     is a direct EDIT-gated call, NOT a propose→confirm priced endpoint (the LLM
#     arc-analysis decompiler is the separate Tier-W tool that reuses that pattern).
# ─────────────────────────────────────────────────────────────────────────────


class MaterializeScenesRequest(BaseModel):
    # The asserted acting principal (the book owner the import tail verified) — used
    # BOTH as the actor stamp on minted nodes AND as the `sub` of the short-lived
    # service bearer that reads book-service's VIEW-gated scene list. book-service
    # re-enforces the grant on that sub, so a wrong id can only ever reach that
    # user's OWN books (service_bearer.py rationale).
    owner_user_id: UUID


def _map_scene_fetch_error(exc: BookSceneFetchError) -> HTTPException:
    """book-service scene-read failure → HTTP. A partial read would understate the
    scene count and mask the silent-success guard, so this fails loud (never a
    best-effort empty)."""
    return HTTPException(
        status_code=502,
        detail={"code": "BOOK_SCENE_READ_FAILED",
                "detail": f"could not read book scenes ({exc.status})"},
    )


@internal_router.post("/{book_id}/materialize-scenes")
async def materialize_scenes_internal(
    book_id: UUID,
    body: MaterializeScenesRequest,
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """SC6 decompiler — the import-tail entry point (internal token). Reads the
    book's parsed scenes via a minted service bearer for `owner_user_id`, then
    upserts one spec node per leaf. Returns per-scene outcome counts."""
    # The internal token authenticates the caller (worker-infra) but does NOT
    # authorize the action: `book_id` is client-traceable (it flows from a
    # user-initiated import job), so gate the asserted owner's EDIT grant on the
    # book before writing spec nodes (`internal-route-driven-by-a-session-must-
    # grant-check`). Fail-closed: a book-service outage → OwnershipError → 404.
    await _gate_book(grant, book_id, body.owner_user_id, GrantLevel.EDIT)
    bearer = mint_service_bearer(body.owner_user_id, settings.jwt_secret)
    try:
        scenes = await fetch_book_scenes(settings.book_internal_url, book_id, bearer)
    except BookSceneFetchError as exc:
        raise _map_scene_fetch_error(exc)
    result = await materialize_scenes(
        get_pool(), works, outline,
        book_id=book_id, scenes=scenes, created_by=body.owner_user_id,
    )
    return result.to_dict()


@router.post("/books/{book_id}/materialize-scenes")
async def materialize_scenes_v1(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """SC6 decompiler — the Hub CTA mirror (EDIT-gated). Same core as the internal
    route; the caller's own bearer reads the scene list (EDIT ⊇ VIEW, so the
    downstream read is always authorized)."""
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        scenes = await fetch_book_scenes(settings.book_internal_url, book_id, bearer)
    except BookSceneFetchError as exc:
        raise _map_scene_fetch_error(exc)
    result = await materialize_scenes(
        get_pool(), works, outline,
        book_id=book_id, scenes=scenes, created_by=user_id,
    )
    return result.to_dict()
