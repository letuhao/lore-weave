"""D-FJ-20 — a context-id put in the WRONG slot is a cross-wiring, not a cross-book call.

🔴 MEASURED LIVE 2026-08-13, session 019ff929, EDITOR surface, book 019ff8f5-ae59-71f9-acb9-
ad607b363ef7 with chapter 019ff8f5-ee89-75ef-a894-ff9462332bc0 open.

The `build-a-book` rail drove `plan_propose_spec` four times across two turns, every call carrying
`book_id="019ff8f5-ee89-75ef-a894-ff9462332bc0"` — the CHAPTER open in the editor, confirmed as a
row in that book's `chapters` table. Every call was refused "not found or not accessible", the rail
re-drove to its cap, and the author's question was answered three times over with the same stale
apology about a plan that never landed.

`_inject_context_ids` is deliberately conservative: it honours a valid-but-different UUID, because
that IS a deliberate cross-book call. A studio-scoped override for this exact shape already exists
and even names `plan_propose_spec` — but the editor is not the studio, so it never applied.

The narrower fact needs no surface gate and no policy judgement: a value that IS the turn's own
chapter_id cannot be a book id. Only an exact match against another id the server is already
holding counts — never a guess, never a similarity check.
"""
import pytest

BOOK = "019ff8f5-ae59-71f9-acb9-ad607b363ef7"
CHAPTER = "019ff8f5-ee89-75ef-a894-ff9462332bc0"
PROJECT = "019ff8f6-2a59-7dad-bfe5-f1b2b445e75c"
OTHER_BOOK = "019f9f2d-f9f1-7037-ba78-8ccc3e19c956"


def _tool(*keys):
    """A tool_def in the shape _inject_context_ids reads: `_meta` lives INSIDE `function`."""
    return {"function": {"_meta": {}, "parameters": {"properties": {k: {} for k in keys}}}}


def _inject(args, tool, **kw):
    from app.services.stream_service import _inject_context_ids
    kw.setdefault("book_id", BOOK)
    kw.setdefault("chapter_id", CHAPTER)
    kw.setdefault("project_id", PROJECT)
    return _inject_context_ids(dict(args), tool, **kw)


class TestTheLiveCrossWiring:
    def test_the_LIVE_defect_the_chapter_id_in_book_id_is_replaced(self):
        """THE FALSIFIER. Before the fix this returned the chapter id untouched and every
        plan_propose_spec call was refused 'not found or not accessible'."""
        out = _inject({"book_id": CHAPTER, "source_markdown": "# Arc"}, _tool("book_id"))
        assert out["book_id"] == BOOK

    def test_the_reverse_swap_is_repaired_too(self):
        out = _inject({"chapter_id": BOOK}, _tool("chapter_id"))
        assert out["chapter_id"] == CHAPTER

    def test_a_project_id_in_book_id_is_repaired(self):
        out = _inject({"book_id": PROJECT}, _tool("book_id"))
        assert out["book_id"] == BOOK


class TestTheRepairStaysNarrow:
    """The value of this fix is that it can only ever fire on an id the SERVER supplied. A wider
    rule would silently redirect real cross-book work, which is what the conservative design of
    `_inject_context_ids` exists to protect."""

    def test_a_genuine_cross_book_call_is_still_honoured(self):
        """A valid UUID that is NOT one of this turn's ids is a deliberate cross-book call and
        must survive untouched — off a studio turn."""
        out = _inject({"book_id": OTHER_BOOK}, _tool("book_id"))
        assert out["book_id"] == OTHER_BOOK

    def test_the_correct_id_in_its_own_slot_is_untouched(self):
        out = _inject({"book_id": BOOK, "chapter_id": CHAPTER}, _tool("book_id", "chapter_id"))
        assert out == {"book_id": BOOK, "chapter_id": CHAPTER}

    def test_a_missing_arg_is_still_simply_filled(self):
        out = _inject({}, _tool("book_id"))
        assert out["book_id"] == BOOK

    def test_a_non_uuid_still_takes_the_mistranscription_path(self):
        out = _inject({"book_id": "Mị Đế"}, _tool("book_id"))
        assert out["book_id"] == BOOK

    def test_a_key_the_tool_does_not_declare_is_never_added(self):
        out = _inject({"book_id": CHAPTER}, _tool("chapter_id"))
        # book_id is not in the schema, so the injector must not touch it at all
        assert out["book_id"] == CHAPTER

    def test_no_repair_when_the_server_knows_only_one_id(self):
        """With no chapter_id in context there is nothing to identify the value AS, so the
        conservative cross-book rule must still win."""
        out = _inject({"book_id": CHAPTER}, _tool("book_id"), chapter_id=None, project_id=None)
        assert out["book_id"] == CHAPTER


class TestTheHelperItself:
    @pytest.mark.parametrize("key,expected", [
        ("book_id", {CHAPTER, PROJECT}),
        ("chapter_id", {BOOK, PROJECT}),
        ("project_id", {BOOK, CHAPTER}),
    ])
    def test_the_other_ids_of_the_turn_are_the_crosswired_set(self, key, expected):
        from app.services.stream_service import _crosswired_ids
        assert set(_crosswired_ids(
            key, book_id=BOOK, chapter_id=CHAPTER, project_id=PROJECT)) == expected

    def test_an_id_that_is_ALSO_the_right_value_is_not_crosswired(self):
        """Some surfaces carry the same UUID in two slots. Treating that as a cross-wiring would
        make the repair a no-op that logs a false warning."""
        from app.services.stream_service import _crosswired_ids
        assert _crosswired_ids(
            "book_id", book_id=BOOK, chapter_id=BOOK, project_id=None) == frozenset()
