"""Plan Hub v2 — the plan-overlay aggregate route (24 H1.3, read surface #3).

`GET /v1/composition/books/{book_id}/plan-overlay` returns the Hub's DECORATIONS
layer in one book-wide call (kills the F-H5 N+1): canon + open-thread problems
keyed by node, a derived per-chapter tension rollup, the motif lockfile chips, and
the (cross-service) unplanned-chapters tray.

Tenancy (BPS-8): VIEW-gated on the path ``book_id`` via the SAME E0 book-grant
chokepoint arc.py uses (``authorize_book`` → OwnershipError=404 no-oracle /
InsufficientGrant=403). Book-scoped throughout; no Work gate (PH9).

Boundaries this slice HOLDS (24 §Ownership):
  • drift/staleness is NOT here — it rides ``26`` IX-14's ``/conformance/status``
    (read surface #7, PH18/OQ-8). This payload carries canon + thread-debt only.
  • ``unplanned_chapters`` needs book-service (the manuscript chapter spine) which
    composition-service cannot join cheaply (SC11 rejects a cross-service server
    join). Returned ``[]``; the FE computes the tray client-side from read surface
    #5 (book scenes) vs the spec nodes (PH12/PH21). Documented in the return
    contract + this slice's uncertainties — never faked.

The response is bounded + partiality-flagged (OUT-5): refs are capped across the
whole payload at ``_REFS_CAP`` and ``problems.refs_capped`` reports truncation;
per-node counts stay EXACT (never silently truncated).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from loreweave_mcp.errors import NOT_ACCESSIBLE_MESSAGE

from app.db.pool import get_pool
from app.db.repositories.plan_overlay import PlanOverlayRepo
from app.deps import get_grant_client_dep
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_current_user
from app.packer.pack import OwnershipError

router = APIRouter(prefix="/v1/composition")

# OUT-5: the whole payload's refs are capped (counts stay exact). ~50 total keeps
# the aggregate small on a pathological book; the drawer pages the rest per node.
_REFS_CAP = 50
# A short human 'line' for a ref (a rule/thread one-liner) — never full prose.
_LINE_MAX = 160

# structure_node nesting is capped at saga→arc→sub-arc (depth 0..2), so an
# ancestor chain is ≤ 3; the guard bound is a cheap belt-and-braces vs bad data.
_MAX_ANCESTOR_HOPS = 6


async def get_plan_overlay_repo() -> PlanOverlayRepo:
    """Local DI factory (kept in-router: ``deps.py`` is the integrate step's /
    another slice's file). ``PlanOverlayRepo`` is a cheap per-request wrapper over
    the shared asyncpg pool — mirrors ``deps.get_outline_repo``. Overridable in
    tests via ``dependency_overrides``."""
    return PlanOverlayRepo(get_pool())


async def _gate_book(
    grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel
) -> None:
    """E0 book-grant chokepoint → HTTP (mirrors arc._gate_book / outline._gate_book).
    none→404 (the uniform H13 not-accessible message, no existence oracle),
    under-tier→403."""
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail=NOT_ACCESSIBLE_MESSAGE)
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


# ── pure assembly (no DB — unit-tested directly) ─────────────────────────────


def _line(text: str | None, limit: int = _LINE_MAX) -> str:
    """A short, single-line human label for a ref (never full prose — OUT-1)."""
    t = " ".join((text or "").split())
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


def _ancestor_chain(node_id: str, parent_map: dict[str, str | None]) -> list[str]:
    """The structure_node itself + every ancestor (sub-arc → arc → saga), so an
    item under a chapter rolls its COUNT up onto each enclosing lane (BA15 subtree
    semantics). Cycle-safe + bounded."""
    chain: list[str] = []
    seen: set[str] = set()
    cur: str | None = node_id
    while cur is not None and cur not in seen and len(chain) < _MAX_ANCESTOR_HOPS:
        chain.append(cur)
        seen.add(cur)
        cur = parent_map.get(cur)
    return chain


def _build_overlay(
    canon_rows: list[dict[str, Any]],
    thread_rows: list[dict[str, Any]],
    structure_parent_rows: list[dict[str, Any]],
    tension_rows: list[dict[str, Any]],
    motif_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the bounded plan-overlay response from the raw repo rows. PURE —
    no I/O — so the shape, the ~50-ref cap, and the empty-book case are unit-tested
    without a DB.

    Attribution model:
      • A canon anchor / open thread lands COUNT + a leaf REF on its own node
        (outline_node.id), and rolls its COUNT (no ref) up each ancestor arc
        (structure_node.id) — so a collapsed lane shows the subtree total and an
        expanded chapter shows its own. Refs stay on the leaf only, so the cap
        stays meaningful (an arc never duplicates its children's refs).
    """
    parent_map: dict[str, str | None] = {
        str(r["id"]): (str(r["parent_id"]) if r.get("parent_id") else None)
        for r in structure_parent_rows
    }

    by_node: dict[str, dict[str, Any]] = {}
    refs_total = 0
    refs_capped = False

    def _entry(node_id: str) -> dict[str, Any]:
        return by_node.setdefault(
            node_id, {"canon": 0, "threads_open": 0, "refs": []}
        )

    def _bump(node_id: str, field: str, arc_id: Any) -> None:
        """Increment ``field`` on the leaf node + every ancestor arc (rollup)."""
        _entry(node_id)[field] += 1
        if arc_id is not None:
            for anc in _ancestor_chain(str(arc_id), parent_map):
                _entry(anc)[field] += 1

    def _add_ref(node_id: str, ref: dict[str, str]) -> None:
        """Append a leaf ref, honoring the whole-payload cap (counts unaffected)."""
        nonlocal refs_total, refs_capped
        if refs_total >= _REFS_CAP:
            refs_capped = True
            return
        _entry(node_id)["refs"].append(ref)
        refs_total += 1

    # canon: boundary-anchored rules (leaf = the chapter node).
    for r in canon_rows:
        node_id = str(r["node_id"])
        _bump(node_id, "canon", r.get("arc_id"))
        _add_ref(node_id, {
            "kind": "canon",
            "id": str(r["rule_id"]),
            "line": _line(r.get("rule_text")),
        })

    # open threads: leaf = the opening node (skip un-anchored / node-deleted).
    for r in thread_rows:
        raw_node = r.get("node_id")
        if raw_node is None:
            continue
        node_id = str(raw_node)
        _bump(node_id, "threads_open", r.get("arc_id"))
        _add_ref(node_id, {
            "kind": "thread",
            "id": str(r["thread_id"]),
            "line": _line(r.get("summary") or r.get("trigger") or r.get("thread_kind")),
        })

    tension_rollup = [
        {
            "chapter_node_id": str(r["chapter_node_id"]),
            "story_order": r.get("story_order"),
            "tension": r.get("tension"),
        }
        for r in tension_rows
    ]

    motif_chips = [
        {
            "node_ref": str(r["node_ref"]),
            "motif_id": str(r["motif_id"]),
            "title": r.get("title") or "",
            "pinned_version": r.get("pinned_version"),
            "live_version": r.get("live_version"),
        }
        for r in motif_rows
    ]

    return {
        "problems": {"by_node": by_node, "refs_capped": refs_capped},
        "tension_rollup": tension_rollup,
        "motif_chips": motif_chips,
        # PH21/OQ-8: the manuscript spine lives in book-service; SC11 forbids the
        # cross-service server join here. The FE derives the tray from read surface
        # #5 vs the spec nodes. Empty (never faked).
        "unplanned_chapters": [],
    }


# ── route ────────────────────────────────────────────────────────────────────


@router.get("/books/{book_id}/plan-overlay")
async def get_plan_overlay(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user),
    grant: GrantClient = Depends(get_grant_client_dep),
    repo: PlanOverlayRepo = Depends(get_plan_overlay_repo),
) -> dict[str, Any]:
    """The Hub's decorations layer in one book-wide call (read surface #3). VIEW on
    the book. Canon + open-thread problems keyed by node (with an arc-subtree
    rollup), a derived per-chapter tension rollup, motif lockfile chips, and the
    (empty here) unplanned tray — see the module docstring for the boundaries this
    route holds (no drift/staleness; unplanned tray is FE-derived)."""
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    canon = await repo.fetch_canon_anchors(book_id)
    threads = await repo.fetch_open_threads(book_id)
    parents = await repo.fetch_structure_parents(book_id)
    tension = await repo.fetch_tension_rollup(book_id)
    motifs = await repo.fetch_motif_chips(book_id)
    return _build_overlay(canon, threads, parents, tension, motifs)
