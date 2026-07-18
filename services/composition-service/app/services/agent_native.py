"""28 AN-2/AN-3/AN-4 — the agent's three read surfaces, COMPOSED from what already exists.

The one law this module lives under (AN-4, and 26 IX-14's consumer note before it):

    **It composes. It never recomputes.**

Every number here is produced by the code that already owns that number — `compute_conformance_
status` for staleness, `OutlineRepo.canon_issues` for contradictions, `structure.open_promises` for
thread debt, `coverage.compute_coverage` for the planned/written diff. A second implementation of any
of them would be a second source of truth, and this repo has already paid for that lesson twice (the
CSS-var duplication; the `unplanned_chapters` hardcode this cluster opened by fixing).

The other law is quieter but decides the shape of everything below: **absent ≠ zero.** These are
orientation tools. An agent reads them to decide what to do next, so a block we could not compute
must come back MISSING with a warning — never as a confident `0`. A faked zero here does not degrade
the agent's answer, it inverts it: "0 unplanned chapters" and "I could not reach book-service" lead
to opposite actions, and only one of them is honest.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from app.engine.scene_decompile import resolve_canonical_work

logger = logging.getLogger(__name__)

#: AN-2: the tree is ORIENTATION, hard-capped ≈2-4K tokens even on a 10k-chapter book. Counts and
#: per-arc one-liners, never prose. Drill-down is the existing per-layer list tools' job — that
#: separation IS the fix for the 146K-token `composition_list_outline` incident.
_ARC_CAP = 50
_ARC_LINE_CHARS = 120

#: AN-3/AN-4: exact COUNTS, capped REFS (OUT-5 verbatim). The count is cheap and the agent needs it
#: to decide; the rows are expensive and it only needs a sample to act.
_REF_CAP = 20
_DIAG_CAP = 25

#: AN-3's closed set — EIGHT sources over the seven F-A4 shapes (the outline pov/present pair
#: splits). A closed-set arg gets an enum, or a weak model sends `"outline"` and gets a silent
#: no-op (the Frontend-Tool-Contract bug this repo shipped once).
ReferenceSource = Literal[
    "outline_pov",
    "outline_present",
    "scene_pov",
    "scene_present",
    "structure_roster",
    "motif_application",
    "canon_rule",
    "narrative_thread",
]
REFERENCE_SOURCES: tuple[str, ...] = (
    "outline_pov", "outline_present", "scene_pov", "scene_present",
    "structure_roster", "motif_application", "canon_rule", "narrative_thread",
)

#: AN-4's fixed severity map. Fixed, not computed — a diagnostics tool that ranked by its own
#: judgement would be a second opinion competing with the engines that produced the findings.
SEVERITY: dict[str, str] = {
    "canon_contradiction": "error",
    # 24 PH18 — the RULE lane. DISTINCT from `canon_contradiction`, which is the ENTITY-continuity
    # lane ("a gone character is acting") and carries no rule id. Without this the agent's problems
    # panel could not see a broken author-declared rule at all, while the human's canon panel could
    # — two truths for "what is wrong with this book".
    "broken_canon_rule": "error",
    "prose_deleted_spec_node": "error",
    "conformance_never_run": "warn",
    "conformance_dirty": "warn",
    "index_stale": "warn",
    "unplanned_chapter": "warn",
    "open_thread_debt": "info",
}
_RANK = {"error": 0, "warn": 1, "info": 2}


@dataclass
class Block:
    """One block of a composed read: either it HAS a value, or it says why it does not.

    This type exists to make the absent-vs-zero distinction unavoidable at the call site. A block
    that failed cannot be spelled the same way as a block that is genuinely empty — you have to pick
    `degraded()` or a value, and `degraded()` demands a reason.
    """

    value: Any = None
    degraded: bool = False
    warning: str = ""

    @classmethod
    def failed(cls, warning: str) -> Block:
        return cls(value=None, degraded=True, warning=warning)

    def into(self, out: dict[str, Any], key: str, warnings: list[str]) -> None:
        """Attach to the payload — OMITTING the key when degraded, and saying so in `warnings`.

        Omission is deliberate and is the whole point. `{"unplanned_chapters": []}` renders as
        "nothing is unplanned"; a MISSING key forces every consumer to branch, which is what we want,
        because we genuinely do not know.
        """
        if self.degraded:
            warnings.append(self.warning)
            return
        out[key] = self.value


@dataclass
class Diagnostic:
    kind: str
    severity: str
    title: str
    detail: str = ""
    node_ref: dict[str, Any] | None = None
    at: str | None = None   # ISO ts, for the recency sort
    # S-10 O3 — deep-link focus params for the panel that owns the fix. The `node_ref` names WHAT is
    # wrong (a scene); `focus` carries the params THAT panel actually focuses by, which differ from the
    # node id (quality-canon-rules focuses a `focusRuleId`, quality-canon a `focusChapterId`). The FE
    # spreads these into the open-panel params so a row jumps to the exact offending row, not just the
    # panel. Only set when the source repo exposes the panel-appropriate id.
    focus: dict[str, str] | None = None


@dataclass
class Diagnostics:
    items: list[Diagnostic] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    refs_capped: bool = False
    warnings: list[str] = field(default_factory=list)

    def add(self, d: Diagnostic) -> None:
        self.items.append(d)
        self.counts[d.kind] = self.counts.get(d.kind, 0) + 1

    def ranked(self, cap: int = _DIAG_CAP) -> dict[str, Any]:
        """error → warn → info, then most recent first. Capped, and it SAYS it capped (OUT-5).

        The counts are the EXACT totals; only the item rows are capped. An agent deciding "is this
        book in trouble" needs the true number; it only needs a sample of rows to act on."""
        ordered = sorted(
            self.items,
            key=lambda d: (_RANK.get(d.severity, 3), _neg_ts(d.at)),
        )
        shown = ordered[:cap]
        return {
            "items": [
                {
                    "kind": d.kind, "severity": d.severity, "title": d.title,
                    **({"detail": d.detail} if d.detail else {}),
                    **({"node_ref": d.node_ref} if d.node_ref else {}),
                    **({"focus": d.focus} if d.focus else {}),
                    **({"at": d.at} if d.at else {}),
                }
                for d in shown
            ],
            # EXACT, never capped — this is what the agent reasons about.
            "counts": dict(self.counts),
            "total": len(self.items),
            "refs_capped": len(ordered) > cap,
            **({"warnings": self.warnings} if self.warnings else {}),
        }


def _neg_ts(at: str | None) -> str:
    """Sort key for "most recent first" over ISO strings, without parsing them.

    ISO-8601 sorts lexicographically, so reversing is just inverting the comparison. A `None`
    timestamp sorts LAST within its severity — an undated finding is not more urgent than a dated
    one, and pretending it is now() would be inventing data.
    """
    return "" if at is None else _invert(at)


def _invert(s: str) -> str:
    # descending sort over a lexicographic key, without a reverse= that would also flip severity
    return "".join(chr(0x10FFFD - ord(c)) if ord(c) < 0x10FFFD else c for c in s)


def arc_line(arc: Any, *, chapters: int | None = None) -> str:
    """One arc, one line — AN-2's spec/ tree. Never prose; a title and its shape."""
    title = (getattr(arc, "title", "") or "(untitled)").strip()
    kind = getattr(arc, "kind", "arc")
    status = getattr(arc, "status", "") or ""
    bits = [f"{kind} \"{title[:60]}\""]
    if status:
        bits.append(status)
    if chapters is not None:
        bits.append(f"{chapters} ch")
    return " · ".join(bits)[:_ARC_LINE_CHARS]


def cap_arcs(arcs: list[Any]) -> tuple[list[Any], bool]:
    """AN-2 caps arcs at 50 and SAYS SO (`arcs_capped`). A silent truncation reads as "this book has
    50 arcs", which is a different claim from "here are 50 of them"."""
    return arcs[:_ARC_CAP], len(arcs) > _ARC_CAP


async def resolve_scope(works: Any, book_id: UUID) -> tuple[Any, UUID | None]:
    """`(work, project_id)` for a READ. Never creates, never denies a book that exists.

    `WorksRepo.resolve_by_book` deliberately EXCLUDES a lazy pending Work (C16 — a placeholder with
    a null project is un-anchorable), and its own docstring says `len == 0` must fall through to the
    knowledge lookup, NOT deny. My first cut treated `0` as `uniform_not_accessible()` — and the live
    smoke 404'd a perfectly real book whose Work was still pending backfill.

    A book with no marked Work still HAS a spec tree: `structure_node` and `outline_node` are
    BOOK-keyed. So the tree, the manuscript and the coverage diff all still answer. Only the
    PROJECT-keyed sources (canon issues, thread debt, motif applications) need a project — and when
    there is none they come back ABSENT with a warning, never as a confident zero.

    Returns `(None, None)` only when the book genuinely has no composition Work at all — which is not
    an error either: it is a book nobody has planned yet, and saying so is the useful answer.
    """
    marked = await works.resolve_by_book(book_id)
    if marked:
        # 28 AN-2 (28:502-510) — resolve the CANONICAL Work (source_work_id IS NULL), never
        # marked[0]. `resolve_by_book` returns the canonical + any C23 derivatives ORDER BY
        # created_at, so marked[0] is only incidentally the canonical — and on archive-and-
        # recreate (PM-4 permits it) a derivative PREDATES the recreated canonical, making
        # marked[0] the derivative and serving its spec as the book's (25-T4). At most one
        # canonical exists (uq_composition_work_book); fall back to marked[0] only if the set is
        # somehow all-derivative (a data anomaly), which stays a read, never a denial.
        w = resolve_canonical_work(marked) or marked[0]
        return w, (w.project_id or w.id)
    pending = await works.get_pending_for_book(book_id)
    if pending is not None:
        # A pending Work has NO project_id (that is what makes it pending). Its `id` is the
        # surrogate every project-keyed row in this service is already written under.
        return pending, (pending.project_id or pending.id)
    return None, None


async def build_book_diagnostics(
    pool: Any,
    *,
    book_id: UUID,
    project_id: UUID | None,
    user_id: UUID,
    cap: int,
) -> "Diagnostics":
    """S-10 O3 — the shared diagnostics builder behind BOTH ``composition_diagnostics`` (the MCP tool)
    and ``GET /v1/composition/books/{book_id}/diagnostics`` (the FE Issues tab). Composes the SAME
    read-only sources the human problems panel + the agent already share (conformance/index staleness,
    canon contradictions, broken canon rules, open-thread debt, prose-deleted spec nodes, unplanned
    chapters), ranked error → warn → info by ``Diagnostics.ranked``. Every source is best-effort: a
    failed source appends a WARNING (absent, not zero) rather than silently reporting completeness — a
    problems panel with a silent hole is worse than no panel. The caller resolves the project scope
    (``resolve_scope``) and formats via ``diag.ranked(cap=cap)``."""
    from app.clients.book_client import get_book_client
    from app.config import settings
    from app.db.repositories.narrative_thread import NarrativeThreadRepo
    from app.db.repositories.outline import OutlineRepo
    from app.mcp.service_bearer import mint_service_bearer

    diag = Diagnostics()
    if project_id is None:
        diag.warnings.append(
            "this book has no composition work — canon issues, thread debt and motif "
            "applications were NOT checked (absent, not zero)",
        )

    # (1) conformance + index staleness
    try:
        from app.engine.arc_conformance_orchestrate import compute_conformance_status

        status = await compute_conformance_status(
            pool=pool, book_client=get_book_client(), book_id=book_id,
        )
        for arc in status["arcs"]:
            reasons = arc.get("dirty_reasons") or []
            if "never_run" in reasons:
                kind = "conformance_never_run"
            elif arc.get("dirty"):
                kind = "conformance_dirty"
            else:
                continue
            diag.add(Diagnostic(
                kind=kind, severity=SEVERITY[kind],
                title=f'arc "{arc.get("title") or "(untitled)"}" — {", ".join(reasons) or "dirty"}',
                detail="run composition_conformance_run to refresh it",
                node_ref={"kind": "arc", "id": arc["structure_node_id"], "title": arc.get("title")},
                at=arc.get("computed_at"),
            ))
        stale = status["index"]["stale_chapter_count"]
        if stale:
            diag.add(Diagnostic(
                kind="index_stale", severity=SEVERITY["index_stale"],
                title=f"{stale} chapter(s) have a stale prose index",
                detail="the sweeper heals these; re-indexing refreshes the canon windows",
            ))
    except Exception:  # noqa: BLE001
        logger.warning("diagnostics: conformance source failed", exc_info=True)
        diag.warnings.append("conformance + index staleness could not be computed")

    # (2) canon contradictions (entity lane)
    try:
        if project_id is None:
            raise LookupError("no project")
        for issue in await OutlineRepo(pool).canon_issues(project_id):
            violations = issue.get("violations") or []
            chapter_id = issue.get("chapter_id")
            diag.add(Diagnostic(
                kind="canon_contradiction", severity=SEVERITY["canon_contradiction"],
                title=f'{len(violations)} canon violation(s) in "{issue.get("scene_title") or "a scene"}"',
                detail="; ".join(
                    str(v.get("detail") or v.get("rule") or v)[:120] for v in violations[:2]
                ),
                node_ref={"kind": "scene", "id": issue["scene_id"], "title": issue.get("scene_title")},
                # quality-canon focuses by chapter (the scene's chapter), not the scene id.
                focus={"focusChapterId": str(chapter_id)} if chapter_id else None,
                at=issue.get("created_at"),
            ))
    except Exception:  # noqa: BLE001
        logger.warning("diagnostics: canon source failed", exc_info=True)
        diag.warnings.append("canon contradictions could not be read")

    # (2b) broken canon rules (critic lane)
    try:
        if project_id is None:
            raise LookupError("no project")
        rv = await OutlineRepo(pool).rule_violations(project_id)
        for item in rv["items"]:
            rule = item.get("rule_text") or "a rule that no longer exists"
            rule_id = item.get("rule_id")
            diag.add(Diagnostic(
                kind="broken_canon_rule", severity=SEVERITY["broken_canon_rule"],
                title=f'canon rule broken: "{rule[:80]}"',
                detail=(item.get("why") or item.get("span") or "")[:120],
                node_ref={"kind": "scene", "id": item["scene_id"], "title": item.get("scene_title")},
                # quality-canon-rules focuses the RULE (rule_id, LLM text id), not the scene.
                focus={"focusRuleId": str(rule_id)} if rule_id else None,
                at=item.get("created_at"),
            ))
        if rv["capped"]:
            diag.warnings.append(f"showing {len(rv['items'])} of {rv['count']} broken canon rules")
    except Exception:  # noqa: BLE001
        logger.warning("diagnostics: rule-violation source failed", exc_info=True)
        diag.warnings.append("broken canon rules could not be read")

    # (3) open thread debt
    try:
        if project_id is None:
            raise LookupError("no project")
        threads = await NarrativeThreadRepo(pool).list_open(project_id, limit=100)
        if threads:
            diag.add(Diagnostic(
                kind="open_thread_debt", severity=SEVERITY["open_thread_debt"],
                title=f"{len(threads)} open promise(s) still unpaid",
                detail="; ".join((t.summary or "")[:60] for t in threads[:3]),
            ))
    except Exception:  # noqa: BLE001
        logger.warning("diagnostics: thread source failed", exc_info=True)
        diag.warnings.append("open thread debt could not be read")

    # (4) prose-deleted spec nodes
    try:
        from app.services.coverage import compute_prose_deleted

        pd = await compute_prose_deleted(
            book_id, mint_service_bearer(user_id, settings.jwt_secret),
            book=get_book_client(), outline=OutlineRepo(pool),
        )
        if pd.degraded:
            diag.warnings.append(pd.warning)
        else:
            for n in pd.nodes[:cap]:
                diag.add(Diagnostic(
                    kind="prose_deleted_spec_node", severity=SEVERITY["prose_deleted_spec_node"],
                    title=f'"{n.get("title") or "(untitled)"}" points at a chapter that no longer exists',
                    detail=(
                        "the spec SURVIVES a prose delete (IX-13) — re-link it to a chapter, or "
                        "archive it. It is never auto-archived."
                    ),
                    node_ref={"kind": n.get("kind") or "chapter", "id": n["id"], "title": n.get("title")},
                ))
    except Exception:  # noqa: BLE001
        logger.warning("diagnostics: prose-deleted source failed", exc_info=True)
        diag.warnings.append("prose-deleted spec nodes could not be checked")

    # (5) unplanned chapters
    try:
        from app.services.coverage import compute_coverage

        cov = await compute_coverage(
            book_id, mint_service_bearer(user_id, settings.jwt_secret),
            book=get_book_client(), outline=OutlineRepo(pool),
        )
        if cov.degraded:
            diag.warnings.append(
                cov.warning or "the planned-vs-written diff degraded — unplanned chapters UNKNOWN",
            )
        else:
            for ch in cov.unplanned[:cap]:
                diag.add(Diagnostic(
                    kind="unplanned_chapter", severity=SEVERITY["unplanned_chapter"],
                    title=f'chapter "{ch.get("title") or "(untitled)"}" is written but not planned',
                    node_ref={"kind": "chapter", "id": str(ch.get("chapter_id") or ""), "title": ch.get("title")},
                ))
    except Exception:  # noqa: BLE001
        logger.warning("diagnostics: coverage source failed", exc_info=True)
        diag.warnings.append("the planned-vs-written diff could not be computed")

    return diag
