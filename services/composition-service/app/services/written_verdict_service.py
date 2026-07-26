"""SC11 amendment Phase 1 — the BACKFILL and the RECONCILE SWEEPER.

Both do the same thing at different cadences: **rebuild the mirror from the PRODUCER's own
predicate.** The producer is book-service, the predicate is `scenes.source_scene_id`, and it always
wins. That is what makes `outline_node.written_scene_id` a regenerable cache rather than a second
source of truth (see the DDL comment in `migrate.py`).

  * BACKFILL — one-shot, for books that existed before the column did. Idempotent (a re-run over an
    already-correct book writes nothing) and RESUMABLE (keyset by book_id, so a crash resumes from
    the last book it finished rather than starting over).
  * SWEEPER — the backstop. Events get dropped: a relay restart mid-flight, an outbox row that
    failed its retries, a chapter deleted while the consumer was down. The sweeper is what makes
    those recoverable instead of permanent, and it is the ONLY reason a cache is safe to trust.

⚠ A DEGRADED READ MUST NOT CLEAR THE MIRROR. If book-service cannot be reached, we do not know
whether the prose exists — and "I could not look" must never be written down as "there is no prose".
`fetch_book_scenes` raises on any non-200 or partial read, and every caller here lets that skip the
book rather than reconcile it to empty. Silently clearing on a failed read would take a fully
written book and render it blank; it is the single worst thing this module could do.
"""
from __future__ import annotations

import logging
from uuid import UUID

import asyncpg

import httpx

from app.db.repositories.written_verdict import WrittenVerdictRepo, links_from_scenes
from app.engine.scene_decompile import BookSceneFetchError
from app.mcp.service_bearer import mint_service_bearer

logger = logging.getLogger(__name__)

_PAGE = 100  # book-service clamps `limit` to 100; page at the clamp.


async def fetch_scene_links(
    base_url: str, book_id: UUID, bearer: str, *,
    chapter_id: UUID | None = None, timeout_s: float = 15.0,
) -> list[dict[str, object]]:
    """book-service's scene rows, carrying the fields THIS mirror needs: `id`, `chapter_id`,
    `source_scene_id`.

    NOT `scene_decompile.fetch_book_scenes` — that reduces each row to a `ParsedScene`, which
    **drops the scene's own `id`**, and the id is the entire point here (`written_scene_id` IS the
    scene id). Reusing it would have stored nothing.

    `chapter_id` scopes the read to ONE chapter, and that is load-bearing for Phase 2: the event is
    per-chapter, and re-walking the whole book's scene index on every publish would reintroduce
    exactly the page-walk this amendment exists to remove. The book-wide form is for the
    backfill/sweeper only, where the walk is paid once, offline.

    Raises BookSceneFetchError on ANY non-200 or transport failure. A partial read must never be
    mistaken for "there is no prose" — see the module note.
    """
    out: list[dict[str, object]] = []
    headers = {"Authorization": f"Bearer {bearer}"}
    url = f"{base_url.rstrip('/')}/v1/books/{book_id}/scenes"
    cursor: str | None = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s)) as client:
        while True:
            params: dict[str, object] = {"limit": _PAGE}
            if chapter_id:
                params["chapter_id"] = str(chapter_id)
            if cursor:
                params["cursor"] = cursor
            try:
                resp = await client.get(url, headers=headers, params=params)
            except httpx.HTTPError as exc:
                raise BookSceneFetchError(502, str(exc)) from exc
            if resp.status_code != 200:
                raise BookSceneFetchError(resp.status_code, resp.text[:200])
            body = resp.json()
            for it in body.get("items", []) or []:
                # ⚠ book-service names the scene's own id `scene_id`, NOT `id`. I read `id`, got
                # None for every row, silently produced ZERO links — and every unit test still
                # passed, because they fed dicts with the `"id"` key I had invented. The mirror
                # reconciled cleanly to empty on every publish. Only the live smoke caught it:
                # the column simply never stamped. (`id` is kept as a fallback so a future
                # response shape that DOES use it cannot silently regress to zero links again.)
                out.append({
                    "id": it.get("scene_id") or it.get("id"),
                    "chapter_id": it.get("chapter_id"),
                    "source_scene_id": it.get("source_scene_id"),
                })
            cursor = body.get("next_cursor")
            if not cursor:
                break
    return out


async def reconcile_one_chapter(
    pool: asyncpg.Pool, book_id: UUID, chapter_id: UUID, *, book_base_url: str, bearer: str,
) -> dict[str, int]:
    """The EVENT path (Phase 2): `chapter.scenes_linked` arrives → re-read THAT chapter → reconcile.

    One chapter, one bounded read. Raises on a degraded read so the consumer can NACK/retry rather
    than reconcile the chapter to empty — "I could not look" is not "there is no prose"."""
    scenes = await fetch_scene_links(book_base_url, book_id, bearer, chapter_id=chapter_id)
    links = links_from_scenes(scenes).get(chapter_id, [])
    return await WrittenVerdictRepo(pool).reconcile_chapter(book_id, chapter_id, links)


async def reconcile_book(
    pool: asyncpg.Pool, book_id: UUID, *, book_base_url: str, bearer: str,
) -> dict[str, int]:
    """Rebuild one book's written-verdict from book-service's scene index.

    Reconciles EVERY chapter that has spec nodes — including the ones with no scenes left, which is
    how a deleted chapter's nodes get cleared. Raises BookSceneFetchError if the index cannot be
    read in full: a partial read would understate the truth and clear nodes that ARE written.
    """
    scenes = await fetch_scene_links(book_base_url, book_id, bearer)  # raises on partial/failed read
    by_chapter = links_from_scenes(scenes)

    repo = WrittenVerdictRepo(pool)

    # WHICH CHAPTERS TO VISIT — and this is not obvious.
    #
    # Not "chapters with spec nodes" (my first cut): the CLEAR is keyed on `written_chapter_id`, and
    # a node's own `chapter_id` is NULL while it is merely PLANNED. Visiting by spec chapter_id
    # would miss exactly the nodes the mirror currently claims.
    #
    # The correct set is the UNION of:
    #   * every chapter book-service returned scenes for  — reconcile against the truth;
    #   * every chapter the MIRROR currently claims backs a node — because if book-service no longer
    #     returns it (the prose was deleted, the whole chapter trashed), nothing else would ever
    #     visit it and its nodes would keep claiming prose that is gone. FOREVER.
    async with pool.acquire() as c:
        rows = await c.fetch(
            """
            SELECT DISTINCT written_chapter_id FROM outline_node
             WHERE book_id = $1 AND written_chapter_id IS NOT NULL
            """,
            book_id,
        )
    mirrored_chapters = {r["written_chapter_id"] for r in rows}

    totals = {"linked": 0, "cleared": 0, "chapters": 0}
    for chapter_id in mirrored_chapters | set(by_chapter):
        res = await repo.reconcile_chapter(book_id, chapter_id, by_chapter.get(chapter_id, []))
        totals["linked"] += res["linked"]
        totals["cleared"] += res["cleared"]
        totals["chapters"] += 1

    # Every genuinely-written node has just been re-stamped with its owning chapter from
    # book-service's answer. Anything STILL claiming prose with no owning chapter is unattributable
    # garbage that no chapter-scoped CLEAR could ever reach — so the book-wide reconcile, which is
    # the only caller that holds the whole truth, is the one that heals it. Without this, such a row
    # would be permanently stale, and the mirror would not be regenerable.
    totals["cleared"] += await repo.clear_orphans(book_id)
    return totals


async def backfill_all(
    pool: asyncpg.Pool, *, book_base_url: str, jwt_secret: str, page: int = 200,
) -> dict[str, int]:
    """Walk every book with spec nodes and rebuild its mirror. Idempotent + resumable.

    A book whose index cannot be read is SKIPPED and counted, never cleared (see the module note).
    The run reports `failed` so a caller can see the gap instead of reading a clean-looking total
    as completeness — a silent partial backfill is how a cache quietly becomes wrong.
    """
    repo = WrittenVerdictRepo(pool)
    stats = {"books": 0, "linked": 0, "cleared": 0, "failed": 0}
    after: UUID | None = None

    while True:
        books = await repo.books_with_spec(after=after, limit=page)
        if not books:
            break
        for book_id in books:
            owner = await _owner_of(pool, book_id)
            if owner is None:
                stats["failed"] += 1
                logger.warning("written-verdict backfill: no owner for book %s — skipped", book_id)
                continue
            try:
                res = await reconcile_book(
                    pool, book_id,
                    book_base_url=book_base_url,
                    bearer=mint_service_bearer(owner, jwt_secret),
                )
            except BookSceneFetchError:
                # UNKNOWN, not empty. Leave the mirror as it was; the sweeper retries.
                stats["failed"] += 1
                logger.warning("written-verdict backfill: book %s unreadable — left UNTOUCHED", book_id)
                continue
            stats["books"] += 1
            stats["linked"] += res["linked"]
            stats["cleared"] += res["cleared"]
        after = books[-1]  # keyset: resume from the last book FINISHED

    return stats


async def _owner_of(pool: asyncpg.Pool, book_id: UUID) -> UUID | None:
    """The Work's actor, whose identity the service bearer asserts to book-service so the VIEW
    grant is enforced on a real user — never a bare internal token that bypasses it."""
    async with pool.acquire() as c:
        return await c.fetchval(
            "SELECT created_by FROM composition_work WHERE book_id = $1 LIMIT 1", book_id,
        )
