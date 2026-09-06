"""F2 — when one of the two colliding ids is OPTIONAL, "omit it" is advice the caller can take.

🔴 THE MEASURED INSTANCE, 2026-09-04, driving the real Studio as an author. Asked for Chapter
Two, the assistant called `composition_outline_node_edit` twice in one turn to create the node:

    {"op": "create", "kind": "chapter", "title": "Chapter Two: The Bureaucracy of Silence",
     "parent_id": "01a06a7f-abcb-…", "project_id": "01a06a7f-abcb-…"}          ok: false
    {"op": "create", "kind": "chapter", "title": "The Warden's Office",
     "parent_id": "01a06a7f-abcb-…", "project_id": "01a06a7f-abcb-…"}          ok: false

Both correctly refused — 135 calls of that shape across 7 tools have succeeded ZERO times. But
`parent_id` is **optional** on `op=create`, and a chapter's parent IS the project root, so there
was nothing to look up. The refusal's advice — *"Look the missing one up (a list/search tool for
that kind of record returns it)"* — named an action with no referent. The model repeated the same
shape, then abandoned the chapter: the book ended with Chapter One saved twice and no Chapter Two.

🔴 THIS DOES NOT MAKE THE CHECK A REPAIR, and that distinction is the whole design. The runtime
still does not know which argument is wrong — dropping `parent_id` on the caller's behalf would
file the chapter at the root when a real parent may have been meant, and §3a forbids a guess
deciding that. **Only the ADVICE changes**, and only where the tool's own schema says the
parameter is droppable.
"""
from __future__ import annotations

from app.agentruntime.toolcontract import (
    duplicate_identifier,
    duplicate_identifier_message,
)

_ID_A = "01a06a7f-abcb-7c3e-ab1c-6cde5e2d5f36"


def test_the_measured_call_is_still_REFUSED():
    """The detection is unchanged. Softening it was never the fix."""
    got = duplicate_identifier({
        "op": "create", "kind": "chapter", "title": "Chapter Two",
        "parent_id": _ID_A, "project_id": _ID_A,
    })
    assert got is not None
    a, b, val = got
    assert {a, b} == {"parent_id", "project_id"} and val == _ID_A


def test_an_optional_param_is_named_as_droppable():
    """The fix. `parent_id` is optional on this tool, so OMITTING it is an action that exists."""
    msg = duplicate_identifier_message(
        "parent_id", "project_id", _ID_A, optional=("parent_id",))
    assert "OPTIONAL" in msg and "OMIT it" in msg, msg
    assert "'parent_id'" in msg


def test_the_old_advice_is_still_there_for_the_REQUIRED_case():
    """🔴 THE ARM THAT KEEPS THIS HONEST. When BOTH ids are required — `book_id`/`chapter_id` on
    `book_chapter_save_draft`, 38 measured calls — there is nothing to drop, and telling the
    model to omit one would send it into a second failure. The original instruction must survive
    untouched for that case, which is the majority of the 135."""
    msg = duplicate_identifier_message("book_id", "chapter_id", _ID_A)
    assert "Look the missing one up" in msg
    assert "OMIT" not in msg and "OPTIONAL" not in msg, msg


def test_both_optional_names_both():
    """Two droppable params is unusual but not impossible; the message must not pick one."""
    msg = duplicate_identifier_message(
        "after_id", "parent_id", _ID_A, optional=("after_id", "parent_id"))
    assert "'after_id' or 'parent_id'" in msg, msg


def test_the_refusal_still_names_the_pair_and_the_value_in_every_case():
    """Whatever the advice, the diagnosis must stay: which two, and what value. A message that
    only advised would leave the reader unable to tell WHICH call this was about."""
    for optional in ((), ("parent_id",)):
        msg = duplicate_identifier_message(
            "parent_id", "project_id", _ID_A, optional=optional)
        assert "'parent_id'" in msg and "'project_id'" in msg and _ID_A in msg
        assert "can never be the same id" in msg


def test_a_legitimate_call_with_two_DISTINCT_ids_is_untouched():
    """The negative control: the check must not fire on the ordinary shape it permits."""
    assert duplicate_identifier({
        "op": "create", "kind": "chapter",
        "parent_id": "01a06a7f-abcb-7c3e-ab1c-6cde5e2d5f36",
        "project_id": "01a06a80-0000-7000-8000-000000000001",
    }) is None
