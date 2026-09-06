"""A NAMED PLACEHOLDER reached a Tier-A confirm card.

MEASURED LIVE 2026-08-21, batch 21, composition_reference_update, 5 of 5 runs. The
reference_source table is EMPTY on this deployment, so no real reference id exists — and the
model SAID so in prose ("I need to know which reference you are referring to") while
simultaneously calling the tool with:

    {"title": [], "project_id": "01a023aa-…", "reference_id": "UNKNOWN_ID_PLEASE_PROVIDE"}

A Tier-A card was minted for it. The author is asked to approve updating a reference whose id is
the literal text UNKNOWN_ID_PLEASE_PROVIDE.

WHY EVERY EXISTING ARM MISSED IT:
  * nil-UUID       — it is not all-zero.
  * whitespace     — it has no spaces; the underscores are what a stub uses instead.
  * declared-UUID  — `reference_id` is advertised as {"title": "Reference Id", "type": "string"}
                     with NO description, so there is no declaration to read. That is the
                     502-of-1314 undeclared-property class this loop measured.

THIRD PLACEHOLDER TO REACH A CARD, after model_ref="default" (batch 18) and
run_id="run_12345_placeholder". The token list is deliberately SMALL and every entry is a word
that appears in a fill-me-in stub and never in an identifier this platform issues. A UUID cannot
contain any of them — hex stops at `f`, so "unknown", "placeholder", "provide" and "todo" are
unreachable.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.stream_service import _invented_supplier_ids  # noqa: E402

REAL = "01a02028-9c26-722a-a2d0-80fdca7f2de0"
#: composition_reference_update's real declaration, copied from the live catalogue.
REF_PROPS = {"reference_id": {"type": "string"}, "project_id": {"type": "string"}}


class TestTheMeasuredCallIsCaught:
    """THE FALSIFIER — the exact argument from 5 of 5 live runs."""

    def test_unknown_id_please_provide_is_dropped(self):
        assert _invented_supplier_ids(
            {"reference_id": "UNKNOWN_ID_PLEASE_PROVIDE"}, None, REF_PROPS) == ["reference_id"]

    def test_it_works_with_no_declaration_at_all(self):
        """The whole point: this argument declares nothing, so the declaration arm is blind."""
        assert _invented_supplier_ids({"reference_id": "UNKNOWN_ID_PLEASE_PROVIDE"}, None, {}) == [
            "reference_id"]


class TestTheOtherPlaceholdersThisLoopHasSeen:
    def test_the_plan_compile_placeholder(self):
        assert _invented_supplier_ids({"run_id": "run_12345_placeholder"}, None, None) == ["run_id"]

    def test_a_your_id_here_stub(self):
        assert _invented_supplier_ids({"node_id": "YOUR_ID_HERE"}, None, None) == ["node_id"]

    def test_it_covers_the_ref_convention_too(self):
        assert _invented_supplier_ids({"model_ref": "TODO"}, None, None) == ["model_ref"]


class TestARealIdentifierIsNeverTouched:
    """🔴 The boundary. A UUID cannot contain these words — hex stops at `f` — so this arm must
    never fire on one, and it must not fire on a legitimate slug or code either."""

    def test_a_uuid_passes(self):
        assert _invented_supplier_ids({"reference_id": REAL}, None, REF_PROPS) == []

    def test_a_real_slug_passes(self):
        assert _invented_supplier_ids({"template_id": "throwaway-loop-skeleton-b15"}, None, None) == []

    def test_a_hex_id_containing_dead_beef_passes(self):
        """`deadbeef` is hex and looks word-ish; it must not be mistaken for a stub."""
        assert _invented_supplier_ids(
            {"node_id": "deadbeef-0000-4000-8000-deadbeefcafe"}, None, None) == []

    def test_a_non_identifier_argument_is_untouched(self):
        """Scoped to the *_id / *_ref conventions — a title or a query may say anything."""
        assert _invented_supplier_ids({"title": "TODO: name this chapter"}, None, None) == []
        assert _invented_supplier_ids({"query": "what is unknown about Aldric"}, None, None) == []

    def test_a_context_id_IS_NOT_exempt_from_THIS_arm(self):
        """🔴 REVERSED 2026-08-27 ON EVIDENCE, and the old assertion is quoted so the change is
        not mistaken for a widening that slipped through: it read "the runtime injects these and
        repairs them itself" and required `book_id="UNKNOWN_ID_PLEASE_PROVIDE"` to survive.

        The exemption's real reason — recorded on the arm below — is that the RUNTIME injects
        context ids and they are not guaranteed to be UUIDs, so dropping one once deleted a
        value the runtime itself had supplied. That reasoning does not reach a value carrying
        the word `unknown` or `placeholder`. The runtime does not inject those; a model does.

        MEASURED over every recorded tool call: 320 non-UUID context ids, and not one looks
        like a runtime injection. 155 carry one of these tokens —
        `current_book_id_placeholder` alone appears 144 times — and the rest are fixture names,
        book TITLES, "all" and "book_list". The old assertion protected a value nothing
        produces, at the cost of 155 real ones.
        """
        assert _invented_supplier_ids(
            {"book_id": "UNKNOWN_ID_PLEASE_PROVIDE"}, None, None) == ["book_id"]

    def test_and_the_exemption_the_5_RED_TESTS_BOUGHT_still_holds(self):
        """The narrowing must not reopen the case that cost five tests. `b1` is what the runtime
        injects in a degraded turn; it carries no placeholder token, so this arm cannot see it
        and every other arm still exempts it."""
        props = {"book_id": {"type": "string", "description": "the book's id (UUID)"}}
        assert _invented_supplier_ids({"book_id": "b1"}, None, props) == []
        assert _invented_supplier_ids({"book_id": "b1"}, None, None) == []


class TestTheWordBoundaryIsRealNotSubstring:
    def test_a_word_embedded_in_a_longer_hex_token_does_not_fire(self):
        """Guarding against the arm being a naive `in` check that hits real data."""
        assert _invented_supplier_ids({"node_id": "abctodofed-1111-4000-8000-abcdefabcdef"},
                                      None, None) == []


class TestTheWordListWasTooNarrowAndTheShapeRuleReplacesIt:
    """🔴 MY FIRST FIX WAS REFUTED BY THE VERY NEXT RUN.

    The word-list arm caught reference_id="UNKNOWN_ID_PLEASE_PROVIDE". Re-measured live on the
    deployed build, the model's next attempt was "REPLACE_WITH_ACTUAL_REFERENCE_ID" — which
    shares not one word with it, and sailed through. A blacklist is whack-a-mole against text a
    model invents freely.

    What the two share is SHAPE, and the shape rule is measured rather than assumed: across every
    code this platform has ever issued — 240 motifs, 53 arc templates — exactly ZERO contain an
    uppercase letter, and a UUID is lowercase hex.
    """

    def test_the_second_placeholder_is_caught(self):
        assert _invented_supplier_ids(
            {"reference_id": "REPLACE_WITH_ACTUAL_REFERENCE_ID"}, None, REF_PROPS) == [
            "reference_id"]

    def test_an_arbitrary_screaming_snake_stub_is_caught(self):
        """The point of a shape rule: it does not need to have seen the wording before."""
        assert _invented_supplier_ids({"node_id": "SOME_ID_I_MADE_UP"}, None, None) == ["node_id"]

    def test_a_lowercase_slug_still_passes(self):
        assert _invented_supplier_ids({"template_id": "throwaway-loop-skeleton-b15"}, None, None) == []

    def test_an_UPPERCASE_UUID_still_passes(self):
        """A UUID is a UUID whatever its case — the arm must test UUID-ness first."""
        assert _invented_supplier_ids(
            {"node_id": "01A02028-9C26-722A-A2D0-80FDCA7F2DE0"}, None, None) == []

    def test_image_ref_is_left_to_the_declaration_arm(self):
        """A MinIO object key may legitimately be mixed-case, so the shape rule is *_id only."""
        props = {"image_ref": {"type": "string",
                               "description": "optional MinIO object key of an already-uploaded base image"}}
        assert _invented_supplier_ids({"image_ref": "maps/Ashfall-Base.png"}, None, props) == []


class TestTheShapeRuleIsNarrowedToScreamingSnake:
    """🔴 THE SUITE CAUGHT MY SECOND ATTEMPT TOO, and it was right to.

    "not a UUID and contains an uppercase letter" broke a standing invariant of this same
    function: `test_with_no_properties_at_all_nothing_is_claimed` pins that world_id="Ashfall" is
    NOT dropped when nothing is declared (D-FJ-2 — no declaration, no judgement). It would also
    have caught a legitimate opaque vendor reference like "ABC-123".

    SCREAMING_SNAKE_CASE is what both measured placeholders actually are, and what neither a name
    nor a vendor id is.
    """

    def test_a_bare_NAME_is_still_left_alone(self):
        """The batch-8 case, and the invariant the broader rule broke."""
        assert _invented_supplier_ids({"world_id": "Ashfall"}, None, None) == []

    def test_an_opaque_vendor_reference_passes(self):
        assert _invented_supplier_ids({"external_id": "ABC-123"}, None, None) == []

    def test_a_single_uppercase_word_passes(self):
        """No underscore, so not a stub shape."""
        assert _invented_supplier_ids({"node_id": "EMBERFALL"}, None, None) == []

    def test_both_measured_placeholders_still_caught(self):
        assert _invented_supplier_ids({"reference_id": "UNKNOWN_ID_PLEASE_PROVIDE"}, None, None) \
            == ["reference_id"]
        assert _invented_supplier_ids(
            {"reference_id": "REPLACE_WITH_ACTUAL_REFERENCE_ID"}, None, None) == ["reference_id"]
