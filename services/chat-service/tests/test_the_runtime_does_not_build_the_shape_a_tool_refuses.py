"""The backfiller must never COMPLETE an argument group a tool accepts exactly one of.

THE INVARIANT. An argument the runtime supplies must leave the call in a shape the tool
accepts. Filling a context id is right for almost every tool; it is wrong when the tool
declares that id mutually exclusive with one the call already carries, because the result is
a shape no caller could have meant and the model cannot undo.

🔴 MEASURED 2026-09-01, AND IT REFUTED THE PREVIOUS CYCLE'S FIX. `composition_list_derivatives`
takes EXACTLY ONE of book_id/project_id. A studio book turn carries both, so
`_inject_context_ids` supplied both and the tool answered "give EXACTLY ONE". Live K=5 through
the real chat path: 24 of 24 calls carried both ids and every one was refused; store-wide the
shape is 0 done in 46 attempts.

The cycle before this one rewrote the refusal that sends the model to that tool, telling it to
"call composition_list_derivatives with NO ARGUMENTS". The live run was UNCHANGED — which is the
point of this file. An obedient model reaches the same shape, because on an empty call the
runtime fills both. Wording cannot fix a shape constructed after the model has spoken.
"""
from __future__ import annotations

from app.services.stream_service import _inject_context_ids

BOOK = "01a05979-2139-7212-865a-0ec342d23a2c"
PROJECT = "01a05979-2281-7b0a-ba74-3edbd0541ec1"
CHAPTER = "01a05979-3333-7212-865a-0ec342d23a2c"


def _tool(props, *, meta=None):
    return {"function": {"name": "t", "_meta": meta or {},
                         "parameters": {"properties": {p: {"type": "string"} for p in props}}}}


class TestAnExclusiveGroupIsCompletedAtMostOnce:
    def test_an_empty_call_gets_one_member_not_both(self):
        """The measured case: the model does exactly what the refusal told it and calls with
        nothing. It must come out with a callable shape."""
        args: dict = {}
        _inject_context_ids(
            args, _tool(["book_id", "project_id"],
                        meta={"exclusive_args": [["book_id", "project_id"]]}),
            book_id=BOOK, chapter_id=None, project_id=PROJECT, studio=True)
        assert args == {"book_id": BOOK}, (
            "the runtime supplied both members of a group the tool accepts exactly one of — "
            "the shape measured 24/24 refused, and no wording can prevent it")

    def test_a_member_the_model_supplied_blocks_the_other(self):
        """The other live shape: the model holds a project_id and passes it. The book must not
        be added underneath."""
        args = {"project_id": PROJECT}
        _inject_context_ids(
            args, _tool(["book_id", "project_id"],
                        meta={"exclusive_args": [["book_id", "project_id"]]}),
            book_id=BOOK, chapter_id=None, project_id=PROJECT, studio=True)
        assert args == {"project_id": PROJECT}

    def test_the_group_does_not_stop_a_fill_outside_it(self):
        """A guard that over-reaches would break the backfiller for every other argument."""
        args: dict = {}
        _inject_context_ids(
            args, _tool(["book_id", "project_id", "chapter_id"],
                        meta={"exclusive_args": [["book_id", "project_id"]]}),
            book_id=BOOK, chapter_id=CHAPTER, project_id=PROJECT, studio=True)
        assert args["chapter_id"] == CHAPTER, "chapter_id is in no group and must still be filled"

    def test_a_tool_with_no_group_is_untouched(self):
        """The overwhelming majority of tools. Filling both ids is correct for them and this
        change must not cost them anything."""
        args: dict = {}
        _inject_context_ids(
            args, _tool(["book_id", "project_id"]),
            book_id=BOOK, chapter_id=None, project_id=PROJECT, studio=True)
        assert args == {"book_id": BOOK, "project_id": PROJECT}

    def test_a_mistranscribed_id_is_still_corrected_inside_a_group(self):
        """A SUBSTITUTION cannot complete a group — the argument is already there. Correcting a
        mangled UUID must keep working, or this fix would trade one live failure for another."""
        args = {"project_id": "not-a-uuid"}
        _inject_context_ids(
            args, _tool(["book_id", "project_id"],
                        meta={"exclusive_args": [["book_id", "project_id"]]}),
            book_id=BOOK, chapter_id=None, project_id=PROJECT, studio=True)
        assert args == {"project_id": PROJECT}, (
            "the group guard swallowed the mistranscription repair, which is a different "
            "measured defect and is not in scope to break")

    def test_a_blank_member_does_not_count_as_present(self):
        """`{"project_id": ""}` is an absent argument wearing a key. Treating it as present
        would leave the call with no id at all."""
        args = {"project_id": ""}
        _inject_context_ids(
            args, _tool(["book_id", "project_id"],
                        meta={"exclusive_args": [["book_id", "project_id"]]}),
            book_id=BOOK, chapter_id=None, project_id=PROJECT, studio=True)
        assert args.get("book_id") == BOOK


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
