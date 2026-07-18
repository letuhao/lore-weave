"""Internal book plan-state — "does this book have an arc plan?".

`GET /internal/composition/books/{book_id}/plan-state?caller_user_id=`
answers, in ONE indexed read, whether a book has any PlanForge run and whether
any of those runs produced a `spec` artifact. chat-service calls it once per chat
turn to decide whether the turn can lean on an arc plan, so this route must stay a
single cheap read — never a list-then-probe fan-out.

SIGNAL: `has_plan` (a run exists) is NOT the same as `has_spec` (a run produced the
plan spec). A run can sit at `pending` or land on `failed` having emitted no spec —
that book has NO arc plan. `has_spec` is the load-bearing bit; `has_plan` +
`latest_status` only explain WHY (e.g. "a run is pending", "the last run failed").

NO-PLAN IS NOT AN ERROR: a book with zero runs returns 200 with
`has_plan=false, run_count=0, latest_status=null, has_spec=false`. A 404 here would
force every caller to treat "new book" as a failure — "no plan yet" is the expected
answer for a fresh book, not a missing resource.

ACCESS: mirrors internal_model_settings — this /internal route is fed a
client-traceable `book_id` + `caller_user_id`, so the internal token authenticates
the SERVICE, not the caller; a real E0 book grant is still required
(`internal-route-driven-by-a-session-must-grant-check`). `GrantClient.resolve_owner`
doubles as that gate — no grant (or book absent) → uniform 404, never a 403/owner
oracle. The read itself is book-keyed (plan_run is per-book post 25 OQ-3;
`created_by` is a plain actor stamp), so the resolved owner does not scope it.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.deps import get_grant_client_dep, get_plan_runs_repo
from app.middleware.internal_auth import require_internal_token

router = APIRouter(
    prefix="/internal/composition",
    tags=["internal"],
    dependencies=[Depends(require_internal_token)],
)


class PlanStateResponse(BaseModel):
    book_id: str
    has_plan: bool
    run_count: int
    latest_status: str | None = None
    has_spec: bool


@router.get("/books/{book_id}/plan-state", response_model=PlanStateResponse)
async def get_book_plan_state(
    book_id: UUID,
    caller_user_id: UUID = Query(...),
    plans=Depends(get_plan_runs_repo),
    grant=Depends(get_grant_client_dep),
) -> PlanStateResponse:
    # Grant check FIRST (the internal token is not authorization).
    if await grant.resolve_owner(book_id, caller_user_id) is None:
        raise HTTPException(status_code=404, detail="book not found or no access")
    state = await plans.plan_state_for_book(book_id)
    run_count = state["run_count"]
    return PlanStateResponse(
        book_id=str(book_id),
        has_plan=run_count > 0,
        run_count=run_count,
        latest_status=state["latest_status"],
        has_spec=state["has_spec"],
    )
