"""`_meta.no_context_fill` — the arguments a tool tells the backfiller to LEAVE ALONE.

`_inject_context_ids` fills a known session context id when the tool's schema declares it and
the model omitted it. That rests on an assumption which is true of almost every tool and not of
all of them: that a context id merely SCOPES a call, so supplying one the model forgot can only
help.

`composition_motif_link_edit` breaks it. Its `book_id` is optional and selects between two
incompatible endpoint rules in `MotifRepo.create_link`:

    book_id OMITTED   both endpoints must be motifs the caller OWNS
    book_id SUPPLIED  both endpoints must be `book_shared AND book_id = $book`

Measured 2026-08-24 (batches c-motiflink6 / c-motiflink7, K=5 each, gemma-4-26b-a4b-qat):

    the model called with the ambient book_id      -> refused, the caller's own motifs
                                                      are not shared into that book
    the refusal said "call again WITHOUT book_id"  -> reached the model on 4 of 4 calls
    the model called again WITHOUT book_id         -> THE RUNTIME PUT IT BACK
    same refusal, twice more                       -> the repeat-breaker ended the turn

A remedy a refusal names has to be reachable, or it is worse than no remedy: it costs the model
two more attempts and then the turn.

The field is named for the EFFECT rather than that cause because a second shape was measured
the same day and then rejected: `composition_entity_override_edit`'s ambient `project_id` is
also the wrong object (the book's CANONICAL Work, where an override needs a DERIVATIVE). But
declaring it here made things worse, not better — `composition_list_derivatives` requires a
project_id and takes nothing else, so the canonical id is a perfectly good input to the lookup
the tool wants, and suppressing the backfill left the model with no project id to look anything
up WITH. It then put the target_entity_id into project_id and book_id on three separate tools.

So the rule this field enforces — AN ARGUMENT THE RUNTIME MAY SUPPLY MUST BE ONE THE CALLER
COULD ALSO HAVE SUPPLIED AND MEANT — is necessary and not sufficient: an argument can be wrong
in a tool's own slot and still be the right thing to hold.
"""
from __future__ import annotations

import json
import pathlib

from app.services.stream_service import _inject_context_ids

BOOK = "33333333-3333-7333-8333-333333333333"
CHAPTER = "44444444-4444-7444-8444-444444444444"
PROJECT = "55555555-5555-7555-8555-555555555555"


def _tool_def(meta: dict | None = None, props: tuple[str, ...] = ("book_id",)) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "composition_motif_link_edit",
            "description": "link two motifs",
            "parameters": {
                "type": "object",
                "properties": {p: {"type": "string"} for p in props},
                "required": [],
            },
            "_meta": meta if meta is not None else {"tier": "A", "scope": "user"},
        },
    }


class TestADeclaredArgIsLeftAlone:
    def test_an_omitted_declared_arg_is_NOT_filled(self):
        """The measured failure, in one assertion."""
        out = _inject_context_ids(
            {"op": "create"},
            _tool_def({"tier": "A", "scope": "user", "no_context_fill": ["book_id"]}),
            book_id=BOOK, chapter_id=None, project_id=None,
        )
        assert "book_id" not in out, (
            "the runtime filled an argument the tool told it to leave alone — the model cannot "
            "then follow a refusal that tells it to omit that argument"
        )

    def test_a_supplied_declared_arg_is_left_exactly_as_the_model_sent_it(self):
        """Not filling is half of it. Correcting one the model DID send would take the choice
        away just as completely, in the other direction."""
        out = _inject_context_ids(
            {"op": "create", "book_id": "99999999-9999-7999-8999-999999999999"},
            _tool_def({"tier": "A", "scope": "user", "no_context_fill": ["book_id"]}),
            book_id=BOOK, chapter_id=None, project_id=None, studio=True,
        )
        assert out["book_id"] == "99999999-9999-7999-8999-999999999999"

    def test_only_the_named_arg_is_skipped(self):
        """The exemption must be surgical. A tool that opts book_id out still wants its
        chapter_id and project_id filled — otherwise this fix trades one silent breakage
        for another."""
        out = _inject_context_ids(
            {"op": "create"},
            _tool_def({"tier": "A", "scope": "user", "no_context_fill": ["book_id"]},
                      props=("book_id", "chapter_id", "project_id")),
            book_id=BOOK, chapter_id=CHAPTER, project_id=PROJECT,
        )
        assert "book_id" not in out
        assert out.get("chapter_id") == CHAPTER
        assert out.get("project_id") == PROJECT


class TestEveryOtherToolIsUnchanged:
    """The control. This function exists because a mid-tier model cannot reliably transcribe a
    UUID, and that measured blocker must keep being solved for the tools that never declare the
    new field — which is all but one of them."""

    def test_a_tool_with_no_declaration_still_gets_its_book_id(self):
        out = _inject_context_ids(
            {"op": "create"}, _tool_def(), book_id=BOOK, chapter_id=None, project_id=None,
        )
        assert out.get("book_id") == BOOK

    def test_an_empty_declaration_changes_nothing(self):
        out = _inject_context_ids(
            {"op": "create"},
            _tool_def({"tier": "A", "scope": "user", "no_context_fill": []}),
            book_id=BOOK, chapter_id=None, project_id=None,
        )
        assert out.get("book_id") == BOOK

    def test_a_malformed_declaration_is_ignored_rather_than_crashing(self):
        """A bad _meta must never take the turn down: the worst acceptable outcome is the old
        behaviour."""
        for bad in ("book_id", 7, {"book_id": True}, [None, 3]):
            out = _inject_context_ids(
                {"op": "create"},
                _tool_def({"tier": "A", "scope": "user", "no_context_fill": bad}),
                book_id=BOOK, chapter_id=None, project_id=None,
            )
            assert out.get("book_id") == BOOK, f"declaration {bad!r} changed behaviour"


class TestTheToolActuallyDeclaresIt:
    """The half that makes the rest matter. The consumer honouring a field nobody sets is a
    mechanism that never runs — this loop has shipped one of those before."""

    def test_the_catalogue_snapshot_or_the_source_declares_it(self):
        # parents: [0]=tests [1]=chat-service [2]=services. An earlier version used
        # parents[3] and looked for services/../composition-service, which does not exist —
        # so `exists()` was False, the test returned early, and it PASSED against a tree with
        # the declaration removed. A skip-on-missing guard is how a check stops checking.
        src = (pathlib.Path(__file__).resolve().parents[2]
               / "composition-service" / "app" / "mcp" / "server.py")
        assert src.exists(), f"composition-service source not found at {src}"
        text = src.read_text(encoding="utf-8")
        # composition_entity_override_edit was declared here for a day and taken back out:
        # its ambient project_id IS the wrong Work, but suppressing the backfill starved the
        # model of the only project id it had, and it put the target_entity_id into project_id
        # and book_id on three other tools. Recorded on
        # D-THE-AMBIENT-PROJECT-IS-THE-WRONG-WORK-AND-THE-RUNTIME-SUPPLIES-IT.
        for tool, arg in (("composition_motif_link_edit", "book_id"),):
            i = text.find(f'name="{tool}"')
            assert i != -1, f"{tool}'s registration moved"
            assert f'no_context_fill=["{arg}"]' in text[i:i + 2500], (
                f"{tool} no longer declares {arg} no-context-fill, so the runtime will fill it "
                f"again and the tool's refusal becomes unfollowable"
            )
