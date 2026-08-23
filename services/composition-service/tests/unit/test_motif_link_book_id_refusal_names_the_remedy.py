"""D-AN-OPTIONAL-ARG-SWITCHES-THE-MODE-AND-THE-REFUSAL-HIDES-IT.

`composition_motif_link_edit`'s `book_id` is optional and silently selects between two
incompatible endpoint rules inside `MotifRepo.create_link`:

    book_id OMITTED   both endpoints must be motifs the caller OWNS
    book_id SUPPLIED  both endpoints must be `book_shared AND book_id = $book`

Measured 2026-08-24 (batch c-motiflink5, K=5): on both runs that got past the Tier-A approval
gate, the model resolved the two motifs to their real ids, passed the correct direction and
kind, and also passed the ambient `book_id`. Its own private motifs are not `book_shared`, so
the repo raised, the tool mapped it to H13's uniform "not found or not accessible", and the
model was told two motifs it had just listed by id did not exist. There is no path from that
message back to the working call, and both runs stopped there.

`EndpointsOwnedNotShared` separates the ONE miss that has a remedy. These tests hold the two
halves that make that safe:

  * the actionable arm fires when the caller owns BOTH endpoints, and the message names the
    remedy (`WITHOUT book_id`) rather than describing the failure;
  * every OTHER miss still raises plain `LookupError`, so H13's no-existence-oracle property is
    untouched — a foreign or absent endpoint must stay indistinguishable.

The subclassing is load-bearing and is asserted directly: an existing `except LookupError`
elsewhere must keep catching the new exception, or this change breaks callers it never saw.
"""
from __future__ import annotations

import uuid

import pytest

from app.db.repositories.motif_repo import EndpointsOwnedNotShared


class TestTheExceptionIsSafeToIntroduce:
    def test_it_is_a_LookupError(self):
        """Every `except LookupError` already written must keep catching it. If this stops
        holding, callers that never heard of this class start leaking a raw exception."""
        assert issubclass(EndpointsOwnedNotShared, LookupError)

    def test_an_existing_lookuperror_handler_still_catches_it(self):
        """The subclassing claim, exercised rather than asserted about the class object."""
        try:
            raise EndpointsOwnedNotShared("both endpoints are motifs you own")
        except LookupError as e:
            assert "you own" in str(e)
        else:  # pragma: no cover - the raise above cannot fall through
            pytest.fail("an except LookupError arm did not catch it")


class TestTheRefusalNamesTheRemedy:
    """The tool's message is the whole point of the change: the model must be able to act on
    it. These read the source rather than standing a server up, so they stay a unit test —
    what matters is that the remedy is stated, and stated as an instruction."""

    @staticmethod
    def _tool_source() -> str:
        import inspect

        from app.mcp import server

        return inspect.getsource(server)

    def test_the_actionable_arm_exists_and_precedes_the_uniform_one(self):
        src = self._tool_source()
        i_specific = src.find("except EndpointsOwnedNotShared:")
        i_uniform = src.find("except LookupError:", i_specific if i_specific > 0 else 0)
        assert i_specific != -1, "the actionable arm is gone"
        assert i_uniform > i_specific, (
            "the specific arm must be ordered BEFORE the LookupError arm it subclasses, "
            "or it can never fire"
        )

    def test_the_message_tells_the_caller_what_to_do(self):
        src = self._tool_source()
        i = src.find("except EndpointsOwnedNotShared:")
        arm = src[i:i + 1500]
        assert "WITHOUT book_id" in arm, (
            "the refusal must name the remedy, not merely describe the failure — a model that "
            "is told what is wrong and not what to do next repeats the call"
        )

    def test_the_uniform_refusal_is_still_there_for_every_other_miss(self):
        """The control. If this change had replaced H13 rather than narrowed it, a foreign or
        absent endpoint would become distinguishable and the tool would be an existence
        oracle."""
        src = self._tool_source()
        i = src.find("except EndpointsOwnedNotShared:")
        after = src[i:i + 1600]
        assert "raise uniform_not_accessible()" in after, (
            "the uniform refusal must survive for every miss that is NOT both-owned"
        )


class TestTheArgumentSaysWhichModeItSelects:
    def test_book_id_is_no_longer_a_bare_annotation(self):
        """It was `book_id: str | None = None` with no Field description, so the emitted
        schema said only {anyOf: [string, null], title: 'Book Id'} — nothing about the fact
        that supplying it CHANGES WHICH ENDPOINTS ARE ACCEPTED."""
        from app.mcp.server import _MotifLinkEditArgs

        schema = _MotifLinkEditArgs.model_json_schema()
        desc = (schema["properties"]["book_id"].get("description") or "")
        assert desc.strip(), "book_id still carries no description"
        assert "OMIT" in desc.upper(), "it must say the usual case is to omit it"
        assert "SHARED" in desc.upper(), "it must say what supplying it selects"

    def test_the_two_motif_ids_kept_their_descriptions(self):
        """A bystander check: this change edited the field beside them."""
        from app.mcp.server import _MotifLinkEditArgs

        props = _MotifLinkEditArgs.model_json_schema()["properties"]
        for f in ("from_motif_id", "to_motif_id"):
            assert "composition_motif_search" in (props[f].get("description") or ""), (
                f"{f} lost the supplier its refusal quotes"
            )
