"""The id-repair sentence must point at a tool that EXISTS, or point at nothing.

`_name_like_dropped_ids` closed with "look it up with the tool named above". That phrase was
written for composition_motif_link_edit, whose description really does say "search motifs by name
with composition_motif_search and pass the id it returns". For a tool whose description names
nothing, the model was told to use a tool that was never named.

🔴 AND IT ACTS ON IT. Measured in c-arcapply, K=5: the model passed arc_id='The Varisuni Ascent'
to composition_arc_template_get, received this repair, then guessed composition_arc_suggest — it
never called composition_arc_template_list, the real supplier, which was on no pass of the wire.
Its closing message was "I still can't find an arc template named 'The Varisuni Ascent'", about a
template its own run had just created.

RE-DERIVED 2026-08-26 over the live catalogue, because the row's number predates the emitter map:
of 131 tools requiring a non-ambient `*_id`, 59 name a supplier in prose, 52 now declare an
EMITTER, 82 have SOME referent, and 49 (37%) have none. The row measured 45 of 86 (52%) before
argument_emitters was populated.

THE REMEDY IS THE ROW'S OWN, IN ITS ORDER: name the supplier — the platform holds the catalogue at
the moment it writes this sentence — and failing that DROP the clause, because "an instruction
with no referent is worse than no instruction, because the model spends its turn acting on it."
"""
from __future__ import annotations

import pathlib

from app.services import stream_service as ss

SRC = pathlib.Path(ss.__file__).read_text(encoding="utf-8", errors="replace")
DROPPED = {"arc_id": "The Varisuni Ascent"}


class TestItNamesTheEmitterWhenOneIsDeclared:
    def test_the_emitter_name_appears_VERBATIM(self):
        """Verbatim, because naming it is also what ARMS it: the arming path keys off catalogue
        names in this very text, so a paraphrase puts no supplier on the wire."""
        msg = ss._name_like_dropped_ids(DROPPED, emitter="composition_arc_template_list")
        assert "composition_arc_template_list" in msg
        assert "the tool named above" not in msg
        assert "The Varisuni Ascent" in msg  # the value is still the query to search with

    def test_it_still_says_this_is_NOT_the_missing_case(self):
        msg = ss._name_like_dropped_ids(DROPPED, emitter="composition_arc_template_list")
        assert "NAME" in msg and "not missing" in msg.lower()


class TestItKeepsTheOldPhrasingWhenSomethingElseNamedATool:
    def test_referent_exists_is_the_unchanged_path(self):
        msg = ss._name_like_dropped_ids(DROPPED, referent_exists=True)
        assert "the tool named above" in msg

    def test_the_default_is_the_old_behaviour(self):
        """Callers not yet taught to resolve a referent must be unchanged."""
        assert ss._name_like_dropped_ids(DROPPED) == ss._name_like_dropped_ids(
            DROPPED, referent_exists=True)


class TestItDropsTheClauseWhenNothingNamedATool:
    def test_no_dangling_referent(self):
        msg = ss._name_like_dropped_ids(DROPPED, referent_exists=False)
        assert "the tool named above" not in msg, (
            "an instruction with no referent is worse than no instruction — the model spends its "
            "turn acting on it")

    def test_it_still_reports_the_real_problem(self):
        msg = ss._name_like_dropped_ids(DROPPED, referent_exists=False)
        assert "The Varisuni Ascent" in msg and "NAME" in msg

    def test_it_does_not_INVENT_a_remedy(self):
        """Naming a plausible-sounding tool would be the fabrication this whole class is about."""
        msg = ss._name_like_dropped_ids(DROPPED, referent_exists=False)
        assert "search" not in msg.split("No tool on this surface")[-1].lower()
        assert "do not guess" in msg.lower()

    def test_an_emitter_WINS_over_the_dropped_clause(self):
        msg = ss._name_like_dropped_ids(DROPPED, emitter="x_list", referent_exists=False)
        assert "x_list" in msg and "No tool on this surface" not in msg


class TestItIsWiredInAtTheCallSite:
    """A helper nobody passes the new arguments to is the old behaviour with extra parameters."""

    def test_the_call_site_resolves_the_EMITTER(self):
        assert "_nl_emitter = next(" in SRC
        assert "declared_emitter as _de" in SRC

    def test_the_call_site_resolves_whether_a_referent_EXISTS(self):
        assert "_nl_referent = bool(_tools_named_in_refusal(" in SRC

    def test_both_are_PASSED(self):
        assert ("_named = _name_like_dropped_ids(\n"
                "                        _invented_vals, emitter=_nl_emitter, "
                "referent_exists=_nl_referent)") in SRC

    def test_the_lookup_cannot_take_the_turn_down(self):
        """A contract lookup that raises must not kill a turn that was otherwise fine."""
        seg = SRC.split("_nl_emitter = \"\"", 1)[1][:900]
        assert "except Exception" in seg and '_nl_emitter = ""' in seg
