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

    def test_a_context_id_is_still_exempt(self):
        """The 5-red-tests lesson: the runtime injects these and repairs them itself."""
        assert _invented_supplier_ids({"book_id": "UNKNOWN_ID_PLEASE_PROVIDE"}, None, None) == []


class TestTheWordBoundaryIsRealNotSubstring:
    def test_a_word_embedded_in_a_longer_hex_token_does_not_fire(self):
        """Guarding against the arm being a naive `in` check that hits real data."""
        assert _invented_supplier_ids({"node_id": "abctodofed-1111-4000-8000-abcdefabcdef"},
                                      None, None) == []
