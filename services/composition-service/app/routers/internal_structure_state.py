"""Internal book structure-state — "did a COMPILE actually write linked structure?".

`GET /internal/composition/books/{book_id}/structure-state?caller_user_id=`
answers, in ONE indexed read, two governance effect signals (Phase G · G0,
spec 2026-07-15-agent-task-governance §14 D2/D3):

* `linked_count` — structure_node rows with `plan_run_id` SET (COMPILE-attributed),
  book-global. *ensure-EXISTS*: "the book has a compiled plan". EXCLUDES the bare
  `composition_arc_create` INSERT (no run stamp) — so a plain insert can NOT fabricate
  the effect (D3: probe the durable, run-attributed truth, not a gameable count).
* `latest_run_linked_count` — rows stamped by the LATEST plan_run only. *produce-NEW*:
  "THIS planning attempt compiled fresh structure". On a re-plan (a fresh latest run whose
  compile has not landed) it reads 0 while `linked_count` is already >0 — so a step gated
  on it is NOT born-done (D2 freshness).

The rail's per-turn book-state probe (chat-service) calls this once a turn to gate the
co_write/planning "compile" step on the REAL effect, not on `has_spec` (which a mere
proposal satisfies — the S06 false-done this closes). Must stay a single cheap read.

ACCESS: mirrors internal_plan_state — a client-traceable `book_id` + `caller_user_id`,
internal token authenticates the SERVICE not the caller, a real E0 book grant is still
required (`internal-route-driven-by-a-session-must-grant-check`). `resolve_owner` doubles
as the gate — no grant (or book absent) → uniform 404, never a 403/owner oracle. The read
is book-keyed (structure_node is per-book post 25), so the resolved owner does not scope it.

NO-STRUCTURE IS NOT AN ERROR: a book with zero compiled arcs returns 200 with both counts 0
and `latest_run_id=null`. A repo that is genuinely dormant (no DB pool — a misconfig, since
prod always has one) → 503, so the probe reads UNKNOWN (None), never a fabricated 0.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.repositories.structure import StructureConflictError
from app.deps import get_grant_client_dep, get_structure_repo
from app.middleware.internal_auth import require_internal_token

router = APIRouter(
    prefix="/internal/composition",
    tags=["internal"],
    dependencies=[Depends(require_internal_token)],
)


class StructureStateResponse(BaseModel):
    book_id: str
    linked_count: int
    latest_run_id: str | None = None
    latest_run_linked_count: int


@router.get("/books/{book_id}/structure-state", response_model=StructureStateResponse)
async def get_book_structure_state(
    book_id: UUID,
    caller_user_id: UUID = Query(...),
    structure=Depends(get_structure_repo),
    grant=Depends(get_grant_client_dep),
) -> StructureStateResponse:
    # Grant check FIRST (the internal token is not authorization).
    if await grant.resolve_owner(book_id, caller_user_id) is None:
        raise HTTPException(status_code=404, detail="book not found or no access")
    if structure is None:
        # Pool dormant — surface UNKNOWN (503), never a fabricated 0 that would tell the
        # rail "no structure, go build it" on a book that may already have a compiled plan.
        raise HTTPException(status_code=503, detail="structure repo unavailable")
    state = await structure.linked_structure_state(book_id)
    latest = state["latest_run_id"]
    return StructureStateResponse(
        book_id=str(book_id),
        linked_count=state["linked_count"],
        latest_run_id=str(latest) if latest else None,
        latest_run_linked_count=state["latest_run_linked_count"],
    )


@router.get("/books/{book_id}/parts")
async def get_book_parts_internal(
    book_id: UUID,
    caller_user_id: UUID = Query(...),
    structure=Depends(get_structure_repo),
    grant=Depends(get_grant_client_dep),
) -> dict:
    """H2 (book-structure §4.5) — the book's LIVE manuscript parts, so the book-service MCP write path
    (`book_chapter_set_part`) can validate a proposed target WITHOUT a user bearer. The agent MCP context
    carries a user_id but no JWT, so composition's bearer-gated public `/parts` is unreachable; without a
    check the agent could home a chapter onto an arc id / foreign-book part and it silently reads as
    Unassigned (§4.5, the agent half of the no-silent-seam fix). Same `{items:[{part_id,title,sort_order,
    lifecycle_state}]}` shape the public route returns, so book-service parses one contract.

    Grant-checked on `caller_user_id` FIRST (the internal token authenticates the SERVICE, not
    authorization — internal-route-driven-by-a-session-must-grant-check): no grant → uniform 404.
    `list_tree` already excludes archived parts AND a non-active `book_lifecycle`, so a trashed book
    returns [] (a bad target on a dead book fails validation, as it should)."""
    if await grant.resolve_owner(book_id, caller_user_id) is None:
        raise HTTPException(status_code=404, detail="book not found or no access")
    if structure is None:
        raise HTTPException(status_code=503, detail="structure repo unavailable")
    nodes = await structure.list_tree(book_id, kinds=("part",))
    items = [_part_json_internal(n) for n in nodes]
    return {"items": items}


# ── Internal part-WRITE routes (manuscript-structure MCP tool, spec 2026-07-22) ────────────────────
# The public part routes (arc.py create_part/rename_part/reorder_parts) are BEARER-gated. The MCP agent
# write path (book_structure_edit in book-service) has only X-Internal-Token + the acting user_id — no
# user JWT — so it cannot reach them. These internal counterparts mirror the internal /parts GET above:
# the token authenticates the SERVICE, a real E0 book grant on `caller_user_id` is still required
# (resolve_owner FIRST → uniform 404, no owner oracle). They REUSE the same StructureRepo methods the
# public routes call, so the semantics (flat integer rank, LWW, exact-set reorder) stay identical.


def _part_json_internal(n) -> dict:
    """Same {part_id,title,sort_order,lifecycle_state} contract the internal GET returns, so book-service
    parses ONE shape for read and write."""
    return {
        "part_id": str(n.id),
        "title": n.title or "",
        "sort_order": int(n.rank) if (n.rank or "").isdigit() else 0,
        "lifecycle_state": "trashed" if getattr(n, "is_archived", False) else "active",
    }


class _PartCreateBody(BaseModel):
    title: str = Field(default="", max_length=500)


class _PartRenameBody(BaseModel):
    title: str = Field(default="", max_length=500)


class _PartReorderBody(BaseModel):
    ordered_ids: list[UUID]


@router.post("/books/{book_id}/parts", status_code=201)
async def create_part_internal(
    book_id: UUID,
    body: _PartCreateBody,
    caller_user_id: UUID = Query(...),
    structure=Depends(get_structure_repo),
    grant=Depends(get_grant_client_dep),
) -> dict:
    """Create a manuscript 'part' (depth-0 grouping) for the agent write path. EDIT grant required."""
    if await grant.resolve_owner(book_id, caller_user_id) is None:
        raise HTTPException(status_code=404, detail="book not found or no access")
    if structure is None:
        raise HTTPException(status_code=503, detail="structure repo unavailable")
    node = await structure.create_part(book_id, created_by=caller_user_id, title=body.title.strip())
    return _part_json_internal(node)


@router.patch("/parts/{node_id}")
async def rename_part_internal(
    node_id: UUID,
    body: _PartRenameBody,
    caller_user_id: UUID = Query(...),
    structure=Depends(get_structure_repo),
    grant=Depends(get_grant_client_dep),
) -> dict:
    """Rename a 'part'. Resolve the node FIRST, 404 unless it's a live 'part' (a parts route must never
    touch an arc — mirrors public `_gate_part`), then gate the OWNING book on caller_user_id."""
    if structure is None:
        raise HTTPException(status_code=503, detail="structure repo unavailable")
    node = await structure.get(node_id)
    if node is None or node.kind != "part":
        raise HTTPException(status_code=404, detail="part not found or no access")
    if await grant.resolve_owner(node.book_id, caller_user_id) is None:
        raise HTTPException(status_code=404, detail="part not found or no access")
    updated = await structure.update(node_id, {"title": body.title.strip()}, expected_version=None)
    if updated is None:
        raise HTTPException(status_code=404, detail="part not found or no access")
    return _part_json_internal(updated)


@router.post("/books/{book_id}/parts/reorder")
async def reorder_parts_internal(
    book_id: UUID,
    body: _PartReorderBody,
    caller_user_id: UUID = Query(...),
    structure=Depends(get_structure_repo),
    grant=Depends(get_grant_client_dep),
) -> dict:
    """Rewrite the book's active-part order. `ordered_ids` must be EXACTLY the active parts — a
    subset/superset/foreign id fails the WHOLE op (StructureConflictError → 409), never a silent drop."""
    if await grant.resolve_owner(book_id, caller_user_id) is None:
        raise HTTPException(status_code=404, detail="book not found or no access")
    if structure is None:
        raise HTTPException(status_code=503, detail="structure repo unavailable")
    try:
        nodes = await structure.reorder_parts(book_id, body.ordered_ids)
    except StructureConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc) or "part reorder conflict") from exc
    return {"items": [_part_json_internal(n) for n in nodes]}


@router.delete("/parts/{node_id}", status_code=204)
async def archive_part_internal(
    node_id: UUID,
    caller_user_id: UUID = Query(...),
    structure=Depends(get_structure_repo),
    grant=Depends(get_grant_client_dep),
) -> None:
    """Archive (SOFT-delete / trash) a 'part' for the agent write path — reversible via the public
    restore. Chapters keep their structure_node_id; the grouping read excludes an archived part, so its
    chapters fall to Unassigned (same as the public DELETE). 404 unless it's a live 'part' of a book the
    caller may EDIT."""
    if structure is None:
        raise HTTPException(status_code=503, detail="structure repo unavailable")
    node = await structure.get(node_id)
    if node is None or node.kind != "part":
        raise HTTPException(status_code=404, detail="part not found or no access")
    if await grant.resolve_owner(node.book_id, caller_user_id) is None:
        raise HTTPException(status_code=404, detail="part not found or no access")
    await structure.archive(node_id)
