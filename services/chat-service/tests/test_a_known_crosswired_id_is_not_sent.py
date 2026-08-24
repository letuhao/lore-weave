"""A cross-wired id the runtime RECOGNISES must not be forwarded just because there is
nothing to replace it with.

`_inject_context_ids` corrects an argument when the model puts one of the turn's own ids in
another id's slot — D-FJ-20 / D-XWIRE-RESULT. The correction lived behind a guard that skipped
the whole key when the turn had no value of that kind to substitute, so the case where the
runtime knew the answer was wrong and had no better one produced no action at all.

MEASURED 2026-08-24, batch c-override9, K=5, gemma-4-26b-a4b-qat. `project_id` is populated in
`context_ids` only on studio/editor turns; this turn has none. The model sent

    composition_list_derivatives {"project_id": "01a03116-dd1f-…"}   <- the turn's BOOK id

and `is_crosswired("project_id", book_id)` returns True — checked against the deployed function,
not inferred. The call went out unchanged and came back "not found or not accessible", which
tells the model nothing about what it did wrong. It retried the same call twice and died on the
repeat-breaker.

Dropping the argument instead makes the tool's own missing-argument refusal fire, which names
the declared supplier and arms it. The evidence standard is unchanged: `is_crosswired` is true
only for an id THIS TURN published under a DIFFERENT name — the same standard the existing
branch already treats as sufficient to OVERWRITE a value.

🔴 AND IT IS NARROWED TO WHERE THAT ARGUMENT HOLDS. "The refusal names a supplier" is the whole
case for dropping, so where the tool declares no emitter for the argument there is no case:
measured c-override11, `composition_list_outline` declares none, its project_id was dropped, and
the run looped on "keeps being called with missing/blank required arguments" — a worse failure
than the opaque 404 it replaced. That is a side effect of this very fix, found by running it.
"""
from __future__ import annotations

from app.services.id_ledger import IdLedger
from app.services.stream_service import _inject_context_ids

BOOK = "01a03116-dd1f-728a-bad1-1041d8f830d4"
PROJ = "01a03116-deb6-7c6e-9e9f-73db5dbe79f3"
CHAP = "01a03116-ccc0-7000-8000-000000000000"


def _def(*props: str, name: str = "composition_entity_override_edit") -> dict:
    """Defaults to a tool that DECLARES an emitter for project_id — dropping is only
    justified where the refusal can name somewhere to go (see the narrowing below)."""
    return {"type": "function", "function": {
        "name": name, "description": "a tool",
        "parameters": {"type": "object",
                       "properties": {p: {"type": "string"} for p in props},
                       "required": list(props)},
        "_meta": {"tier": "R", "scope": "book"}}}


def _ledger(**known) -> IdLedger:
    led = IdLedger()
    for k, v in known.items():
        led.note(k, v)
    return led


class TestAKnownWrongIdIsDropped:
    def test_a_crosswired_id_with_no_substitute_is_removed(self):
        """The measured failure."""
        args = {"project_id": BOOK}
        _inject_context_ids(args, _def("project_id"), book_id=BOOK, chapter_id=None,
                            project_id=None, id_ledger=_ledger(book_id=BOOK))
        assert "project_id" not in args, (
            "an id the ledger identifies as a book_id was forwarded into project_id, so the "
            "tool answers 'not found' and the model learns nothing"
        )

    def test_the_ledger_really_does_recognise_it(self):
        """Guards the premise. If this stops holding, the test above passes for the wrong
        reason — nothing would be dropped and nothing would be wrong."""
        assert _ledger(book_id=BOOK).is_crosswired("project_id", BOOK) is True

    def test_it_still_SUBSTITUTES_when_there_is_something_to_substitute(self):
        """The pre-existing behaviour must be untouched: dropping is the fallback for when
        the turn has no id of that kind, never a replacement for correcting."""
        args = {"project_id": BOOK}
        _inject_context_ids(args, _def("project_id"), book_id=BOOK, chapter_id=None,
                            project_id=PROJ, id_ledger=_ledger(book_id=BOOK, project_id=PROJ))
        assert args["project_id"] == PROJ


class TestItDropsOnlyWhatItCanProve:
    """The evidence standard is the whole safety argument. Anything short of "this turn
    published that id under another name" must be left exactly as the model sent it."""

    def test_an_unknown_uuid_is_left_alone(self):
        """A cross-book call, or an id from somewhere the runtime cannot see, is the model's
        to make. Dropping it would break deliberate work."""
        other = "01a03116-9999-7999-8999-999999999999"
        args = {"project_id": other}
        _inject_context_ids(args, _def("project_id"), book_id=BOOK, chapter_id=None,
                            project_id=None, id_ledger=_ledger(book_id=BOOK))
        assert args["project_id"] == other

    def test_the_id_under_its_OWN_name_is_left_alone(self):
        """A book_id in the book_id slot is correct, not cross-wired."""
        args = {"book_id": BOOK}
        _inject_context_ids(args, _def("book_id"), book_id=None, chapter_id=None,
                            project_id=None, id_ledger=_ledger(book_id=BOOK))
        assert args["book_id"] == BOOK

    def test_with_no_ledger_nothing_is_dropped(self):
        args = {"project_id": BOOK}
        _inject_context_ids(args, _def("project_id"), book_id=BOOK, chapter_id=None,
                            project_id=None, id_ledger=None)
        assert args["project_id"] == BOOK

    def test_a_non_string_value_is_left_alone(self):
        args = {"project_id": 7}
        _inject_context_ids(args, _def("project_id"), book_id=BOOK, chapter_id=None,
                            project_id=None, id_ledger=_ledger(book_id=BOOK))
        assert args["project_id"] == 7

    def test_an_arg_the_tool_does_not_declare_is_untouched(self):
        args = {"project_id": BOOK}
        _inject_context_ids(args, _def("book_id"), book_id=None, chapter_id=None,
                            project_id=None, id_ledger=_ledger(book_id=BOOK))
        assert args["project_id"] == BOOK


class TestTheOtherKeysStillWork:
    """The control. This function's original job — filling an id a weak model omitted —
    must be unchanged for every key."""

    def test_a_missing_id_is_still_filled(self):
        args: dict = {}
        _inject_context_ids(args, _def("book_id", "chapter_id"), book_id=BOOK,
                            chapter_id=CHAP, project_id=None, id_ledger=_ledger(book_id=BOOK))
        assert args["book_id"] == BOOK
        assert args["chapter_id"] == CHAP


class TestItDropsOnlyWhereTheRefusalCanNameASupplier:
    """The narrowing, and the reason for it: dropping is better than forwarding ONLY because the
    missing-argument refusal that follows names the emitter and arms it. A tool with no declared
    emitter gets a refusal that names nowhere, and the model blank-retries into the breaker —
    measured live on composition_list_outline in c-override11."""

    def test_a_tool_with_NO_declared_emitter_keeps_the_value(self):
        args = {"project_id": BOOK}
        _inject_context_ids(args, _def("project_id", name="composition_list_outline"),
                            book_id=BOOK, chapter_id=None, project_id=None,
                            id_ledger=_ledger(book_id=BOOK))
        assert args["project_id"] == BOOK, (
            "the argument was dropped for a tool whose refusal can name no supplier, which "
            "turns an opaque 404 into a blank-args loop"
        )

    def test_a_tool_WITH_a_declared_emitter_still_drops(self):
        """The control: the narrowing must not disable the fix where it was justified."""
        args = {"project_id": BOOK}
        _inject_context_ids(args, _def("project_id", name="composition_entity_override_edit"),
                            book_id=BOOK, chapter_id=None, project_id=None,
                            id_ledger=_ledger(book_id=BOOK))
        assert "project_id" not in args

    def test_the_emitter_declarations_this_rests_on_are_real(self):
        """Guards the premise against the contract file changing underneath."""
        from app.agentruntime.toolcontract import declared_emitter

        from app.services.stream_service import _tool_contract_registry

        reg = _tool_contract_registry()
        assert declared_emitter(reg, "composition_entity_override_edit", "project_id"), (
            "the tool this narrowing keeps dropping for no longer declares an emitter"
        )
        assert not declared_emitter(reg, "composition_list_outline", "project_id")
