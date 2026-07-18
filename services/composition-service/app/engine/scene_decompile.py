"""Scene decompiler (22 SC6 / B4) — materialize a book's parsed scenes into the
durable spec (`outline_node`, kind='scene').

WHAT THIS IS. A binary acquires source by **decompilation**. `book-service.scenes`
is the INDEX (parse leaves over `chapter.body`, derived by the parser — SC1); the
durable SPEC of a scene's authoring intent is `outline_node` (SC2, anchor inverted).
After a parse, the import tail calls this to upsert one spec node per parse leaf, so
the Studio's SceneRail is no longer empty on an imported book (the empty-rail bug,
fixed at its root — §F1).

SCOPE (23 BA8). The spec tree is Per-book. In the CURRENT schema an `outline_node`
still carries a `project_id` partition key and derives `book_id` from
`composition_work` in-SQL (create_node), so this resolves the book's **canonical
Work** (source_work_id IS NULL) and materializes under it. A book with no canonical
Work yet (never opened in the composer) is guarded **gracefully** and reported —
never silently (per `silent-success-is-a-bug-not-environment`). The full Per-book
re-key that drops `project_id` is B0 (spec 25 M0–M3), a prerequisite of this file.

IDEMPOTENCY (re-run safe). The `decompile_key`/`source` columns + `mappings[]`
write-back are 26 Phase D (D1) — they do NOT exist yet. Here idempotency uses the
natural key of a parse leaf that already lives in composition's own DB:
`(project_id, chapter_id, story_order)` for a kind='scene' node, where
`story_order = scenes.sort_order`. On a re-run the node minted last time is found
and **matched, not duplicated**. A scene already carrying `source_scene_id` (the
index owner back-linked it — SC2) is likewise matched. A per-book advisory xact
lock serializes a concurrent import-retry double-submit (the risk-table guard),
mirroring `OutlineRepo.commit_decomposed_tree`.

WRITE DIRECTION. Composition never writes `book-service.scenes.source_scene_id`
(SC2: the sole writing role is the index owner — the parser + the import tail's
26 IX-12 write-back). This module only reads the index and writes the spec.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx

from app.db.repositories.outline import OutlineRepo
from app.db.repositories.works import WorksRepo
from app.logging_config import trace_id_var

logger = logging.getLogger(__name__)

# Namespace key (arg-1) for the per-book materialize advisory xact lock, distinct
# from _DECOMPOSE_COMMIT_LOCK_NS (0x10AF) so the two never collide on hashtext().
_MATERIALIZE_LOCK_NS = 0x2C6E  # "SC6"-ish sentinel

# book-service getBookScenes clamps `limit` to 100 (parseLimitOffset), so a page
# request larger than that is silently truncated — page exactly at the clamp.
_SCENE_PAGE_LIMIT = 100


@dataclass(frozen=True)
class ParsedScene:
    """One parse leaf from book-service's public scene list, reduced to exactly
    what the decompiler needs. `source_scene_id` is the index→spec back-link
    (SC2): non-null ⇒ this leaf already maps to an existing spec node."""

    chapter_id: UUID
    sort_order: int
    title: str = ""
    source_scene_id: UUID | None = None


@dataclass
class MaterializeResult:
    """Per-scene outcome counts (SC6). `work_resolved=False` with `scenes_total>0`
    is the graceful no-Work guard — reported, never a silent 200-with-zero."""

    book_id: UUID
    work_resolved: bool
    project_id: UUID | None
    scenes_total: int
    created: int
    matched: int
    chapters: int
    skipped_authored: int = 0  # 26 IX-11 — leaves whose spec node a human authored (left alone)
    # 26 IX-12 — the decompiler RETURNS the back-link map; the index owner (import tail)
    # writes `scenes.source_scene_id` from it (composition never writes book-service's DB,
    # SCOPE-2). One entry per leaf that now resolves to a decompiler-owned spec node (a
    # fresh mint OR a re-matched prior decompiled node — so a retry after a failed
    # write-back returns the SAME map). Leaves already carrying `source_scene_id` and
    # human-authored nodes are NOT mapped here (their link is the anchor path, IX-5 r1).
    mappings: list[dict[str, Any]] = field(default_factory=list)
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": str(self.book_id),
            "work_resolved": self.work_resolved,
            "project_id": str(self.project_id) if self.project_id else None,
            "scenes_total": self.scenes_total,
            "created": self.created,
            "matched": self.matched,
            "skipped_authored": self.skipped_authored,
            "mappings": self.mappings,
            "chapters": self.chapters,
            "detail": self.detail,
        }


class BookSceneFetchError(Exception):
    """book-service returned a non-2xx (or transport failed) on the scene read.
    `status` is the HTTP status (502 for a transport error)."""

    def __init__(self, status: int, detail: str | None = None) -> None:
        super().__init__(f"book-service scene read failed: {status} {detail or ''}".strip())
        self.status = status
        self.detail = detail


def _uuid_or_none(v: Any) -> UUID | None:
    if v is None:
        return None
    try:
        return UUID(str(v))
    except (ValueError, TypeError):
        return None


def resolve_canonical_work(works: list) -> Any | None:
    """The book's CANONICAL Work (source_work_id IS NULL) among the marked Works
    (`WorksRepo.resolve_by_book` returns the canonical + any C23 derivatives). At
    most one canonical exists (`uq_composition_work_book`). Derivatives are
    branches of the spec (23 BA8) — imported prose decompiles onto the canonical."""
    for w in works:
        if getattr(w, "source_work_id", None) is None:
            return w
    return None


async def fetch_book_scenes(
    base_url: str, book_id: UUID, bearer: str, *, timeout_s: float = 15.0,
) -> list[ParsedScene]:
    """The thin internal call to book-service's scene list (22 A2: the public,
    VIEW-gated book-wide list `GET /v1/books/{id}/scenes`). It is the only surface
    that carries `source_scene_id` + `title` + `chapter_id` + `sort_order` together,
    book-wide — exactly the decompiler's inputs. Keyset-paged, so this follows
    `next_cursor` to completion. `bearer` is forwarded so book-service enforces the
    VIEW grant on the JWT `sub` (the internal route mints a service bearer for the
    asserted owner; the /v1 mirror forwards the caller's own).

    Raises BookSceneFetchError on any non-200 / transport failure — a partial read
    would understate `scenes_total` and mask the silent-success bug this route
    guards against."""
    out: list[ParsedScene] = []
    headers = {"Authorization": f"Bearer {bearer}"}
    tid = trace_id_var.get()
    if tid:
        headers["X-Trace-Id"] = tid
    url = f"{base_url.rstrip('/')}/v1/books/{book_id}/scenes"
    cursor: str | None = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s)) as client:
        while True:
            params: dict[str, Any] = {"limit": _SCENE_PAGE_LIMIT}
            if cursor:
                params["cursor"] = cursor
            try:
                resp = await client.get(url, headers=headers, params=params)
            except httpx.HTTPError as exc:
                logger.warning("book-service scene read unreachable: %s", exc)
                raise BookSceneFetchError(502, str(exc)) from exc
            if resp.status_code != 200:
                raise BookSceneFetchError(resp.status_code, resp.text[:200])
            body = resp.json()
            for it in body.get("items", []) or []:
                cid = _uuid_or_none(it.get("chapter_id"))
                if cid is None:
                    continue  # a leaf with no chapter can't anchor a spec scene
                out.append(ParsedScene(
                    chapter_id=cid,
                    sort_order=int(it.get("sort_order") or 0),
                    title=(it.get("title") or ""),
                    source_scene_id=_uuid_or_none(it.get("source_scene_id")),
                ))
            cursor = body.get("next_cursor")
            if not cursor:
                break
    return out


async def materialize_scenes(
    pool: Any,
    works: WorksRepo,
    outline: OutlineRepo,
    *,
    book_id: UUID,
    scenes: list[ParsedScene],
    created_by: UUID,
) -> MaterializeResult:
    """The decompiler core (SC6): upsert one kind='scene' `outline_node` per parse
    leaf, keyed on the book, idempotent. `created_by` is a plain actor stamp (25
    M3). Pure over the passed `scenes` list so a test can drive it with a seeded
    index (mock the book client's scene list) without a book-service round-trip."""
    scenes_total = len(scenes)
    chapters = len({sc.chapter_id for sc in scenes})

    # Resolve the book's canonical Work (source_work_id IS NULL). resolve_by_book
    # excludes lazy/pending (null-project) Works, so also try the C16 pending row —
    # decompiling during a knowledge outage must still land (create_node addresses
    # a pending Work by its surrogate id; proven by test_c16_pending_work).
    work = resolve_canonical_work(await works.resolve_by_book(book_id))
    if work is None:
        work = await works.get_pending_for_book(book_id)
    if work is None:
        # Graceful no-Work guard: reported (never a silent 200-with-zero). The book
        # gets a Work when it is first opened in the composer; a re-run then lands.
        return MaterializeResult(
            book_id=book_id, work_resolved=False, project_id=None,
            scenes_total=scenes_total, created=0, matched=0, chapters=chapters,
            detail=(
                "no canonical composition_work for this book yet; open the book in "
                "the composer (or re-run after import creates the Work) to decompile"
            ) if scenes_total else "no parsed scenes to decompile",
        )

    # DECOMP-2: a PENDING Work (project_id NULL — created during a knowledge outage)
    # has only a surrogate-id partition. `WorksRepo.backfill_project` re-keys
    # composition_work when the real project arrives, but NOT outline_node — so scene
    # nodes minted here would be STRANDED off the real partition after backfill (empty
    # rail + orphan rows + a re-mint on the next run). Refuse to mint until the project
    # is real; the import tail re-runs after backfill. An empty rail during a knowledge
    # OUTAGE is an honest degrade (work_resolved reported, never a silent 200-with-zero),
    # not a lost decompile. (The decompiler is the only writer that reaches a pending Work
    # by the book path; the normal composer resolves by project_id — NULL on a pending
    # Work — so it cannot strand rows this way.)
    if work.project_id is None:
        return MaterializeResult(
            book_id=book_id, work_resolved=False, project_id=None,
            scenes_total=scenes_total, created=0, matched=0, chapters=chapters,
            detail=(
                "the book's composition_work is awaiting its knowledge project "
                "(pending backfill); re-run the decompile once it is provisioned"
            ),
        )
    partition = work.project_id  # guaranteed non-null past the pending guard

    created = 0
    matched = 0
    skipped_authored = 0
    mappings: list[dict[str, Any]] = []
    chapter_node_cache: dict[UUID, UUID | None] = {}
    async with pool.acquire() as c:
        async with c.transaction():
            # Serialize concurrent import-retry double-submits per book (the
            # risk-table guard) — a plain check-then-insert would let two retries
            # both see "absent" and double-mint. Released at Tx end.
            await c.execute(
                "SELECT pg_advisory_xact_lock($1, hashtext($2))",
                _MATERIALIZE_LOCK_NS, str(book_id),
            )
            for sc in scenes:
                # Fast path: the index owner already back-linked this leaf to a
                # spec node (SC2). Matched — never re-mint.
                if sc.source_scene_id is not None:
                    matched += 1
                    continue
                # 26 IX-11 idempotency + never-overwrite-authored: a kind='scene' node
                # already at (chapter_id, story_order=sort_order) IS this leaf's spec
                # node. If it was AUTHORED by a human, it is left alone and reported as
                # skipped_authored (a decompiler re-run must never clobber authoring — the
                # provenance-transposed tenancy bug class); a prior 'decompiled' mint is a
                # plain match. Either way the node is never overwritten.
                existing = await c.fetchrow(
                    """
                    SELECT id, source FROM outline_node
                    WHERE project_id = $1 AND kind = 'scene' AND NOT is_archived
                      AND chapter_id = $2 AND story_order = $3
                    LIMIT 1
                    """,
                    partition, sc.chapter_id, sc.sort_order,
                )
                if existing is not None:
                    if existing["source"] == "authored":
                        skipped_authored += 1
                    else:
                        matched += 1
                        # IX-12: a re-matched decompiled node still yields its map entry,
                        # so a retry after a failed write-back returns the SAME mappings.
                        mappings.append({
                            "chapter_id": str(sc.chapter_id),
                            "sort_order": sc.sort_order,
                            "outline_node_id": str(existing["id"]),
                        })
                    continue
                # Parent the scene under its chapter's outline node when one exists
                # (coherent lazy-tree); else a top-level scene (chapter_id still
                # anchors it for the rail/browser, which read by chapter_id).
                if sc.chapter_id not in chapter_node_cache:
                    chapter_node_cache[sc.chapter_id] = await c.fetchval(
                        """
                        SELECT id FROM outline_node
                        WHERE project_id = $1 AND chapter_id = $2
                          AND kind = 'chapter' AND NOT is_archived
                        ORDER BY rank COLLATE "C", id
                        LIMIT 1
                        """,
                        partition, sc.chapter_id,
                    )
                node = await outline.create_node(
                    partition, created_by=created_by, kind="scene",
                    parent_id=chapter_node_cache[sc.chapter_id],
                    chapter_id=sc.chapter_id, title=sc.title,
                    story_order=sc.sort_order, status="outline",
                    # 26 IX-11 — stamp provenance + the idempotency key.
                    source="decompiled",
                    decompile_key=f"{sc.chapter_id}:{sc.sort_order}",
                    conn=c,
                )
                created += 1
                # IX-12 back-link map — the index owner writes scenes.source_scene_id.
                mappings.append({
                    "chapter_id": str(sc.chapter_id),
                    "sort_order": sc.sort_order,
                    "outline_node_id": str(node.id),
                })

    return MaterializeResult(
        book_id=book_id, work_resolved=True, project_id=partition,
        scenes_total=scenes_total, created=created, matched=matched,
        skipped_authored=skipped_authored, mappings=mappings, chapters=chapters,
    )
