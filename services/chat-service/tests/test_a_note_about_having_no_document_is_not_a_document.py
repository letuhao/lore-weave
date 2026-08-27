"""D-THE-DOCUMENT-HANDED-TO-AN-EXTRACT-TOOL-IS-A-MESSAGE-ABOUT-HAVING-NO-DOCUMENT.

    THE INVARIANT. A value recognisable as a NOTE ABOUT HAVING NO CONTENT, without knowing
    anything about the author's book, is knowably not content — the same sentence
    `_is_nil_uuid` already carries for identifiers, one argument-kind wider.

Having nothing to work from, the model does not ask the author. It writes a sentence saying it
has nothing and puts that sentence in the payload slot.

🔴 MEASURED 2026-08-27 over `loreweave_chat.chat_messages.tool_calls` — 508 arguments carrying
a document, 10 hollow, across two tools:

    glossary_extract_entities_from_doc.source_markdown   9   extraction runs on the note
    book_chapter_save_draft.body                         1   the note becomes the CHAPTER

The chapter one is the worst and is the one a narrow rule misses — the other nine are caught
without the `please provide` arm, and it is not:

    "I will perform a consistency check on your story. Please provide the text or specify
     which chapters I should analyze."

So that arm is kept and NARROWED to a request for CONTENT specifically, which costs nothing:
the loose and narrow rules flag exactly the same 10 of 508. THE RESIDUAL FALSE-POSITIVE
SURFACE IS NAMED — a chapter whose dialogue reads "please provide the text". None of the 508
recorded documents is one.

WHAT THIS DOES NOT DO. It does not judge whether a real document is TRUE, grounded, or the
author's. A fabricated story about Wei Wuxian sails straight through, exactly as a well-formed
invented UUID sails through `_invented_supplier_ids` — that is
D-GROUNDED-REQUEST-ANSWERED-WITH-UNGROUNDED-PROSE, blocked on DQ-T55, and a different question.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.stream_service import (  # noqa: E402
    DOCUMENT_ARGS,
    _hollow_document_args,
    _hollow_document_note,
    _is_hollow_document,
)

# The measured instances, verbatim from the store.
CHAPTER_BODY = ("I will perform a consistency check on your story. Please provide the text or "
                "specify which chapters I should analyze.")
NO_NOTES = "The user has not provided any story notes or descriptions yet."
BRACKETED = ("[No story content provided yet. Please provide your story idea, notes, or a "
             "summary to begin the extraction process.]")
NARRATED = ("(No source text provided in the current conversation history to extract from. I "
            "will ask the user to provide the story details, notes, or a draft.)")
PASTE = ("[No source document provided yet. Please paste your notes, character descriptions, "
         "or world details to begin capturing them.]")

REAL_PROSE = ("The air in the archives was thick with the scent of old parchment and something "
              "sharper — the metallic tang of ozone that always preceded a surge in the Ember.")


def test_the_MEASURED_instances_are_all_caught():
    """🔴 THE FALSIFIER, on the original instances: the exact strings from the store."""
    for doc in (CHAPTER_BODY, NO_NOTES, BRACKETED, NARRATED, PASTE):
        assert _is_hollow_document(doc), doc[:60]


def test_the_CHAPTER_BODY_instance_is_caught_at_the_argument_level():
    """The worst one: this would be saved into the manuscript as the chapter's prose."""
    assert _hollow_document_args({"chapter_id": "x", "body": CHAPTER_BODY}) == ["body"]


def test_real_prose_is_untouched():
    assert not _is_hollow_document(REAL_PROSE)
    assert _hollow_document_args({"body": REAL_PROSE}) == []


def test_FICTION_that_uses_the_phrase_is_not_refused():
    """🔴 THE PRECISION ARM, and the reason `please provide` is narrowed rather than dropped.
    A false refusal here deletes prose the author wanted written."""
    for doc in (
        '"Please provide the codex," the Regent said, "or I take the hand that holds it."',
        "Aldric asked the archivist to provide the ledger before the storm broke.",
        "She would not provide the text of the oath, not even under the Ember's light.",
        "The contract required him to provide a full account of the chapters he had burned.",
    ):
        assert not _is_hollow_document(doc), doc[:60]


def test_the_loose_arm_is_LOAD_BEARING_not_decoration():
    """The other nine instances are caught without `please provide`; the chapter body is not.
    If this ever fails, the arm has become removable and the trade should be re-measured."""
    without_please = [d for d in (NO_NOTES, BRACKETED, NARRATED, PASTE) if _is_hollow_document(d)]
    assert len(without_please) == 4
    stripped = CHAPTER_BODY.replace("Please provide the text or specify which chapters "
                                    "I should analyze.", "").strip()
    assert not _is_hollow_document(stripped), (
        "the chapter-body instance is now caught by some OTHER arm — the `please provide` arm "
        "may no longer be load-bearing, and its false-positive cost should be re-weighed"
    )


def test_only_DOCUMENT_arguments_are_touched():
    """PRECISION on the other axis, and the reason the name set is closed. `description`,
    `summary`, `notes` and `instructions` are deliberately OUT: no instance was measured on
    any of them, and a refusal with no evidence behind it deletes values that were fine."""
    assert _hollow_document_args({"description": NO_NOTES}) == []
    assert _hollow_document_args({"summary": NO_NOTES}) == []
    assert _hollow_document_args({"instructions": NO_NOTES}) == []
    assert _hollow_document_args({"source_markdown": NO_NOTES}) == ["source_markdown"]
    for name in ("description", "summary", "notes", "instructions"):
        assert name not in DOCUMENT_ARGS


def test_non_strings_and_junk_are_not_its_business():
    for v in (None, 7, [], {}, b"bytes", ""):
        assert not _is_hollow_document(v)


def test_the_note_says_what_was_wrong_and_where_content_comes_from():
    """🔴 THE GENERIC MISSING-ARGUMENT SENTENCE WOULD CALL THIS FORGOTTEN. A document is
    model-supplied, so without its own arm the model is told it forgot something — when it did
    not forget, it knowingly had nothing. The sentence has to say so and say where to go."""
    note = _hollow_document_note({"source_markdown": NO_NOTES})
    assert "source_markdown" in note
    low = note.lower()
    assert "not a document" in low
    assert "ask the author" in low
    assert "do not compose one yourself" in low
    assert _hollow_document_note({}) == ""


def test_a_FABRICATED_document_still_passes_and_that_is_stated():
    """WHAT THIS DOES NOT COVER, asserted rather than only written in prose. The parent defect
    — a document the model invented wholesale — is NOT addressed by a shape test, exactly as a
    well-formed invented UUID is not addressed by `_is_nil_uuid`."""
    fabricated = ("The story follows a young cultivator named Wei Wuxian who lives in the "
                  "Azure Cloud Sect. He is accompanied by his loyal companion.")
    assert not _is_hollow_document(fabricated), (
        "this now fires on a FABRICATED document — the rule has widened from 'recognisably "
        "not content' into 'judged ungrounded', which is DQ-T55's question and needs its "
        "precision measured against real books before shipping"
    )
