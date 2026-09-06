"""D-RESUME-REBUILDS-CONTEXT-IDS-WITHOUT-CHAPTER-OR-PROJECT.

The resume rebuilds `context_ids` BY HAND from the suspension row, and that dict has now lost a
field three times: `studio` (fixed 2026-08-12), then chapter_id and project_id.

Absent chapter_id is not a missing nicety. `_crosswired_ids` identifies a mis-wired id by EXACT
MATCH against the turn's OTHER context ids, so with chapter_id absent it has nothing to match:
a chapter id sent as `book_id` goes out untouched and the book-scope check correctly refuses it.

Measured 2026-08-24 (batch c-gbuild5): every run resumed through an approval card, and on 4 of 4
failing calls the book_id EQUALLED that run's chapter_id. The author was told "I'm having a
technical issue accessing the book's database to save them" and the writes did not happen — on a
book that was fine.
"""
from app.db.suspended_runs import SuspendedRun
from app.services.stream_service import _crosswired_ids, _inject_context_ids

BOOK = "01a03469-2ecf-7cd0-a7f2-e88303ef223c"
CHAPTER = "01a03469-2f61-7fea-901d-f12f25b9d758"   # the id actually sent as book_id
PROJECT = "01a03469-3027-730d-9529-78a14da28b5d"


def _susp(**kw):
    base = dict(
        run_id="r", session_id="s", owner_user_id="u", message_id="m", working=[],
        pending_tool_call={}, input_tokens=0, output_tokens=0, model_source="user_model",
        model_ref="x", parent_message_id=None, user_message_content="go",
        book_id=BOOK, studio=False, chapter_id=CHAPTER, project_id=PROJECT,
    )
    base.update(kw)
    return SuspendedRun(**base)


class TestTheSuspensionCarriesAllThree:
    def test_the_row_has_chapter_and_project_fields(self):
        s = _susp()
        assert s.chapter_id == CHAPTER
        assert s.project_id == PROJECT

    def test_they_default_to_none_for_pre_existing_rows(self):
        """NULL for rows suspended before the migration is exactly the old behaviour: no
        substitute available, so no correction attempted."""
        s = _susp(chapter_id=None, project_id=None)
        assert s.chapter_id is None and s.project_id is None


class TestTheGuardCanFireOnceTheyAreCarried:
    def test_the_chapter_id_is_recognised_as_crosswired_for_book_id(self):
        assert CHAPTER in _crosswired_ids(
            "book_id", book_id=BOOK, chapter_id=CHAPTER, project_id=PROJECT)

    def test_the_measured_call_is_corrected(self):
        """The exact payload from c-gbuild5: glossary_propose_entities{book_id: <CHAPTER>}."""
        tool = {"function": {"name": "glossary_propose_entities", "_meta": {},
                             "parameters": {"type": "object",
                                            "properties": {"book_id": {"type": "string"}}}}}
        out = _inject_context_ids({"book_id": CHAPTER}, tool,
                                  book_id=BOOK, chapter_id=CHAPTER, project_id=PROJECT)
        assert out["book_id"] == BOOK, (
            "the chapter id was forwarded as book_id — the book-scope check will refuse it and "
            "the author's write will not happen"
        )

    def test_without_the_chapter_id_the_guard_is_blind(self):
        """🔴 THE PROOF THAT THE MISSING FIELD IS THE CAUSE, not a bystander. This is the
        resume's OLD state — book_id only — and the wrong id sails through untouched."""
        tool = {"function": {"name": "glossary_propose_entities", "_meta": {},
                             "parameters": {"type": "object",
                                            "properties": {"book_id": {"type": "string"}}}}}
        out = _inject_context_ids({"book_id": CHAPTER}, tool,
                                  book_id=BOOK, chapter_id=None, project_id=None)
        assert out["book_id"] == CHAPTER

    def test_a_legitimate_cross_book_call_is_still_honored(self):
        """Precision: only an id THIS TURN published is evidence. An unrelated book id is a
        deliberate cross-book call and must not be redirected."""
        other = "01a03469-ffff-7000-8000-000000000000"
        tool = {"function": {"name": "glossary_propose_entities", "_meta": {},
                             "parameters": {"type": "object",
                                            "properties": {"book_id": {"type": "string"}}}}}
        out = _inject_context_ids({"book_id": other}, tool,
                                  book_id=BOOK, chapter_id=CHAPTER, project_id=PROJECT)
        assert out["book_id"] == other


class TestTheRESUMEPathActuallyPassesThem:
    """🔴 THE TESTS ABOVE PASSED WITH THE RESUME FIX REVERTED, which makes them a guard on the
    HELPER and not on the call site. `_inject_context_ids` and `_crosswired_ids` were always
    correct — the defect was that `resume_stream_response` rebuilt `context_ids` by hand and
    never handed them the ids. A falsifier that cannot see that is guarding the wrong line.

    Structural, for the same reason the silent-turn guard is: the resume path needs a live
    suspension, a pool and a provider to invoke, and the thing worth pinning is one dict."""

    @staticmethod
    def _resume_src() -> str:
        import inspect

        from app.services import stream_service

        src = inspect.getsource(stream_service)
        i = src.find("async def resume_stream_response")
        assert i > 0, "resume_stream_response not found"
        return src[i:]

    def test_the_resume_carries_chapter_id_from_the_suspension(self):
        assert '"chapter_id": susp.chapter_id' in self._resume_src(), (
            "the resume rebuilds context_ids without chapter_id — the cross-wire guard is blind "
            "again and a chapter id will go out as book_id"
        )

    def test_the_resume_carries_project_id_from_the_suspension(self):
        assert '"project_id": susp.project_id' in self._resume_src()

    def test_it_still_carries_the_two_that_were_already_there(self):
        """The field this dict lost in 2026-08-12 must not be lost again while fixing the others."""
        src = self._resume_src()
        assert '"book_id": susp.book_id' in src
        assert '"studio": bool(susp.studio)' in src

    def test_the_suspension_is_saved_with_all_three(self):
        """The read half is worthless if the write half never stored them."""
        import inspect

        from app.services import stream_service

        src = inspect.getsource(stream_service)
        i = src.find("await save_suspended_run(")
        assert i > 0
        # 🔴 NOT A CHARACTER WINDOW. The first version used src[i:i+2500] and went RED because
        # the second argument sat at offset ~2500 — the assertion failed for arithmetic, not for
        # the thing it tests. Bound the block by the STATEMENT's end instead.
        end = src.find("# DBT-CHAT-PERSIST", i)
        assert end > i, "could not find the end of the save_suspended_run call"
        block = src[i:end]
        assert 'chapter_id=(context_ids or {}).get("chapter_id")' in block
        assert 'project_id=(context_ids or {}).get("project_id")' in block
