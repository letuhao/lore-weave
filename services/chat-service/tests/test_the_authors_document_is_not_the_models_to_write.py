"""DQ-T55, answered by the owner 2026-08-28.

    "REPLACE `source_markdown` WITH A REFERENCE THE RUNTIME RESOLVES — a chapter_id, or an
     explicit 'the author's last message' — so the server fetches the text and the model cannot
     author its own source at all. … The point is STRUCTURAL, not defensive: fabricated source
     material stops being something to detect and becomes something that cannot be expressed."

THE DEFECT (D-GROUNDED-REQUEST-ANSWERED-WITH-UNGROUNDED-PROSE, "the worst user-visible outcome
measured in this loop"): asked to DELETE a glossary kind, the model instead called
`glossary_extract_entities_from_doc` with a `source_markdown` it invented wholesale — "a young
cultivator named Wei Wuxian who lives in the Azure Cloud Sect" — and the SAME invented document
was handed to the tool against several different books. A canned sample it reaches for.

FIVE PROSE INTERVENTIONS WERE MEASURED AND REFUTED before this, including the registry recipe
already saying it in the imperative ("feed it the user's notes VERBATIM"). That is why the remedy
had to be structural.

🔴 WHY THE ENFORCEMENT IS IN CHAT-SERVICE. This is the only layer that can tell the model's text
from the server's — both arrive in the same MCP payload, and the service on the far side has no
way to know who wrote the field. glossary-service declares the contract and refuses a caller that
names no source; chat-service is where the model's value is actually discarded.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.stream_service import (  # noqa: E402
    _AUTHOR_SOURCED_TOOLS,
    _SOURCE_REF_LAST_USER_MESSAGE,
    _resolve_authors_source,
)

TOOL = "glossary_extract_entities_from_doc"
FABRICATED = "a young cultivator named Wei Wuxian who lives in the Azure Cloud Sect"
AUTHOR_SAID = "My book is about Aldric Vane, a warden of Hollow Keep."


class TestTheModelsDocumentIsDiscarded:
    def test_a_fabricated_source_is_replaced_by_what_the_author_wrote(self):
        args = {"book_id": "b", "source_ref": _SOURCE_REF_LAST_USER_MESSAGE,
                "source_markdown": FABRICATED}
        _resolve_authors_source(args, TOOL, AUTHOR_SAID)
        assert args["source_markdown"] == AUTHOR_SAID
        assert FABRICATED not in args["source_markdown"]

    def test_the_overwrite_is_UNCONDITIONAL_not_fill_if_blank(self):
        """🔴 THE DISTINCTION THAT MAKES THIS WORK. `_inject_context_ids`, right beside it, fills
        only a MISSING argument — deliberately, so a cross-book call is respected. Copying that
        shape here would leave the fabrication case untouched, because a fabricating model always
        supplies text. The empty field was never the problem."""
        args = {"source_ref": _SOURCE_REF_LAST_USER_MESSAGE, "source_markdown": FABRICATED}
        _resolve_authors_source(args, TOOL, AUTHOR_SAID)
        assert args["source_markdown"] == AUTHOR_SAID, (
            "a non-empty model-authored document survived — the resolver is fill-if-blank"
        )

    def test_an_author_message_that_matches_is_left_alone(self):
        """The honest case: the model pasted what the author actually said. Same result, and no
        warning to cry wolf with."""
        args = {"source_ref": _SOURCE_REF_LAST_USER_MESSAGE, "source_markdown": AUTHOR_SAID}
        _resolve_authors_source(args, TOOL, AUTHOR_SAID)
        assert args["source_markdown"] == AUTHOR_SAID


class TestItRefusesRatherThanGuesses:
    def test_no_source_ref_strips_the_text_and_leaves_the_refusal_to_the_owner(self):
        """One refusal, written once, on the side that owns the contract. glossary-service names
        the accepted value; inventing a second message here would drift from it."""
        args = {"source_markdown": FABRICATED}
        _resolve_authors_source(args, TOOL, AUTHOR_SAID)
        assert "source_markdown" not in args

    def test_an_unresolvable_reference_strips_the_text(self):
        """chapter_id is the owner's other named reference and is NOT built. It must not fall
        through to whatever text the model attached — that would be the defect wearing a
        reference's clothes."""
        args = {"source_ref": "chapter_id:019f5239-0000-0000-0000-000000000000",
                "source_markdown": FABRICATED}
        _resolve_authors_source(args, TOOL, AUTHOR_SAID)
        assert "source_markdown" not in args

    def test_an_empty_author_message_resolves_to_empty_never_to_the_models_text(self):
        """If the author has written nothing, the answer is nothing — the far side then says the
        reference resolved empty. Falling back to the model's text would be the fabrication."""
        args = {"source_ref": _SOURCE_REF_LAST_USER_MESSAGE, "source_markdown": FABRICATED}
        _resolve_authors_source(args, TOOL, "   ")
        assert args["source_markdown"] == ""


class TestItIsScopedToTheContractAndNotToAFieldName:
    def test_plan_propose_spec_is_UNTOUCHED(self):
        """🔴 THE BLAST RADIUS THIS AVOIDS. `plan_propose_spec.source_markdown` is 174 of the 686
        measured prose-bearing arguments, and there the model AUTHORING the document is the whole
        job — the registry recipe instructs it to write a structured outline. Keying this rule on
        the field NAME would break that tool while claiming to fix this one."""
        args = {"source_markdown": "# 1. Arc Overview\n## Arc I", "mode": "rules"}
        before = dict(args)
        _resolve_authors_source(args, "plan_propose_spec", AUTHOR_SAID)
        assert args == before

    def test_the_rule_is_keyed_on_the_tool(self):
        assert TOOL in _AUTHOR_SOURCED_TOOLS
        assert "plan_propose_spec" not in _AUTHOR_SOURCED_TOOLS
        assert "book_chapter_save_draft" not in _AUTHOR_SOURCED_TOOLS

    def test_a_non_dict_args_object_is_survivable(self):
        _resolve_authors_source(None, TOOL, AUTHOR_SAID)  # must not raise


class TestTheCallSitePassesAnArgumentThatEXISTS:
    """🔴 A CALL-SITE GUARD, AND IT CAUGHT A REAL ONE. The first version passed
    `user_message_content` — the name this turn's message carries in `_emit_chat_turn`, which is
    NOT in scope inside the tool loop. It parsed cleanly and would have raised NameError on every
    extract call: a fix that looks shipped and is dead."""

    SRC = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")

    def test_the_resolver_is_called_from_the_dispatch(self):
        assert "_resolve_authors_source(args_obj, c[\"name\"], request_text)" in self.SRC

    def test_the_name_it_passes_is_a_parameter_of_the_enclosing_function(self):
        import ast
        tree = ast.parse(self.SRC)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.AsyncFunctionDef) and n.name == "_stream_with_tools")
        params = {a.arg for a in fn.args.args} | {a.arg for a in fn.args.kwonlyargs}
        assert "request_text" in params, (
            "the resolver is handed a name the tool loop does not define — it will NameError on "
            "every call and the fix is dead"
        )
