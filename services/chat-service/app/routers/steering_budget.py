"""T12 — the steering budget, BEFORE it silently eats an author's rules.

WHY THIS EXISTS. A 2026-09-06 human-sim run wrote 8 steering rules for a book and the model
generated against 3 of them for the entire run. The 5 dropped included the locked arc outline and
the corruption-tier mechanics — the plot-critical content steering exists to protect — so the book
was written against a bible the model could not see. Nothing anywhere in the UI said so; it was
found by reading container logs.

Issue #223 raised ``STEERING_TOKEN_CAP`` 2000→8000, which fixes that particular book, and
explicitly deferred the real problem: a bible that genuinely outgrows the cap STILL loses rules
silently. MCP Tool I/O's **OUT-5** already states the rule — *"never silently truncate: report the
cap"* — and an author cannot be expected to debug their own novel from a container's stderr.

WHY A READ ENDPOINT AND NOT A PER-TURN NOTICE. A mid-turn toast reports the generation it already
spoiled. This answers the question while the author is EDITING their rules, which is when they can
act on it — and it is a plain read, rather than threading a new event through a 14,705-line
streaming generator that feeds ``StreamingResponse`` directly.

WHY IT LIVES IN CHAT-SERVICE. The cap and the token estimator are here. Re-implementing the
estimate in the browser would create a second source of truth that disagrees with the one actually
applied at generation time — a worse failure than no indicator, because it would be believed.

Mounted under ``/v1/chat`` so the existing gateway proxy filter reaches it with no gateway change.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.client.book_steering_client import get_book_steering_client
from app.client.grant_client import GrantLevel, get_grant_client
from app.deps import get_current_user
from app.services.steering import STEERING_TOKEN_CAP, select_steering_ex
from app.services.token_budget import estimate_tokens, scale_by_window

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/chat/books", tags=["steering-budget"])


class SteeringBudget(BaseModel):
    """What this book's steering costs, against what it is allowed."""

    #: Rules the book has, enabled.
    total_entries: int
    #: Estimated tokens for ALL of them — what the author has written.
    total_tokens: int
    #: The cap actually applied. Scales with the session model's context window, so it is reported
    #: rather than assumed: an author comparing their total against a hardcoded 8000 would draw the
    #: wrong conclusion on a large-window model.
    cap_tokens: int
    #: True when the cap would drop rules from a turn that includes everything.
    over_budget: bool
    #: How many would be dropped, and WHICH. The count alone is not actionable: "5 dropped" does
    #: not tell an author that the locked arc outline was one of them.
    would_drop: int
    would_drop_names: list[str]


@router.get("/{book_id}/steering-budget", response_model=SteeringBudget)
async def read_steering_budget(
    book_id: UUID,
    context_length: int | None = None,
    user_id: UUID = Depends(get_current_user),
) -> SteeringBudget:
    """Report what a book's steering costs and what the cap would drop.

    ``context_length`` is optional and mirrors what the turn would pass: the cap scales with the
    session model's real window, so a caller that knows the model gets the number that will
    actually apply. Omitted, it reports against the flat default.

    AUTHORIZATION IS EXPLICIT HERE, and it has to be. `get_steering` reads book-service's
    INTERNAL route with a service token — it does not check the caller at all. Returning its
    result to whoever asked would leak another author's rule NAMES and rule COUNT to any
    authenticated user, which is a tenancy break (User Boundaries: every user-facing read filters
    by its scope key). So the caller's grant is resolved first, and a caller below VIEW gets the
    same 404 a missing book gets — no existence oracle.
    """
    lvl, _ = await get_grant_client().resolve_access(book_id, user_id)
    if lvl < GrantLevel.VIEW:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND"},
        )

    # `get_steering` returns [] on ANY failure and never raises, so "no rules" and "book-service is
    # down" arrive identically. This endpoint exists to remove exactly that kind of silence, so it
    # must not present a fetch failure as a confident, empty budget. Probe the difference.
    entries = await get_book_steering_client().get_steering(str(book_id))
    if not entries:
        # An empty result is AMBIGUOUS by the client's own contract. Say so rather than reporting
        # a clean zero the author might trust.
        logger.info(
            "steering budget: no entries returned for book %s (genuinely none, or the fetch "
            "failed — the client cannot distinguish these)", book_id,
        )
        return SteeringBudget(
            total_entries=0, total_tokens=0,
            cap_tokens=scale_by_window(STEERING_TOKEN_CAP, context_length),
            over_budget=False, would_drop=0, would_drop_names=[],
        )
    total_tokens = sum(
        estimate_tokens(f"## {e.get('name', '')}\n{e.get('body', '')}")
        for e in entries
        if isinstance(e, dict)
    )

    # Ask the REAL selector, with a message that mentions every rule by name, so manual/auto
    # entries are included too. Anything less would under-report: a budget preview that silently
    # ignored the modes it could not trigger would be the same partial truth this task exists to
    # remove.
    probe = " ".join(f"#{e.get('name', '')}" for e in entries if isinstance(e, dict))
    _selected, truncation = select_steering_ex(
        entries, message=probe, active_title=None, context_length=context_length,
    )

    return SteeringBudget(
        total_entries=len(entries),
        total_tokens=total_tokens,
        cap_tokens=scale_by_window(STEERING_TOKEN_CAP, context_length),
        over_budget=truncation is not None,
        would_drop=truncation.dropped if truncation else 0,
        would_drop_names=list(truncation.dropped_names) if truncation else [],
    )
