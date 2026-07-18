"""Thin internal client for book-service reads the translation worker needs."""
from loreweave_internal_client import build_internal_client

from .config import settings

# #36 — the extraction COST estimate used to feed the windowing-aware planner a flat
# `text_length: 8000` for EVERY chapter, so it never windowed and undercounted LLM calls
# on large chapters. We now fetch the REAL per-chapter size (book-service's
# `word_count_estimate`, = octet_length(body)/5) and pass it through.
_DEFAULT_CHAPTER_TEXT_LENGTH = 8000   # legacy assumption — used when a size is unknown
_WORD_COUNT_TO_TEXT_LENGTH = 5        # reconstruct ~byte length (octet_length) as a char proxy;
                                      # conservative for CJK (bytes > chars) → never UNDER-windows
_CHAPTER_LIST_PAGE = 200
_CHAPTER_LIST_MAX_PAGES = 50          # hard bound: ≤10k chapters scanned, even on a malformed book


async def book_owns_chapter(book_id, chapter_id) -> bool:
    """Authoritative chapter→book binding check (book-service is the single
    authority for chapter ownership). Returns True iff `chapter_id` is an active
    chapter of `book_id`.

    Used by the Tier-W confirm spine to assert each requested chapter actually
    belongs to the book bound in the confirm token (`claims.resource_id`) — a
    confirm payload must NOT be able to retarget chapters under a DIFFERENT book
    than the one whose grant was (re-)authorized. The blocks endpoint validates
    `chapter_id AND book_id` server-side (`SELECT EXISTS(... WHERE id=? AND
    book_id=? AND lifecycle_state='active')`) and 404s when unbound — so a 2xx is
    a positive binding proof, a 404 a clean "not bound".

    Fail-CLOSED: a transport error / 5xx raises (the caller must NOT spend on an
    unverifiable binding); only a definitive 404 returns False."""
    url = (
        f"{settings.book_service_internal_url}"
        f"/internal/books/{book_id}/chapters/{chapter_id}/blocks"
    )
    # W5 (ephemeral wave): shared factory bakes X-Internal-Token + JSON.
    async with build_internal_client(
        settings.book_service_internal_url,
        internal_token=settings.internal_service_token, timeout_s=10,
    ) as client:
        r = await client.get(url)
        if r.status_code == 404:
            return False
        r.raise_for_status()
        return True


async def get_chapter_blocks(book_id, chapter_id) -> list[dict]:
    """T2: the chapter's extracted blocks (ordered, with content_hash) for the
    segmenter. Returns [] for a chapter with no blocks."""
    url = (
        f"{settings.book_service_internal_url}"
        f"/internal/books/{book_id}/chapters/{chapter_id}/blocks"
    )
    async with build_internal_client(
        settings.book_service_internal_url,
        internal_token=settings.internal_service_token, timeout_s=30,
    ) as client:
        r = await client.get(url)
        # A chapter present in chapter_translations but absent in book-service (deleted /
        # orphaned translation row) → no blocks → no segments. Treat 404 as empty rather
        # than raising, so a backfill / finalize-hook rebuild is a clean no-op instead of
        # a 500 (D-TRANSL-T2M1 LOW-1, confirmed live by the backfill run). 5xx still raises
        # (transient — should retry, not wipe segments).
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return r.json().get("blocks", []) or []


async def get_chapter_word_counts(book_id, chapter_ids) -> dict[str, int]:
    """#36 — best-effort per-chapter size signal for the extraction cost estimate.

    Reads `word_count_estimate` from the existing `GET /internal/books/{id}/chapters`
    list (the same endpoint knowledge-service uses for ITS cost estimate). Returns
    `{chapter_id: word_count_estimate}` for the requested ids that exist; an id we
    couldn't find is simply absent (the caller defaults its size). Returns `{}` on ANY
    transport/parse error — a cost estimate must NEVER fail job creation, so we degrade
    to the legacy uniform-size assumption instead of raising.
    """
    wanted = {str(c) for c in chapter_ids}
    if not wanted:
        return {}
    base = (
        f"{settings.book_service_internal_url}"
        f"/internal/books/{book_id}/chapters"
    )
    out: dict[str, int] = {}
    offset = 0
    try:
        async with build_internal_client(
            settings.book_service_internal_url,
            internal_token=settings.internal_service_token, timeout_s=15,
        ) as client:
            for _ in range(_CHAPTER_LIST_MAX_PAGES):
                r = await client.get(
                    base,
                    params={"limit": _CHAPTER_LIST_PAGE, "offset": offset},
                )
                r.raise_for_status()
                items = r.json().get("items") or []
                for it in items:
                    cid = str(it.get("chapter_id") or "")
                    if cid in wanted:
                        out[cid] = int(it.get("word_count_estimate") or 0)
                # Stop on the last page or once every requested id is resolved.
                if len(items) < _CHAPTER_LIST_PAGE or len(out) >= len(wanted):
                    break
                offset += _CHAPTER_LIST_PAGE
    except Exception:  # noqa: BLE001 — advisory size; degrade to defaults, never block
        return {}
    return out


async def list_chapter_ids(book_id) -> list[str]:
    """ALL of a book's chapter ids, in book order (paginated). translation_coverage derives its
    chapter list from `chapter_translations`, so a chapter that has NEVER been translated is
    structurally invisible to it (D-S05-COVERAGE-MISMATCH) — exactly the chapters a "translate
    what's new" pass must find. This gives coverage the book's REAL chapter set so it can mark the
    untranslated ones. Returns [] on ANY error — coverage then degrades to translated-only rather
    than failing (a read must never break the turn)."""
    base = f"{settings.book_service_internal_url}/internal/books/{book_id}/chapters"
    out: list[str] = []
    offset = 0
    try:
        async with build_internal_client(
            settings.book_service_internal_url,
            internal_token=settings.internal_service_token, timeout_s=15,
        ) as client:
            for _ in range(_CHAPTER_LIST_MAX_PAGES):
                r = await client.get(base, params={"limit": _CHAPTER_LIST_PAGE, "offset": offset})
                r.raise_for_status()
                items = r.json().get("items") or []
                for it in items:
                    cid = str(it.get("chapter_id") or "")
                    if cid:
                        out.append(cid)
                if len(items) < _CHAPTER_LIST_PAGE:
                    break
                offset += _CHAPTER_LIST_PAGE
    except Exception:  # noqa: BLE001 — advisory; coverage degrades to translated-only
        return []
    return out


async def build_chapters_meta(book_id, chapter_ids) -> list[dict]:
    """#36 — chapters_meta for `estimate_extraction_cost`, carrying REAL per-chapter
    sizes (best-effort) instead of the flat `[{'text_length': 8000}]` placeholder that
    blinded the windowing planner. Order-preserving over `chapter_ids`; any chapter whose
    size we couldn't fetch keeps the legacy 8000-char default (→ no regression)."""
    sizes = await get_chapter_word_counts(book_id, chapter_ids)
    meta: list[dict] = []
    for cid in chapter_ids:
        wc = sizes.get(str(cid))
        text_length = (
            wc * _WORD_COUNT_TO_TEXT_LENGTH if wc and wc > 0
            else _DEFAULT_CHAPTER_TEXT_LENGTH
        )
        meta.append({"chapter_id": str(cid), "text_length": text_length})
    return meta
