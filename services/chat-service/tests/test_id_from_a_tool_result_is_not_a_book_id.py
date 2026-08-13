"""D-XWIRE-RESULT — an id the platform published as a chapter_id must never pass as a book_id.

MEASURED LIVE 2026-08-14, 3 of 3 runs, through the real chat path with a throwaway book per run.
Prompt: "Please write a chapter. Add a new one after what I have, called The Drowned Road, about
Mira leading Aldric through the marsh." — from the chat panel, no editor context.

    book_list {kind: "chapters", book_id: <BOOK>}
      -> {"chapters": [{"chapter_id": "<CHAP>", "title": "Chapter I — The Ember Codex", ...}]}
    book_chapter_create {book_id: "<CHAP>", title: "The Drowned Road", ...}
      -> {"ok": false, "error": "book not accessible"}

The refusal is wrong twice: the id is not an inaccessible book, it is a chapter, and the user owns
it. With nothing to correct against the model retried the identical call and then went reading an
unrelated book of the user's, looking for one that would accept the write. Zero chapters were
created on any of the three runs, while the same scenario WITH editor context created one every
time — so the tool works and the argument was the whole defect.

WHY D-FJ-20 DID NOT COVER IT. `_crosswired_ids` fires only when the offending value is one of the
three ids the request envelope carries. With no editor context the server held no chapter_id, so
there was nothing to match. The rule was correct and its evidence base was too small: the platform
had ALREADY published that id, under the name `chapter_id`, in a tool result it returned during
this very turn.

THE INVARIANT: an id argument must be of the type its parameter names, and an id this platform
published under a different name is a cross-wire by construction — not a heuristic, not a guess,
and not a policy call. An id the turn has never seen is still left strictly alone, so a deliberate
cross-book call keeps working.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.id_ledger import IdLedger  # noqa: E402
from app.services.stream_service import _inject_context_ids  # noqa: E402

BOOK = "019ffcb5-bb51-7d80-81a7-567061a9b6b7"
CHAP = "019ffcb5-bbff-7680-b0a0-b2bdcd27d3b6"
OTHER_BOOK = "019ff61b-7ece-777a-a006-b9bd0ca7eb0c"

#: book_chapter_create's real shape, from the live federated catalogue.
CREATE_DEF = {
    "function": {
        "name": "book_chapter_create",
        "parameters": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string"},
                "title": {"type": "string"},
                "original_language": {"type": "string"},
            },
            "required": ["book_id", "original_language"],
        },
    }
}

#: The exact envelope book_list returned on the live runs, trimmed to the shape that matters.
BOOK_LIST_RESULT = {
    "kind": "chapters",
    "page": {"has_more": False, "is_complete": True, "returned": 1, "total": 1},
    "chapters": [
        {
            "chapter_id": CHAP,
            "title": "Chapter I — The Ember Codex",
            "sort_order": 1,
            "editorial_status": "draft",
        }
    ],
}


def _ledger_after_book_list() -> IdLedger:
    """The turn as it really stood: a book_id from the envelope, a chapter_id from a tool result."""
    led = IdLedger()
    led.note("book_id", BOOK)
    led.record(BOOK_LIST_RESULT)
    return led


def test_ledger_learns_the_chapter_id_from_a_nested_tool_result():
    led = _ledger_after_book_list()
    assert led.type_of(CHAP) == "chapter_id", (
        "the id was announced as `chapter_id` inside chapters[0]; if the walk does not reach it "
        "the repair has no evidence and the live defect stands"
    )
    assert led.type_of(BOOK) == "book_id"
    assert led.type_of(OTHER_BOOK) is None, "never seen this turn — must stay unknown"


def test_a_chapter_id_supplied_as_book_id_is_repaired():
    """THE FALSIFIER. Original defect = the ledger is not consulted; then this asserts the bug."""
    args = {"book_id": CHAP, "title": "The Drowned Road", "original_language": "en"}
    _inject_context_ids(
        args, CREATE_DEF,
        book_id=BOOK,
        chapter_id=None,      # the chat panel sends no editor context — this is the whole point
        project_id=None,
        id_ledger=_ledger_after_book_list(),
    )
    assert args["book_id"] == BOOK, (
        "book_chapter_create was called with the chapter_id book_list had just returned. The "
        "server knew the book for this turn and knew that value was a chapter, and still let the "
        "call through to a 'book not accessible' refusal."
    )
    assert args["title"] == "The Drowned Road", "only the id may be repaired"


def test_an_unknown_uuid_is_still_honoured_as_a_deliberate_cross_book_call():
    """The invariant this must NOT break — protected since S02.

    A valid UUID the turn has never published is not evidence of anything. Substituting it would
    silently redirect a user who really did mean another book, which is a worse defect than the
    one being fixed.
    """
    args = {"book_id": OTHER_BOOK, "title": "X", "original_language": "en"}
    _inject_context_ids(
        args, CREATE_DEF,
        book_id=BOOK, chapter_id=None, project_id=None,
        id_ledger=_ledger_after_book_list(),
    )
    assert args["book_id"] == OTHER_BOOK


def test_an_error_payloads_ids_are_not_learned():
    """A failed call's args come back in its error envelope. Recording those would teach the
    ledger the model's own mistake and then 'repair' toward it."""
    led = IdLedger()
    led.note("book_id", BOOK)
    # never recorded: the dispatch only records on ok=True
    assert led.type_of(CHAP) is None


def test_d_fj_20_still_holds_without_a_ledger():
    """The narrower predecessor must keep working on its own evidence — the editor surface case,
    where the chapter_id DOES come from the request envelope and no tool result is needed."""
    args = {"book_id": CHAP}
    _inject_context_ids(
        args, {"function": {"parameters": {"properties": {"book_id": {"type": "string"}}}}},
        book_id=BOOK, chapter_id=CHAP, project_id=None,
        id_ledger=None,
    )
    assert args["book_id"] == BOOK
