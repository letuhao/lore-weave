"""One home for "what is canon AT this chapter" — the story bible a judge is graded against.

Why this module exists
----------------------
The sequence *(genre tags → cast as-of the chapter → render)* was written out inline at two
endpoints in `routers/plan.py` (self-heal, quality-report) and **nowhere else** — so the
autonomous authoring run's D5 critic seam, which has no bearer-side router to copy from,
judged with **no canon at all**:

    judge_prose(..., passage=text, active_rules=[], present_facts=[], ...)

`EngineCriticSeam`'s own docstring called that an honest v1 gap — *"this headless seam passes
empty active_rules/present_facts, so `canon_consistency` judges from the passage alone"* — and
it is exactly the failure QC-5 is written to catch: a misattributed betrayal scores 5/5 because
the judge was never told who betrayed whom. Measured 2026-08-13 on the acceptance book:
`canon_consistency=5, violations=[]`, from empty canon.

A third inline copy would have made it three; the two that existed had already drifted to the
point that only their comments differed. So the sequence lives here once, and its three callers
import it.

What "AS OF" means, and why it is not optional
---------------------------------------------
The cast is read at the chapter's **book `sort_order`** — the same axis
`entity_facts.valid_from_ordinal` is written on. Reading the untimed roster instead builds a
bible that describes the END of the book: a character who dies in chapter 40 is alive in it
while judging chapter 12, and their final rank is stated as their current one. That does not
make the judge fail; it makes it confidently wrong, which is worse.

When the position cannot be resolved the read DEGRADES to the untimed roster and says so in a
WARN — `canon_grounding` on the returned bible records which of the two happened, because an
ungrounded-in-time bible is invisible in the output otherwise.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.clients.book_client import BookClient, BookClientError
from app.clients.kal_client import KalClient
from app.engine.heal_canon import cast_from_state, convention_for, render_canon

logger = logging.getLogger(__name__)

__all__ = [
    "CanonBible", "cast_roster", "canon_cast_at", "book_genre_tags", "canon_for_chapter",
]


@dataclass(frozen=True)
class CanonBible:
    """The rendered bible plus **how it was grounded** — never just the string.

    `grounding` is the field that matters:

    * `as_of` — the cast was read at the chapter's story position. The strong case.
    * `untimed` — the position could not be resolved, so this bible describes the END of the
      book: a character who dies in chapter 40 is alive in it.
    * `convention_only` — a bible WAS rendered, but it holds **no cast**: the genre / address-form
      convention block and nothing else. The judge has style guidance and zero canon.
    * `empty` — nothing rendered at all.

    ⚠️ `convention_only` exists because the first cut did not have it, and the first live run
    after C2 reported `grounding='as_of', cast_size=0` — which reads as *grounded* and was in
    fact a **KAL outage** (`kal state@11 unavailable: Name or service not known`; the client
    degrades a transport failure to `[]` by contract). A field that says "grounded" when the
    canon read failed is worse than no field: it launders an outage into a verdict. The cast is
    what grounds a bible, so a bible without one does not get to claim a position.

    A caller that reports a `canon_consistency` score alongside anything but `as_of` is
    reporting a weaker number than it looks — the same lesson as `name_truth_source`, computed
    and then dropped before the envelope so no caller could read it.
    """

    text: str
    grounding: str  # 'as_of' | 'untimed' | 'convention_only' | 'empty'
    as_of: int | None = None
    cast_size: int = 0

    def as_present_facts(self) -> list[str]:
        """The critic's `present_facts` shape.

        A rendered bible is one multi-line established-fact block, not a list of structured
        rules — the same shape `build_quality_report` already hands `judge_prose`, kept
        identical on purpose so the two judges see canon the same way.
        """
        return [self.text.strip()] if self.text.strip() else []


async def cast_roster(
    kal: KalClient, book_id: UUID, user_id: UUID, *, strict: bool = False
) -> list[dict]:
    """The book's full cast as `{entity_id, name}`, read through the KAL (INV-KAL).

    Drains the KAL `roster` keyset cursor to completion (D4 / §12.5.2): the prior glossary
    `list_entities` path read only the first page and ignored `next_cursor`, silently
    truncating the cast at ~100 — so a deep book's planner saw an incomplete roster. The KAL
    roster is bounded-per-page, COMPLETE-in-aggregate; the client follows `next_cursor` until
    null.

    Default (non-strict): empty/partial on outage (the packer just gets a thin/no roster).
    `strict=True` raises `RosterIncomplete` on a truncated drain so a caller that treats the
    cast as AUTHORITATIVE (commit-time entity validation) can skip instead of false-rejecting
    a valid id in a dropped page. `user_id` is forwarded as the KAL tenancy identity.

    ── WHY THIS SURVIVES T7, per caller ──────────────────────────────────────────────────
    T7 moved the CANON BIBLE reads onto `state@as_of` (`canon_cast_at`), because a bible is a
    claim about what is true AT the chapter being written. Every remaining caller here answers
    a different question — "does this entity belong to this book" or "what do I label it" —
    and for those the untimed catalogue is the CORRECT read, not a leftover:

    - **existence / tenancy validation** (`present_entity` at commit, the motif-swap and
      role-rebind binding targets): an entity introduced in chapter 50 is a perfectly valid
      binding target while planning chapter 10. Gating membership on a story position would
      reject valid ids for the reason that they are not born yet.
    - **label resolution** (`entity → name` for the bound-motif render): the display name of a
      binding, not a canon claim. `roster`'s id+name projection is exactly this.
    - **`/decompose`'s cast**: the plan spans the whole book, so no single position exists to
      read it at. The per-chapter grounding happens downstream, where a position does exist.

    A caller that ever needs "who was alive / what was their rank THEN" belongs on
    `canon_cast_at`, not here. Documented rather than left silent: an untimed read that
    *should* have been timed is invisible in the output — it just quietly describes the end of
    the book."""
    return await kal.roster(book_id, user_id=user_id, strict=strict)


async def canon_cast_at(
    kal: KalClient, book: BookClient, book_id: UUID, chapter_id: UUID, user_id: UUID,
) -> tuple[list[dict], int | None]:
    """The cast AS OF the chapter being worked on — the input to `render_canon`.

    Returns `(cast, as_of)`. `as_of is None` means the position was NOT resolved and the cast
    is the untimed roster — the degrade path, which the caller must be able to see. It used to
    be visible only in a log line; a fallback nobody can observe from the result is a fallback
    that gets reported as a success.

    The position is the chapter's `sort_order` — the book position, the same axis
    `entity_facts.valid_from_ordinal` is written on (extraction sources it from book-service's
    `sort_order` for exactly this reason). A job-relative or list index here would silently
    answer about a different chapter.
    """
    orders = await book.get_chapter_sort_orders([chapter_id])
    as_of = orders.get(str(chapter_id))
    if not isinstance(as_of, int):
        logger.warning(
            "canon cast for book %s chapter %s has NO resolved story position (sort_order "
            "absent) — falling back to the untimed roster; the bible will describe the end "
            "of the book, not this chapter", book_id, chapter_id)
        return await cast_roster(kal, book_id, user_id), None
    logger.info("canon cast resolved story position: book=%s chapter=%s as_of=%d",
                book_id, chapter_id, as_of)
    cast = cast_from_state(await kal.state(book_id, as_of=as_of, user_id=user_id))
    return await _fill_missing_names(kal, book_id, user_id, cast), as_of


async def _fill_missing_names(
    kal: KalClient, book_id: UUID, user_id: UUID, cast: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Give the state-derived cast the NAMES only the roster carries.

    🔴 **Measured (QC-5 C41): the block headed "CHARACTER CANON" contained no characters.**
    `state@as_of` projects `{entity_id, facts}` and nothing else, so a name reaches
    `cast_from_state` only when the entity happens to carry a `name` FACT. On the acceptance
    book **13 of 21 entities do; 8 do not** — and the 8 are the people. `render_canon` then
    drops every nameless row (*"a nameless bible line grounds nothing"*, correctly), so the
    bible listed the talent competition, the spirit stones and the tea pavilion, and not one
    character. A critic asked whether prose contradicts a rule about a named character, handed a
    character canon with that character missing, flags prose that conforms — which is QC-5's
    clause 1a failing at 7/8 on the untouched control.

    The names were never missing from the system: `roster` *"could only ever supply
    `{entity_id, name}` — the KAL projects it to id+name by contract"*, which is this
    function's whole reason to exist. Best-effort by construction: a roster outage leaves the
    cast exactly as `state` gave it, because a thinner bible must never cost the critique.
    """
    if not any(not (c.get("name") or "").strip() for c in cast):
        return cast
    try:
        names = {str(r.get("entity_id")): str(r.get("name") or "").strip()
                 for r in await cast_roster(kal, book_id, user_id)}
    except Exception:  # noqa: BLE001 — advisory; the bible degrades, the critique does not
        # WARNING, not debug: this degrade costs the critic every character whose name lives
        # only in the roster, and C41 measured that as 8 of 21 entities on the acceptance book.
        # A fallback nobody can observe is a fallback that gets reported as a success — the same
        # rule `canon_cast_at` states one function up.
        logger.warning("canon cast: roster unavailable — %d entity(ies) stay NAMELESS and will "
                       "be dropped from the bible", sum(1 for c in cast
                                                        if not (c.get("name") or "").strip()),
                       exc_info=True)
        return cast
    filled = 0
    for c in cast:
        if not (c.get("name") or "").strip():
            nm = names.get(str(c.get("entity_id") or ""))
            if nm:
                c["name"] = nm
                filled += 1
    if filled:
        logger.info("canon cast: filled %d name(s) from the roster that state@as_of omitted",
                    filled)
    return cast


async def book_genre_tags(book: BookClient, book_id: UUID, bearer: str) -> list[str]:
    """The book's genre tags for motif retrieval and the address-form convention (best-effort — an
    empty list just means no convention block binds). Reads the `genres`/`genre_tags` field off
    the book object if present."""
    try:
        b = await book.get_book(book_id, bearer)
    except BookClientError:
        return []
    if not b:
        return []
    raw = b.get("genres") or b.get("genre_tags") or []
    return [str(g) for g in raw if isinstance(g, (str,)) and g.strip()]


async def canon_for_chapter(
    *,
    kal: KalClient,
    book: BookClient,
    book_id: UUID,
    chapter_id: UUID,
    user_id: UUID,
    bearer: str,
    source_language: str,
) -> CanonBible:
    """Render the story bible for ONE chapter: genre convention + the cast as of its position.

    Degrade-safe by construction — every read inside is best-effort and an outage yields an
    `empty` bible rather than an exception, because every caller is advisory (a critic, a
    self-heal proposal, a quality report). None of them may fail a chapter over a canon read.
    """
    try:
        genre_tags = await book_genre_tags(book, book_id, bearer)
    except Exception:  # noqa: BLE001 — advisory; a convention-less bible still grounds names
        logger.warning("canon bible: genre tags unreadable (continuing)", exc_info=True)
        genre_tags = []
    try:
        cast, as_of = await canon_cast_at(kal, book, book_id, chapter_id, user_id)
    except Exception:  # noqa: BLE001 — advisory; see the docstring
        logger.warning("canon bible: cast unreadable — judging without canon", exc_info=True)
        return CanonBible(text="", grounding="empty")

    text = render_canon(cast, convention=convention_for(genre_tags, source_language))
    if not text.strip():
        return CanonBible(text="", grounding="empty", as_of=as_of, cast_size=len(cast))
    if not cast:
        # A convention block renders even with nobody in it, so `text` being non-empty proves
        # nothing about canon. Say so, loudly: this is the shape a KAL outage takes.
        logger.warning(
            "canon bible for book %s chapter %s has NO CAST — convention block only; the "
            "judge gets style guidance and zero canon (KAL empty or unavailable)",
            book_id, chapter_id)
        return CanonBible(text=text, grounding="convention_only", as_of=as_of, cast_size=0)
    return CanonBible(
        text=text,
        grounding="as_of" if as_of is not None else "untimed",
        as_of=as_of,
        cast_size=len(cast),
    )
