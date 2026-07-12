"""27 V2-E — THE LINK STEP: the compiler's output actually becomes spec rows.

BPS-18/DA-13's law: *an emitted artifact with no linker is a bug.* Before this, PlanForge produced
a `planning_package` and nothing on earth turned it into `structure_node` / `outline_node` rows —
the compiler compiled into the void. A compile that materialises nothing IS the silent-success bug,
at compile scale (PF-8).

Two halves:

  (a) SKELETON LINK — `link_outline_skeleton`, run INLINE at `compile()`. Deterministic, no LLM,
      composition-local: the package's arc → `structure_node(kind='arc')`, its chapters →
      `outline_node(kind='chapter')` under that arc.
  (b) SCENE LINK — `link_scene_plan`, run at pass-6/7 acceptance: the healed scenes →
      `outline_node(kind='scene')` under their chapter, carrying title/synopsis/tension/cast.

Four rules, each of which exists because its absence produced a real bug class:

  • **IDEMPOTENCY IS RUN-SCOPED** (PF-10). The upsert conflicts on
    `(book_id, plan_run_id, plan_arc_id|plan_event_id)`, and the `ON CONFLICT` **repeats the partial
    index's WHERE clause verbatim** — Postgres will not use a partial unique index for arbitration
    unless the inference predicate matches it (`postgres-partial-index-on-conflict-predicate-must-
    match`). Event ids are 100% stable WITHIN a run and 0% stable ACROSS re-proposes (POC 03), which
    is exactly why the key is run-scoped and not bare `event_id`.

  • **A RE-LINK NEVER SILENTLY RECLAIMS AN AUTHOR'S EDIT** (PF-11). Every link records the `version`
    of each row it wrote. On re-link, a row whose CURRENT version exceeds the one we last wrote has
    been touched by a human since — it keeps its authored fields and gets structural linkage only,
    and is reported as `preserved_user_edit`. Overwriting it would be the write-only bug inverted:
    the generator silently winning over the human.

  • **THE WRITER STAMPS `source='planforge'`** (E2b). That enum value is reserved in
    `outline_node_source_check` / `structure_node_source_check` and, until now, written by NOBODY —
    a reserved-but-never-written value is the write-only bug class. It is also load-bearing: the
    decompiler's preservation predicate (26 IX-11) protects `source='authored'` rows, and it can
    only tell PlanForge's mints apart from a human's if the stamp actually lands.

  • **ZERO NODES LINKED IS AN ERROR, NEVER A SILENT 200** (E4/PF-8a). `success: false`. A link that
    reports OK having written nothing is the exact failure this whole step exists to make impossible.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import asyncpg

from app.engine.chapter_gen import STORY_ORDER_CHAPTER_STRIDE

logger = logging.getLogger(__name__)

#: PF-11's "we have no record of what we wrote" sentinel. See the guard comment in the chapter loop.
_NO_PRIOR = 2_147_483_647


def _settled(current_version: int, guard: int) -> bool:
    """Did a HUMAN block that skipped update (True), or was it a no-op (False)?

    The row's version alone decides it, exactly and without comparing any content. The DO UPDATE's
    WHERE is `version <= guard AND <something differs>`. So if the update was skipped and the row's
    version is PAST our guard, it was the version clause that blocked it — a human is ahead of us.
    If the version is at-or-below the guard, that clause passed, so only the content clause can have
    blocked it — nothing differed.

    With no prior record the guard is `_NO_PRIOR`, which no real version can exceed, so a row we have
    never written can never be mistaken for a preserved one.
    """
    return current_version > guard


@dataclass
class TargetCounts:
    """Per-target outcome counts. ALWAYS returned and persisted (E4) — a linker that reports only a
    total cannot tell you it updated nothing and created nothing."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    preserved_user_edit: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "preserved_user_edit": self.preserved_user_edit,
        }

    @property
    def touched(self) -> int:
        return self.created + self.updated + self.unchanged + self.preserved_user_edit


@dataclass
class LinkReport:
    """The `link_report` artifact (E4/PF-10/PF-11)."""

    run_id: str
    target: str                      # "skeleton" | "scene_plan"
    success: bool = True
    arcs: TargetCounts = field(default_factory=TargetCounts)
    chapters: TargetCounts = field(default_factory=TargetCounts)
    scenes: TargetCounts = field(default_factory=TargetCounts)
    #: PF-11 — the version of every node we wrote, so the NEXT re-link can tell whether a human has
    #: touched it since. Without this the preservation check has nothing to compare against.
    linked_versions: dict[str, int] = field(default_factory=dict)
    #: PF-10 — cross-run AND cross-axis near-duplicates. SURFACED, never auto-merged: a title match
    #: is a heuristic, and silently merging two arcs on a heuristic is unrecoverable.
    possible_duplicates: list[dict[str, Any]] = field(default_factory=list)
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "target": self.target,
            "success": self.success,
            "arcs": self.arcs.to_dict(),
            "chapters": self.chapters.to_dict(),
            "scenes": self.scenes.to_dict(),
            "linked_versions": self.linked_versions,
            "possible_duplicates": self.possible_duplicates,
            "detail": self.detail,
        }


class LinkError(Exception):
    """Zero nodes linked (E4). Carries the report so the caller can persist it — a failure the user
    cannot inspect is barely better than a silent success."""

    def __init__(self, report: LinkReport) -> None:
        super().__init__(report.detail or "link produced no nodes")
        self.report = report


# ── the two upserts ───────────────────────────────────────────────────────────
#
# The ON CONFLICT target REPEATS the partial index's WHERE clause. This is not decoration: Postgres
# refuses to infer a partial unique index for arbitration unless the predicate matches, and the
# statement fails at runtime with "no unique or exclusion constraint matching the ON CONFLICT
# specification" — which, in a linker, means every re-link inserts a duplicate instead.

# The arc is PF-11-guarded exactly like the chapters. An earlier version was not, on the reasoning
# that "an arc carries no authored prose — only a title and a summary the plan owns". That premise
# is FALSE: `PATCH /arcs/{id}` (routers/arc.py) patches `title`/`summary` through StructureRepo with
# If-Match OCC — arcs are a first-class authored surface. Unguarded, every compile silently reverted
# a user's arc rename; and the unconditional `version + 1` staled their held ETag, so their NEXT arc
# edit 412'd, and it invalidated the arc-conformance manifest's `structure_node_version` on every
# compile whether or not the arc had changed.
_UPSERT_ARC = """
INSERT INTO structure_node
  (created_by, book_id, parent_id, kind, depth, rank, title, summary, status,
   source, plan_run_id, plan_arc_id)
-- `status` shares outline_node's set (empty|outline|drafting|done) — NOT 'active'. A freshly
-- linked arc is PLANNED but unwritten, which is exactly `outline`. (Caught by the live smoke:
-- 'active' is the WORK's status vocabulary, and reusing it here violated
-- structure_node_status_check. A unit suite that never touches the DB cannot see this.)
VALUES ($1, $2, NULL, 'arc', 0, $3, $4, $5, 'outline', 'planforge', $6, $7)
ON CONFLICT (book_id, plan_run_id, plan_arc_id)
  WHERE plan_run_id IS NOT NULL AND plan_arc_id IS NOT NULL AND NOT is_archived
DO UPDATE SET
  title      = EXCLUDED.title,
  summary    = EXCLUDED.summary,
  updated_at = now(),
  version    = structure_node.version + 1
WHERE structure_node.version <= $8
  -- …and only bump when something ACTUALLY changed, so an unchanged re-compile does not stale a
  -- user's held ETag for nothing.
  AND (structure_node.title IS DISTINCT FROM EXCLUDED.title
       OR structure_node.summary IS DISTINCT FROM EXCLUDED.summary)
RETURNING id, version, (xmax = 0) AS inserted
"""

# The DO UPDATE's WHERE carries BOTH guards, and a skipped update means one of exactly two things —
# which the caller tells apart from the row's version alone (see `_settled` below):
#
#   1. PF-11 preservation. We only overwrite the authored fields when the row's CURRENT version is
#      the one we last wrote. If a human has edited it since, `version` has moved PAST our guard, the
#      update is skipped, their words stand, and we still record the linkage.
#   2. A no-op. If nothing we would write actually differs, we do not write — so we do not bump
#      `version`. Without this clause every compile bumped every chapter and scene even when the plan
#      was byte-identical, which (a) staled every ETag the user was holding, so their NEXT edit
#      412'd, and (b) made `unchanged` structurally unreachable in the report — a counter that can
#      never be non-zero is a lying metric. The arc had this clause; the chapters and scenes did not,
#      and the 5-compile live smoke showed it: `updated: 1, unchanged: 0` on every single no-op
#      compile, with Event 1 climbing to v4.
#
# The DISTINCT list must cover EVERY column the DO UPDATE SETs, or a real change to an uncovered
# column would be silently skipped as a no-op.
_UPSERT_CHAPTER = """
INSERT INTO outline_node
  (created_by, project_id, book_id, parent_id, kind, rank, title, synopsis, status,
   structure_node_id, story_order, chapter_id, source, plan_run_id, plan_event_id)
VALUES ($1, $2, $3, NULL, 'chapter', $4, $5, $6, 'outline', $7, $8, NULL,
        'planforge', $9, $10)
ON CONFLICT (book_id, plan_run_id, plan_event_id)
  WHERE plan_run_id IS NOT NULL AND plan_event_id IS NOT NULL AND NOT is_archived
DO UPDATE SET
  title             = EXCLUDED.title,
  synopsis          = EXCLUDED.synopsis,
  structure_node_id = EXCLUDED.structure_node_id,
  story_order       = EXCLUDED.story_order,
  updated_at        = now(),
  version           = outline_node.version + 1
WHERE outline_node.version <= $11
  AND (outline_node.title             IS DISTINCT FROM EXCLUDED.title
    OR outline_node.synopsis          IS DISTINCT FROM EXCLUDED.synopsis
    OR outline_node.structure_node_id IS DISTINCT FROM EXCLUDED.structure_node_id
    OR outline_node.story_order       IS DISTINCT FROM EXCLUDED.story_order)
RETURNING id, version, (xmax = 0) AS inserted
"""

_UPSERT_SCENE = """
INSERT INTO outline_node
  (created_by, project_id, book_id, parent_id, kind, rank, title, synopsis, status,
   tension, present_entity_ids, story_order, chapter_id, source, plan_run_id, plan_event_id)
VALUES ($1, $2, $3, $4, 'scene', $5, $6, $7, 'outline', $8, $9, $10, $11,
        'planforge', $12, $13)
ON CONFLICT (book_id, plan_run_id, plan_event_id)
  WHERE plan_run_id IS NOT NULL AND plan_event_id IS NOT NULL AND NOT is_archived
DO UPDATE SET
  title              = EXCLUDED.title,
  synopsis           = EXCLUDED.synopsis,
  tension            = EXCLUDED.tension,
  present_entity_ids = EXCLUDED.present_entity_ids,
  parent_id          = EXCLUDED.parent_id,
  story_order        = EXCLUDED.story_order,
  updated_at         = now(),
  version            = outline_node.version + 1
WHERE outline_node.version <= $14
  AND (outline_node.title              IS DISTINCT FROM EXCLUDED.title
    OR outline_node.synopsis           IS DISTINCT FROM EXCLUDED.synopsis
    OR outline_node.tension            IS DISTINCT FROM EXCLUDED.tension
    OR outline_node.present_entity_ids IS DISTINCT FROM EXCLUDED.present_entity_ids
    OR outline_node.parent_id          IS DISTINCT FROM EXCLUDED.parent_id
    OR outline_node.story_order        IS DISTINCT FROM EXCLUDED.story_order)
RETURNING id, version, (xmax = 0) AS inserted
"""

#: PF-10 — a title-matched node from a DIFFERENT run, or (E2b's cross-axis widening) one the
#: DECOMPILER minted from imported prose. An imported-then-replanned book will legitimately have
#: both. We surface it; we never merge it.
_FIND_DUPES = """
SELECT id, title, source, plan_run_id
FROM outline_node
WHERE book_id = $1 AND kind = $2 AND NOT is_archived
  AND lower(btrim(title)) = ANY($3::text[])
  AND (plan_run_id IS DISTINCT FROM $4 OR source = 'decompiled')
"""


def _rank(i: int) -> str:
    """A dense, byte-ordered rank. The linker writes a whole plan at once, so it does not need the
    fractional-rank machinery that exists for INSERT-BETWEEN; it needs a stable total order that
    sorts correctly under `COLLATE "C"` (which is how every keyset read orders)."""
    return f"m{i:06d}"


class PlanLinkService:
    """Materialises a plan run's artifacts into spec rows."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def _duplicates(
        self, conn: asyncpg.Connection, book_id: UUID, kind: str,
        titles: list[str], run_id: UUID,
    ) -> list[dict[str, Any]]:
        if not titles:
            return []
        rows = await conn.fetch(
            _FIND_DUPES, book_id, kind,
            [t.strip().lower() for t in titles if t and t.strip()], run_id,
        )
        return [
            {
                "node_id": str(r["id"]),
                "title": r["title"],
                "source": r["source"],
                "other_run_id": str(r["plan_run_id"]) if r["plan_run_id"] else None,
                # Named, so the report reads as a question rather than an accusation.
                "why": (
                    "a decompiled node with the same title — this book was imported and is now "
                    "being re-planned"
                    if r["source"] == "decompiled"
                    else "a node with the same title from a different plan run"
                ),
            }
            for r in rows
        ]

    async def link_outline_skeleton(
        self,
        *,
        created_by: UUID,
        book_id: UUID,
        project_id: UUID,
        run_id: UUID,
        package: dict[str, Any],
        prior_versions: dict[str, int] | None = None,
    ) -> LinkReport:
        """(a) The SKELETON — arc + chapters. Deterministic, no LLM. Runs inline at compile().

        `prior_versions` is the previous `link_report.linked_versions`: the versions we last wrote.
        A row now ABOVE its recorded version has been edited by a human since, and PF-11 says we
        keep their words. Absent (a first link) ⇒ nothing to preserve.
        """
        prior = prior_versions or {}
        report = LinkReport(run_id=str(run_id), target="skeleton")

        arc_id = str(package.get("arc_id") or "").strip()
        chapters = [c for c in (package.get("chapters") or []) if isinstance(c, dict)]
        if not arc_id or not chapters:
            report.success = False
            report.detail = (
                "the package has no arc_id / no chapters — there is nothing to link. "
                "A compile that materialises nothing is a failure, not an empty success."
            )
            raise LinkError(report)

        # The arc's HUMAN title (compile.py emits `arc_title`). An earlier version used `premise`,
        # which is a 500-char multi-line blob ("Arc: ...\nTheme: ...\nKey events:\n- ...") - and that
        # is what the Plan Hub, the arc picker and the navigator all rendered as the arc's NAME.
        # `premise` is the SUMMARY; the title is the title.
        title = str(package.get("arc_title") or arc_id)[:500]
        summary = str(package.get("premise") or "")[:2000]

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # ARC -> structure_node. PF-11-guarded like the chapters (see _UPSERT_ARC).
                arc_key = f"arc:{arc_id}"
                arc_guard = prior.get(arc_key, _NO_PRIOR)
                arc_row = await conn.fetchrow(
                    _UPSERT_ARC, created_by, book_id, _rank(0), title,
                    summary, run_id, arc_id, arc_guard,
                )
                if arc_row is None:
                    # The DO UPDATE's WHERE was false. Two reasons, both meaning "no write happened,
                    # and that is correct": a human's version is ahead of ours (their arc name
                    # stands, PF-11), or nothing changed (we deliberately did not bump the version).
                    # Either way we must NOT lose the row: we need its id for the chapters, and its
                    # version MUST carry forward. Dropping the key here is exactly HIGH-1 - the next
                    # link would see no prior version, use the open sentinel, and clobber the human
                    # on the compile after that.
                    existing = await conn.fetchrow(
                        """
                        SELECT id, version FROM structure_node
                        WHERE book_id = $1 AND plan_run_id = $2 AND plan_arc_id = $3
                          AND NOT is_archived
                        """,
                        book_id, run_id, arc_id,
                    )
                    if existing is None:
                        report.success = False
                        report.detail = "the arc upsert matched no row"
                        raise LinkError(report)
                    arc_row = existing
                    # An earlier version told the two apart by COMPARING CONTENT. The version is the
                    # truth and the content is only a proxy for it — a human who edited and reverted
                    # was mislabelled "unchanged" and handed their row straight back.
                    if _settled(existing["version"], arc_guard):
                        report.arcs.preserved_user_edit += 1
                        # A preserve is NOT a write. Keep the guard we had, or the next compile would
                        # read the human's version as ours and overwrite them one compile later.
                        report.linked_versions[arc_key] = arc_guard
                    else:
                        report.arcs.unchanged += 1
                        # An UNCHANGED row genuinely IS still at the version we last wrote.
                        report.linked_versions[arc_key] = existing["version"]
                    structure_node_id = arc_row["id"]
                else:
                    if arc_row["inserted"]:
                        report.arcs.created += 1
                    else:
                        report.arcs.updated += 1
                    structure_node_id = arc_row["id"]
                    report.linked_versions[arc_key] = arc_row["version"]

                # CHAPTERS → outline_node. story_order uses the same strided global axis the whole
                # Hub reads (chapter n at n * 1000), so a scene can slot in at +i beneath it.
                titles: list[str] = []
                for i, ch in enumerate(chapters):
                    event_id = str(ch.get("event_id") or f"ch{i + 1}")
                    ordinal = int(ch.get("ordinal") or (i + 1))
                    ch_title = str(ch.get("title") or "")[:500]
                    titles.append(ch_title)
                    key = f"chapter:{event_id}"
                    last = prior.get(key)
                    # The PF-11 guard. `DO UPDATE ... WHERE version <= guard` fires only if the row
                    # is still at the version WE last wrote; if a human has edited it since, its
                    # version has moved past the guard, the update is skipped, and their words stand.
                    #
                    # Why an open sentinel is SAFE when we have no prior record: the conflict target
                    # is `(book_id, plan_run_id, plan_event_id)` with plan_run_id = THIS run. So a
                    # conflict can only ever hit a row THIS RUN linked before — never a human's node,
                    # never another run's. Missing bookkeeping therefore means "we lost our own
                    # report", and overwriting our own previous link is the correct default.
                    # On the INSERT path the WHERE is not evaluated at all.
                    guard = last if last is not None else _NO_PRIOR
                    row = await conn.fetchrow(
                        _UPSERT_CHAPTER, created_by, project_id, book_id, _rank(i), ch_title,
                        str(ch.get("synopsis") or "")[:20000], structure_node_id,
                        ordinal * STORY_ORDER_CHAPTER_STRIDE, run_id, event_id, guard,
                    )
                    if row is None:
                        # DO UPDATE ... WHERE was false: either a human is ahead of us (PF-11 — their
                        # words stand) or nothing differed. Read the version back to tell which, and
                        # in BOTH cases record it: this ledger is what the next link compares
                        # against, and dropping the key means the link after that sees "no prior
                        # record", uses the open sentinel, and overwrites the human. (HIGH-1.)
                        existing = await conn.fetchrow(
                            "SELECT version FROM outline_node WHERE book_id = $1"
                            " AND plan_run_id = $2 AND plan_event_id = $3 AND NOT is_archived",
                            book_id, run_id, event_id,
                        )
                        if existing is None:
                            report.success = False
                            report.detail = f"the chapter upsert matched no row ({event_id})"
                            raise LinkError(report)
                        if _settled(existing["version"], guard):
                            report.chapters.preserved_user_edit += 1
                            # Carry the PRIOR guard forward UNCHANGED — the version we last WROTE,
                            # not the version the row is at NOW.
                            #
                            # Recording the current version was my first fix and it was WRONG, and
                            # the LIVE SMOKE caught it where the unit test could not: on the next
                            # compile the guard equalled the human's version, `version <= guard` was
                            # TRUE, the update fired — the human survived exactly one more compile.
                            #
                            # The ledger means "the version this row had immediately after OUR last
                            # write". A preserve is not a write, so that value does not change. The
                            # human keeps the row until they explicitly hand it back.
                            report.linked_versions[key] = guard
                        else:
                            report.chapters.unchanged += 1
                            report.linked_versions[key] = existing["version"]
                        continue
                    if row["inserted"]:
                        report.chapters.created += 1
                    else:
                        report.chapters.updated += 1
                    report.linked_versions[key] = row["version"]

                # ADVISORY. It only produces `possible_duplicates`, so a failure here must never
                # roll back the arc + chapters we just successfully wrote.
                try:
                    report.possible_duplicates = await self._duplicates(
                        conn, book_id, "chapter", titles, run_id,
                    )
                except Exception:  # noqa: BLE001 - report-only; degrade, never lose the link
                    logger.warning("duplicate probe failed; link stands", exc_info=True)

        if report.chapters.touched == 0:
            report.success = False
            report.detail = "zero chapters linked"
            raise LinkError(report)
        return report

    async def link_scene_plan(
        self,
        *,
        created_by: UUID,
        book_id: UUID,
        project_id: UUID,
        run_id: UUID,
        scenes_by_event: dict[str, list[dict[str, Any]]],
        prior_versions: dict[str, int] | None = None,
    ) -> LinkReport:
        """(b) The SCENE link — the healed `scene_plan` becomes scene nodes under their chapters.

        `scenes_by_event` maps the chapter's `event_id` → its ordered scenes. Each scene carries
        title / synopsis / tension / `present_entity_ids` (glossary ids, already resolved by pass 6's
        roster join — this step does not invent entities).

        The scene's provenance id is `"{event_id}:{ordinal}"` (PF-9), which is what makes a re-link
        update the same scene rather than minting a second one.
        """
        prior = prior_versions or {}
        report = LinkReport(run_id=str(run_id), target="scene_plan")

        if not scenes_by_event:
            report.success = False
            report.detail = "the scene plan is empty — nothing to link"
            raise LinkError(report)

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # The chapters THIS RUN linked. A scene may only hang under a chapter of the same
                # run: linking it under some other run's chapter would silently graft this plan onto
                # a different one.
                chap_rows = await conn.fetch(
                    """
                    SELECT id, plan_event_id, chapter_id, story_order
                    FROM outline_node
                    WHERE book_id = $1 AND plan_run_id = $2 AND kind = 'chapter'
                      AND NOT is_archived
                    """,
                    book_id, run_id,
                )
                by_event = {r["plan_event_id"]: r for r in chap_rows}
                if not by_event:
                    report.success = False
                    report.detail = (
                        "no chapters are linked for this run — run the skeleton link first"
                    )
                    raise LinkError(report)

                titles: list[str] = []
                for event_id, scenes in scenes_by_event.items():
                    chap = by_event.get(event_id)
                    if chap is None:
                        # The plan named an event with no linked chapter. Skipped, and COUNTED —
                        # a scene silently dropped is a scene the author never learns they lost.
                        report.scenes.skipped += len(scenes)
                        continue
                    for i, sc in enumerate(scenes):
                        if not isinstance(sc, dict):
                            report.scenes.skipped += 1
                            continue
                        plan_event_id = f"{event_id}:{i + 1}"
                        sc_title = str(sc.get("title") or "")[:500]
                        titles.append(sc_title)
                        present = [
                            UUID(str(e)) for e in (sc.get("present_entity_ids") or [])
                            if _is_uuid(e)
                        ]
                        # `isinstance(True, int)` is True, so a JSON `true` would store 1. And an
                        # out-of-range value would land in a column whose consumers assume 0..100.
                        tension = sc.get("tension")
                        if isinstance(tension, bool) or not isinstance(tension, (int, float)):
                            tension = None
                        else:
                            tension = max(0, min(100, int(tension)))
                        skey = f"scene:{plan_event_id}"
                        last = prior.get(skey)
                        guard = last if last is not None else _NO_PRIOR
                        row = await conn.fetchrow(
                            _UPSERT_SCENE, created_by, project_id, book_id, chap["id"],
                            _rank(i), sc_title, str(sc.get("synopsis") or "")[:20000],
                            tension, present,
                            # The scene's slot on the SAME strided global axis its chapter sits on.
                            # `+ i`, ZERO-BASED — the chapter sits exactly at its own scene 0. Every
                            # other writer uses this convention (`_renumber_scene_story_order`'s
                            # `row_number() - 1`, `resync_reading_order`, plan.py's `enumerate`), so
                            # `+ i + 1` put linker-minted scenes one slot ABOVE everyone else's: the
                            # first scene drag or book reorder would renumber them all down by one,
                            # shifting the packer's strictly-prior cutoffs and the canon-rule windows
                            # that key on those exact integers. Two conventions on one column is a
                            # bug this repo has already shipped once.
                            (chap["story_order"] or 0) + i,
                            # `chapter_id` inherits the chapter's — NULL until bootstrap [A] stamps
                            # it. NULL is legal now, and means "planned, not yet written" (the M6.1
                            # CHECK swap is what makes this insert possible at all).
                            chap["chapter_id"],
                            run_id, plan_event_id, guard,
                        )
                        if row is None:
                            # See the chapter branch. The version MUST carry forward either way, or
                            # the human's edit is reclaimed one compile later (HIGH-1); and a
                            # preserve carries the PRIOR guard, not the row's current version.
                            existing = await conn.fetchrow(
                                "SELECT version FROM outline_node WHERE book_id = $1"
                                " AND plan_run_id = $2 AND plan_event_id = $3 AND NOT is_archived",
                                book_id, run_id, plan_event_id,
                            )
                            if existing is None:
                                report.success = False
                                report.detail = (
                                    f"the scene upsert matched no row ({plan_event_id})"
                                )
                                raise LinkError(report)
                            if _settled(existing["version"], guard):
                                report.scenes.preserved_user_edit += 1
                                report.linked_versions[skey] = guard
                            else:
                                report.scenes.unchanged += 1
                                report.linked_versions[skey] = existing["version"]
                            continue
                        if row["inserted"]:
                            report.scenes.created += 1
                        else:
                            report.scenes.updated += 1
                        report.linked_versions[skey] = row["version"]

                try:
                    report.possible_duplicates = await self._duplicates(
                        conn, book_id, "scene", titles, run_id,
                    )
                except Exception:  # noqa: BLE001 - report-only; degrade, never lose the link
                    logger.warning("duplicate probe failed; link stands", exc_info=True)

        if report.scenes.touched == 0:
            report.success = False
            report.detail = "zero scenes linked"
            raise LinkError(report)
        return report


def _is_uuid(v: Any) -> bool:
    try:
        UUID(str(v))
        return True
    except (ValueError, AttributeError, TypeError):
        return False
