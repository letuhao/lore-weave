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
from pydantic import BaseModel

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
