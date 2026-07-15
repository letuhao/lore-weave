"""Track C Phase 2 — the BOOK-STATE PROBE: what is actually in this book, right now.

Reads the five artifacts a book-building rail produces, straight from the services that own
them. Fanned out in parallel, bounded, and cached for the turn.

WHY THIS IS WORTH A FAN-OUT. The flagship's signature failure is not a missing tool — it is
the agent losing its place. Grounding it costs five indexed reads on a turn that is already
about to spend tens of thousands of tokens on an LLM call, and it buys the one thing the
model cannot supply for itself: the truth about what it has actually accomplished. Note in
particular that this catches the class of bug no call-log can: a tool that ran, returned
"success", and wrote nothing.

DEGRADE CONTRACT — every source is independently best-effort. A source that fails yields
``None`` (UNKNOWN), never ``0``. That distinction is load-bearing: ``0`` tells the agent
"your world is empty, go build it", and telling that to a user whose glossary service merely
blipped would have the agent cheerfully rebuild a world they already have. If EVERY source
fails, the caller renders no grounding block at all and the turn degrades to exactly the
pre-Phase-2 behavior.
"""

from __future__ import annotations

import asyncio
import logging

from loreweave_internal_client import build_internal_client

from app.config import settings
from app.middleware.trace_id import trace_id_var
from app.services.rail_progress import BookState

logger = logging.getLogger(__name__)

# One probe rides a turn that is about to make an LLM call, so a slow service must never
# hold the turn hostage: a source that cannot answer in 2s is treated as UNKNOWN.
_PROBE_TIMEOUT_S = 2


async def _get_json(base: str, path: str, params: dict | None = None) -> dict | None:
    """GET an /internal route; None on ANY failure (including a non-200)."""
    if not base:
        return None
    try:
        async with build_internal_client(
            base,
            internal_token=settings.internal_service_token,
            timeout_s=_PROBE_TIMEOUT_S,
            trace_id_provider=trace_id_var.get,
        ) as client:
            resp = await client.get(f"{base}{path}", params=params or {})
        if resp.status_code == 200:
            body = resp.json()
            return body if isinstance(body, dict) else None
        logger.debug("book-state probe %s → HTTP %s", path, resp.status_code)
        return None
    except Exception:  # noqa: BLE001 — a probe never breaks the turn
        logger.debug("book-state probe %s failed", path, exc_info=True)
        return None


async def _categories(book_id: str) -> int | None:
    d = await _get_json(settings.glossary_service_url, f"/internal/books/{book_id}/ontology")
    if d is None:
        return None
    kinds = d.get("kinds")
    return len(kinds) if isinstance(kinds, list) else None


async def _cast(book_id: str) -> int | None:
    d = await _get_json(settings.glossary_service_url, f"/internal/books/{book_id}/entity-count")
    if d is None:
        return None
    n = d.get("count")
    return int(n) if isinstance(n, int) else None


async def _connections(book_id: str) -> int | None:
    d = await _get_json(settings.knowledge_service_url, f"/internal/books/{book_id}/kg-state")
    if d is None:
        return None
    if not d.get("has_projection"):
        return 0  # confirmed: no projection exists yet
    n = d.get("entity_count")
    # UNKNOWN, not zero, when the stats cache was never computed (n is null) or the shape is
    # unexpected — matching every sibling source. A confirmed 0 here would tell the rail the
    # connection step never landed and send the agent to re-drive a projection that exists.
    return int(n) if isinstance(n, int) else None


async def _suggestions(book_id: str) -> int | None:
    """The review pile still awaiting triage — ai-suggested entities still in DRAFT (a
    keep/throw-out/combine decision moves them off draft, so this counts down as the user
    triages). 0 = a clean pile (confirmed), None = glossary unreachable (UNKNOWN, never a
    manufactured zero — telling the triage rail "0 left" on a blip would call it finished
    while items remain)."""
    d = await _get_json(settings.glossary_service_url, f"/internal/books/{book_id}/suggestions-count")
    if d is None:
        return None
    n = d.get("count")
    return int(n) if isinstance(n, int) else None


async def _plan(book_id: str, caller_user_id: str) -> int | None:
    d = await _get_json(
        settings.composition_service_internal_url,
        f"/internal/composition/books/{book_id}/plan-state",
        {"caller_user_id": caller_user_id},
    )
    if d is None:
        return None
    # A plan-EXISTENCE flag (1/0), not a count of runs — "has an arc plan" means a SPEC
    # artifact exists. A plan_run that never produced a spec is a started-and-abandoned
    # attempt, and calling that "done" would march the agent past the step that writes the
    # plan. Return 0 only when the route positively says so; an unexpected shape is UNKNOWN
    # (None), matching every sibling source, never a manufactured zero.
    hs = d.get("has_spec")
    if hs is True:
        return 1
    if hs is False:
        return 0
    return None


async def _structure(book_id: str, caller_user_id: str) -> tuple[int | None, int | None]:
    """The COMPILE-attributed structure (Phase G · G0) — the effect a mere proposal does NOT
    produce. Returns ``(structure, structure_fresh)``:

    * ``structure`` = compiled arcs book-global (structure_node with plan_run_id set) —
      *ensure-EXISTS*, and it EXCLUDES the bare ``composition_arc_create`` INSERT, so a plain
      insert can't fabricate "the plan is compiled" (D3).
    * ``structure_fresh`` = arcs the LATEST plan run compiled — *produce-NEW*, so a re-plan reads
      0 until ITS compile lands (D2).

    Both come from ONE cheap /internal read. UNKNOWN (None) on any failure — never a manufactured
    0, matching every sibling source (a book-service blip must not read as "no structure, rebuild
    it"). Grant-scoped by ``caller_user_id`` exactly like ``_plan``."""
    d = await _get_json(
        settings.composition_service_internal_url,
        f"/internal/composition/books/{book_id}/structure-state",
        {"caller_user_id": caller_user_id},
    )
    if d is None:
        return None, None
    lc, fresh = d.get("linked_count"), d.get("latest_run_linked_count")
    return (
        lc if isinstance(lc, int) else None,
        fresh if isinstance(fresh, int) else None,
    )


async def _chapters_and_prose(book_id: str) -> tuple[int | None, int | None]:
    d = await _get_json(settings.book_service_url, f"/internal/books/{book_id}/prose-state")
    if d is None:
        return None, None
    ch, pr = d.get("chapters"), d.get("with_prose")
    return (ch if isinstance(ch, int) else None, pr if isinstance(pr, int) else None)


async def probe_book_state(book_id: str, caller_user_id: str) -> BookState:
    """Read the book's five artifacts in parallel. Never raises."""
    if not book_id:
        return BookState()

    results = await asyncio.gather(
        _categories(book_id),
        _cast(book_id),
        _connections(book_id),
        _plan(book_id, caller_user_id),
        _chapters_and_prose(book_id),
        _suggestions(book_id),
        _structure(book_id, caller_user_id),
        return_exceptions=True,
    )

    def _val(r):
        return None if isinstance(r, BaseException) else r

    categories, cast, connections, plan = (_val(r) for r in results[:4])
    ch_pr = _val(results[4]) or (None, None)
    chapters, prose = ch_pr
    suggestions = _val(results[5])
    struct = _val(results[6]) or (None, None)
    structure, structure_fresh = struct

    state = BookState(
        categories=categories, cast=cast, connections=connections,
        plan=plan, structure=structure, structure_fresh=structure_fresh,
        chapters=chapters, prose=prose, suggestions=suggestions,
    )
    state.failed_sources = [
        name for name, v in (
            ("glossary/categories", categories), ("glossary/cast", cast),
            ("knowledge/connections", connections), ("composition/plan", plan),
            ("composition/structure", structure),
            ("book/chapters", chapters), ("glossary/suggestions", suggestions),
        ) if v is None
    ]
    if state.failed_sources:
        # Loud enough to notice, quiet enough not to spam: a permanently-failing source
        # means the agent is running half-blind, which is exactly the thing that used to be
        # invisible.
        logger.warning(
            "book-state probe: %d/6 sources unavailable for book=%s (%s) — "
            "the rail will be grounded only on what answered",
            len(state.failed_sources), book_id, ", ".join(state.failed_sources),
        )
    return state
