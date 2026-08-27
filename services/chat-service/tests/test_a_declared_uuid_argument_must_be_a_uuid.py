"""D-DECLARED-UUID-IN-PROSE-ONLY — the requirement is stated where no validator can read it.

MEASURED LIVE 2026-08-14, batch 8, K=3. Asked *"Make a new map called Saltmarsh in my Ashfall
world"*, the model called `world_map_create` on 3 of 3 runs with:

    {"name": "Saltmarsh", "world_id": "Ashfall"}

— the world's NAME where a UUID is required. A Tier-A confirm card was minted for a call the
service can only reject, so the author is asked to approve work that cannot happen.

MEASURED ACROSS THE LIVE CATALOGUE, and this is why it is a class rather than a tool:

    *_id properties whose DESCRIPTION says UUID : 219
      declaring format:uuid                     :   0
      not declaring it                          : 219   (glossary 72, book 54, plan 31,
                                                          translation 23, world 20, …)

So `"Ashfall"` is a schema-VALID `world_id` everywhere on this platform. The requirement lives in
prose the validator never sees.

THE INVARIANT: an argument the tool declares as a UUID must be a UUID before a card is minted for
it. Reading the DESCRIPTION is not inference — it is the only declaration there is until the
providers add `format: uuid`, and it is the same move as reading `tier` or `synonyms` rather than
guessing from a name.

🔴 SCOPED AWAY FROM THE CASE THIS FUNCTION ALREADY LEARNED. Its own comment records that including
`context` deleted `book_id="b1"` — a value the RUNTIME injects, not guaranteed to be a UUID — and
turned 5 tests red. That reasoning still holds, so the three context ids are excluded by name:
`_inject_context_ids` owns them and repairs a malformed one by SUBSTITUTING the value the server
knows. For a non-context id there is nothing to substitute, so the honest move is to drop it and
report it missing, which sends the model to look it up.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.services.stream_service import (  # noqa: E402
    _RUNTIME_CONTEXT_IDS,
    _declares_uuid,
    _invented_supplier_ids,
)

#: world_map_create's real declaration, copied from the live catalogue: type string, UUID stated
#: only in the description.
WORLD_PROPS = {
    "world_id": {"type": "string",
                 "description": "the world this map belongs to (UUID; you must own it)"},
    "name": {"type": "string", "description": "the map's name, e.g. 'The Northern Realms'"},
}
REAL = "01a02028-9c26-722a-a2d0-80fdca7f2de0"


def test_the_measured_call_is_caught():
    """THE FALSIFIER — the exact arguments from the live run."""
    assert _invented_supplier_ids(
        {"name": "Saltmarsh", "world_id": "Ashfall"}, None, WORLD_PROPS) == ["world_id"]


class TestAnIdWithWhitespaceIsAName:
    """🔴 THE DECLARATION ARM COVERS 219 OF 496 `*_id` PROPERTIES. The other 277 say nothing about
    their format — composition alone accounts for 200 — so they are invisible to it.

    MEASURED LIVE 2026-08-14, batch 14: composition_arc_get was called with
    node_id="The Hollow Keep", the arc's TITLE, and again with "arc_1". Its description says
    merely "The arc/saga (structure_node) id", so nothing declared could catch it.

    Whitespace needs no declaration to be certain: no identifier this platform issues contains a
    space — not a UUID, not a slug, not a code."""

    def test_the_measured_call_is_caught_with_NO_declaration(self):
        """THE FALSIFIER for this arm — properties deliberately say nothing about UUIDs."""
        props = {"node_id": {"type": "string", "description": "The arc/saga (structure_node) id."}}
        assert _invented_supplier_ids({"node_id": "The Hollow Keep"}, None, props) == ["node_id"]

    def test_a_spaceless_placeholder_is_NOT_caught_by_this_arm(self):
        """Stated so the limit is honest: "arc_1" has no whitespace and no declaration, so this
        arm does not see it. It is the residual, and the declaration gap is what would close it."""
        props = {"node_id": {"type": "string", "description": "The arc/saga (structure_node) id."}}
        assert _invented_supplier_ids({"node_id": "arc_1"}, None, props) == []

    def test_a_real_uuid_has_no_whitespace_and_passes(self):
        assert _invented_supplier_ids({"node_id": REAL}, None, None) == []

    def test_a_context_id_is_still_exempt(self):
        """book_id="b1" has no whitespace so this arm never sees it — but the exemption is kept
        explicit, because a runtime-injected value must not be judged here at all."""
        assert _invented_supplier_ids({"book_id": "some book"}, None, None) == []

    def test_a_non_id_argument_with_spaces_is_untouched(self):
        """Scoped to the `*_id` convention — a title or a query is full of spaces by nature."""
        assert _invented_supplier_ids({"title": "The Hollow Keep"}, None, None) == []


def test_a_real_uuid_passes():
    """The existing rule is untouched: a valid UUID is accepted even if it is the WRONG world —
    whether it is the right row remains the tool's question."""
    assert _invented_supplier_ids(
        {"name": "Saltmarsh", "world_id": REAL}, None, WORLD_PROPS) == []


def test_an_argument_that_does_not_declare_uuid_is_left_alone():
    """Only what the tool DECLARES. An `*_id` whose description says nothing about UUIDs may
    legitimately be an opaque string, and refusing it would break real calls."""
    props = {"external_id": {"type": "string", "description": "the vendor's own reference"}}
    assert _invented_supplier_ids({"external_id": "abc-123"}, None, props) == []


def test_with_no_properties_at_all_nothing_is_claimed():
    """No declaration, no judgement — the D-FJ-2 rule this file already follows: with nothing
    declared the runtime knows nothing and must not guess."""
    assert _invented_supplier_ids({"world_id": "Ashfall"}, None, None) == []
    assert _invented_supplier_ids({"world_id": "Ashfall"}, None, {}) == []


class TestTheContextIdsAreDeliberatelyExempt:
    """The 5-red-tests lesson, pinned so it cannot be undone by a later widening."""

    def test_the_three_are_named(self):
        assert _RUNTIME_CONTEXT_IDS == {"book_id", "chapter_id", "project_id"}

    def test_a_non_uuid_context_id_is_NOT_dropped(self):
        """`book_id="b1"` is what the runtime injects in tests and may inject in degraded real
        turns. Dropping it deletes a value the runtime itself supplied and breaks the dispatch —
        measured once already, at the cost of 5 tests."""
        props = {"book_id": {"type": "string", "description": "the book's id (UUID)"}}
        assert _invented_supplier_ids({"book_id": "b1"}, None, props) == []

    def test_a_context_id_holding_a_PLACEHOLDER_WORD_is_dropped(self):
        """🔴 THE EXEMPTION IS PER-ARM, AND THIS ARM IS NOT ENTITLED TO IT. The exemption
        exists because the RUNTIME injects context ids and they are not guaranteed to be
        UUIDs. That reasoning cannot reach a value containing the word `placeholder`: the
        runtime does not inject those, only a model does.

        MEASURED 2026-08-27 over every recorded call — 320 non-UUID context ids, 155 of which
        carry one of these tokens, dominated by `current_book_id_placeholder` at 144."""
        props = {"book_id": {"type": "string", "description": "the book's id (UUID)"}}
        for value in ("current_book_id_placeholder", "placeholder_book_id",
                      "YOUR_BOOK_ID_HERE", "[chapter_id_placeholder]"):
            assert _invented_supplier_ids({"book_id": value}, None, props) == ["book_id"], value

    def test_the_b1_EXEMPTION_STILL_HOLDS_beside_it(self):
        """The narrowing must not reopen the case that cost five red tests. `b1` carries no
        placeholder token, so the arm above cannot see it and the exemption is untouched."""
        props = {"book_id": {"type": "string", "description": "the book's id (UUID)"}}
        assert _invented_supplier_ids({"book_id": "b1"}, None, props) == []

    def test_what_this_STILL_DOES_NOT_REACH_is_asserted_not_assumed(self):
        """🔴 165 OF THE 320 ARE NOT COVERED and the biggest are named here, so nobody reads
        this widening as having closed D-FIXTURE-NAME-IS-THE-MOST-PLAUSIBLE-LOOKING-ID. A
        fixture name, a book TITLE and "all" carry no placeholder token; catching them needs
        the declaration-driven arm, which is the one that once deleted a runtime value."""
        props = {"project_id": {"type": "string", "description": "the project (a UUID)"},
                 "book_id": {"type": "string", "description": "the book's id (UUID)"}}
        for arg, value in (
            ("project_id", "LOOP-THROWAWAY-composition-derivative-edit-seeded-0-f5d5d3ed"),
            ("book_id", "all"),
            ("book_id", "book_list"),
            ("project_id", "Mị Đế"),
        ):
            assert _invented_supplier_ids({arg: value}, None, props) == [], (arg, value)

    def test_but_a_non_context_id_beside_it_still_is(self):
        """The exemption is per-argument, not per-call: a bad world_id is still caught when a
        context id is present in the same args."""
        props = {
            "book_id": {"type": "string", "description": "the book's id (UUID)"},
            "world_id": {"type": "string", "description": "the world (UUID)"},
        }
        assert _invented_supplier_ids(
            {"book_id": "b1", "world_id": "Ashfall"}, None, props) == ["world_id"]


class TestWhatCountsAsDeclared:
    def test_a_real_format_declaration_counts(self):
        """When a provider eventually adds `format: uuid`, that is the better declaration and
        must be honoured without needing the prose."""
        assert _declares_uuid({"x_id": {"type": "string", "format": "uuid"}}, "x_id") is True

    def test_the_description_counts_because_it_is_all_there_is(self):
        assert _declares_uuid(
            {"x_id": {"description": "the thing's id (UUID; you must own it)"}}, "x_id") is True

    def test_case_does_not_matter(self):
        assert _declares_uuid({"x_id": {"description": "a uuid"}}, "x_id") is True

    def test_silence_is_not_a_declaration(self):
        assert _declares_uuid({"x_id": {"description": "an opaque handle"}}, "x_id") is False
        assert _declares_uuid({}, "x_id") is False
        assert _declares_uuid(None, "x_id") is False


def test_the_call_site_passes_the_declaration():
    """CALL-SITE GUARD. The predicate is inert if the properties are never handed to it — and the
    default is None, which returns [] silently."""
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "services" / "stream_service.py").read_text(encoding="utf-8")
    i = src.index("_invented_ids = _invented_supplier_ids(")
    call = src[i:i + 320]
    assert "_tool_def_for_args" in call
    assert '.get("properties")' in call


# ── A FIXTURE'S OWN NAME IS THE MOST ID-SHAPED STRING IN THE TURN ────────────────────────
#
# 🔴 MEASURED TWICE. composition_list_derivatives was called with
# project_id="LOOP-THROWAWAY-composition-derivative-edit-seeded-0-f5d5d3ed" (2026-08-23), and
# earlier in this loop a LOOP-THROWAWAY name was passed as a world_id, with the model saying
# "I'm having trouble accessing the map (ID: LOOP-THROWAWAY-…)".
#
# No other arm can see it: there is no whitespace, it is not SCREAMING_SNAKE, and it is not a
# placeholder word. Only the DECLARED-UUID arm can, and it could not — composition's
# `project_id` was declared as "The Work's project_id." with no mention of a UUID, so
# `_declares_uuid` returned False. 48 of that module's 93 `*_id` declarations were in that
# state; 9 of the 10 distinct names are validated by `_uuid()` in the handler, so they ARE
# UUIDs and now say so. (`structure_template_id` is NOT `_uuid()`-validated and was left alone.)
#
# Renaming the fixtures is NOT the fix: the distinctive naming is deliberate and documented in
# `_purge_worlds`. The declaration is what has to be true.
_DERIV_PROPS = {
    "project_id": {"type": "string",
                   "description": "Any Work's project_id from the book. (a UUID)"},
}


def test_a_throwaway_fixture_name_is_dropped_when_the_arg_declares_a_uuid():
    """A NON-context id declaring a UUID drops the fixture name."""
    props = {"node_id": {"type": "string", "description": "The outline node's id. (a UUID)"}}
    args = {"node_id": "LOOP-THROWAWAY-composition-derivative-edit-seeded-0-f5d5d3ed"}
    assert _invented_supplier_ids(args, None, props) == ["node_id"]


def test_project_id_is_EXEMPT_even_when_it_declares_a_uuid_and_that_is_deliberate():
    """🔴 THE MEASURED CASE IS UNCATCHABLE BY THIS ARM, BY DESIGN — and my first draft of this
    test asserted the opposite before the suite corrected it.

    `project_id` is in `_RUNTIME_CONTEXT_IDS`. D-FJ-2 records why: a context id is injected by
    the runtime UPSTREAM of this point and is not guaranteed to be a UUID, so treating a
    non-UUID one as fabricated once DELETED A VALUE THE RUNTIME ITSELF HAD SUPPLIED and broke
    the dispatch. The exemption is worth more than this catch.

    So widening composition's declarations helps the SIX non-context names (arc_id, job_id,
    link_id, motif_id, node_id, rule_id) and cannot help book_id / chapter_id / project_id.
    The measured failure — a LOOP-THROWAWAY name sent as a project_id — needs a different
    mechanism, and pretending otherwise here would hide that.
    """
    args = {"project_id": "LOOP-THROWAWAY-composition-derivative-edit-seeded-0-f5d5d3ed"}
    assert _invented_supplier_ids(args, None, _DERIV_PROPS) == []


def test_the_same_name_survives_when_the_declaration_stays_silent():
    """This is exactly why the 41 declarations were widened — the arm is declaration-driven."""
    silent = {"node_id": {"type": "string", "description": "The outline node's id."}}
    args = {"node_id": "LOOP-THROWAWAY-composition-derivative-edit-seeded-0-f5d5d3ed"}
    assert _invented_supplier_ids(args, None, silent) == []


def test_a_real_uuid_is_untouched_by_the_widened_declaration():
    props = {"node_id": {"type": "string", "description": "The outline node's id. (a UUID)"}}
    assert _invented_supplier_ids({"node_id": "01a02cd6-01e1-73f2-8bbf-6d297e51213a"},
                                  None, props) == []
