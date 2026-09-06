"""A per-op refusal names ARGUMENTS and no MOVE — so the turn has nowhere to go.

18 catalogue tools are flat-superset op-dispatch: they declare only `op` as required, because one
schema serves several ops. `_missing_required_names` therefore finds nothing missing, the call
DISPATCHES, and the server refuses with the per-op requirement it knew all along:

    op=create requires from_motif_id, to_motif_id, and kind

Every repair path above the dispatch is blind to that. No supplier is named, and
`_tools_named_in_refusal` arms nothing because the sentence contains no tool name. The model is
told what it is missing and given no way to obtain any of it.

MEASURED 2026-08-25. Across every service's MCP layer, 45 literal refusal strings are of this
shape. In the recorded corpus, 52 refusals name arguments this way; 27 also happen to name a tool
(the arming already fires for those) and **25 name none at all** — dead.

WHAT THIS FILE PINS, and why each half is here:
  * the PARSER, including the three-item list that the first regex silently truncated;
  * the STRUCTURAL precision guard — a token survives only if the tool declares it;
  * both ARMS of the guidance: name the emitter, or say to ask the author;
  * that it is WIRED IN at the dispatch site, ABOVE the arming call, because a helper with no
    call site is a mechanism that has never run.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from app.services import stream_service as ss

SRC = pathlib.Path(ss.__file__).read_text(encoding="utf-8", errors="replace")

MOTIF_LINK_PROPS = {
    "op": {}, "from_motif_id": {}, "to_motif_id": {}, "kind": {}, "book_id": {}, "link_id": {},
}


class TestTheParserReadsTheWholeList:
    def test_a_three_item_list_keeps_its_LAST_argument(self):
        """The regex this replaced dropped `kind`: a repeating `,\\s*item` group consumed ", and"
        as if `and` were an item, so the optional and-clause never matched. It parsed, it looked
        right, and it under-counted exactly the argument a model most needs named."""
        got = ss._args_named_in_refusal(
            "op=create requires from_motif_id, to_motif_id, and kind", MOTIF_LINK_PROPS)
        assert got == ["from_motif_id", "to_motif_id", "kind"]

    def test_a_two_item_and_list(self):
        assert ss._args_named_in_refusal(
            "op=create requires code and name", {"code": {}, "name": {}}) == ["code", "name"]

    def test_a_single_argument(self):
        assert ss._args_named_in_refusal(
            "op=delete requires link_id", MOTIF_LINK_PROPS) == ["link_id"]

    def test_an_f_string_op_still_parses(self):
        """Several servers build the string with the op interpolated."""
        assert ss._args_named_in_refusal(
            "op=archive requires motif_id", {"motif_id": {}}) == ["motif_id"]


class TestTheSchemaIsThePrecisionGuard:
    def test_a_word_the_tool_does_not_declare_is_dropped(self):
        """Prose is full of nouns. Only the schema decides what an argument is."""
        assert ss._args_named_in_refusal(
            "requires a valid dictionary", {"overridden_fields": {}}) == []

    def test_the_connective_is_never_an_argument_even_if_declared_nowhere(self):
        got = ss._args_named_in_refusal(
            "op=bind requires project_id, node_id, and motif_id",
            {"project_id": {}, "node_id": {}, "motif_id": {}})
        assert "and" not in got and len(got) == 3

    def test_no_properties_means_no_extraction(self):
        """An unknown tool must never have arguments invented for it."""
        assert ss._args_named_in_refusal("op=create requires anything", {}) == []


class TestTheGuidanceNamesAMove:
    def test_a_declared_emitter_is_NAMED_so_the_arming_can_see_it(self):
        reg = {"argument_emitters": {"t": {"motif_id": "composition_motif_search"}}}
        out = ss._where_each_argument_comes_from("t", ["motif_id"], reg)
        assert "composition_motif_search" in out, (
            "the emitter's NAME must appear verbatim — the caller appends this to the refusal "
            "text and `_tools_named_in_refusal` keys off catalogue names in it, so a paraphrase "
            "arms nothing")

    def test_two_arguments_from_ONE_emitter_are_named_together(self):
        reg = {"argument_emitters": {"t": {"a_id": "lister", "b_id": "lister"}}}
        out = ss._where_each_argument_comes_from("t", ["a_id", "b_id"], reg)
        assert out.count("lister") == 1 and "a_id and b_id" in out

    def test_an_argument_with_NO_emitter_says_ASK_THE_AUTHOR(self):
        """`budget_usd` and `pause_after_each_unit` are DECISIONS — how much money to spend, and
        whether to pause between units. No tool can supply them, and without this the turn is told
        not to guess and given nowhere to go."""
        out = ss._where_each_argument_comes_from(
            "composition_authoring_run_manage",
            ["budget_usd", "pause_after_each_unit"], {"argument_emitters": {}})
        assert "ASK THE AUTHOR" in out
        assert "budget_usd and pause_after_each_unit" in out
        assert "Do NOT guess" in out

    def test_the_two_arms_can_appear_together(self):
        reg = {"argument_emitters": {"t": {"run_id": "plan_propose_spec"}}}
        out = ss._where_each_argument_comes_from("t", ["run_id", "budget_usd"], reg)
        assert "plan_propose_spec" in out and "ASK THE AUTHOR" in out

    def test_nothing_to_say_returns_EMPTY_not_a_stub_sentence(self):
        assert ss._where_each_argument_comes_from("t", [], {"argument_emitters": {}}) == ""

    def test_a_broken_registry_never_takes_the_turn_down(self):
        out = ss._where_each_argument_comes_from("t", ["x_id"], None)
        assert "ASK THE AUTHOR" in out


class TestItDoesNotOverAsk:
    """The first version told the model to ASK for things it could already answer.

    Caught by running the helper against the real refusal strings in the deployed container,
    BEFORE the live run — which is the only reason it is not in the measurement.
    """

    ENUM_PROPS = {"kind": {"anyOf": [
        {"enum": ["composed_of", "precedes", "variant_of"], "type": "string"},
        {"type": "null"}]}}

    def test_an_enum_is_a_CHOICE_not_a_question(self):
        """`kind` on composition_motif_link_edit is composed_of | precedes | variant_of, and the
        request that triggers it says 'mark A as coming BEFORE B'. Asking the author to spell
        that out is worse than the refusal it replaced."""
        out = ss._where_each_argument_comes_from(
            "composition_motif_link_edit", ["kind"], {"argument_emitters": {}}, self.ENUM_PROPS)
        assert "ASK THE AUTHOR" not in out
        assert "composed_of | precedes | variant_of" in out

    def test_the_optional_enum_SHAPE_is_read(self):
        """Pydantic emits an optional enum as anyOf[{enum}, {null}], which is how EVERY enum on a
        flat-superset tool is declared — reading only a top-level `enum` would find none."""
        assert ss._enum_values(self.ENUM_PROPS["kind"]) == [
            "composed_of", "precedes", "variant_of"]
        assert ss._enum_values({"enum": ["a", "b"]}) == ["a", "b"]
        assert ss._enum_values({"type": "string"}) == []
        assert ss._enum_values(None) == []

    def test_a_value_the_author_already_said_is_taken_from_the_REQUEST_first(self):
        """"op=create requires code and name" is answered by the author's own sentence on most
        turns. A flat 'ask' would send the model back to a user who has already said it."""
        out = ss._where_each_argument_comes_from(
            "composition_motif_edit", ["name"], {"argument_emitters": {}}, {"name": {}})
        assert "from the author's request" in out
        assert "ASK THE AUTHOR" in out  # still offered, as the fallback

    def test_all_three_arms_can_appear_at_once(self):
        reg = {"argument_emitters": {"t": {"run_id": "plan_propose_spec"}}}
        props = {"kind": self.ENUM_PROPS["kind"], "run_id": {}, "budget_usd": {}}
        out = ss._where_each_argument_comes_from(
            "t", ["run_id", "kind", "budget_usd"], reg, props)
        assert "plan_propose_spec" in out
        assert "composed_of | precedes | variant_of" in out
        assert "budget_usd" in out and "ASK THE AUTHOR" in out

    def test_the_call_site_passes_the_PROPERTIES_through(self):
        """Without props the enum arm is dead — it would silently fall back to asking."""
        assert ("_po_help = _where_each_argument_comes_from(\n"
                "                            c[\"name\"], _po_args, _tool_contract_registry(), "
                "_po_props)") in SRC


class TestItIsActuallyWIREDIN:
    """A helper nobody calls is a mechanism that has never run — this repo has shipped one."""

    def test_the_dispatch_site_calls_the_parser(self):
        assert "_po_args = _args_named_in_refusal(_refusal_text, _po_props)" in SRC

    def test_it_appends_to_the_REFUSAL_TEXT_so_the_existing_arming_sees_the_emitter(self):
        assert '_refusal_text = f"{_refusal_text} {_po_help}"' in SRC, (
            "the guidance must go into `_refusal_text`, not only into the model-visible content: "
            "arming reads that variable, and a sentence the arming cannot see puts no supplier "
            "on the wire")

    def test_it_runs_BEFORE_the_arming_call(self):
        """Order is the whole mechanism. Appended after, the emitter name would never be armed."""
        append_at = SRC.index('_refusal_text = f"{_refusal_text} {_po_help}"')
        arm_at = SRC.index("if _refusal_text and discovery:")
        assert append_at < arm_at, "the append must precede the arming branch"

    def test_a_refusal_that_ALREADY_names_a_tool_is_left_alone(self):
        """composition_arc_template_edit already says 'Call composition_arc_template_list to get
        the id'. A second sentence beside a correct one is noise, not help."""
        assert "if _po_args and not _po_already:" in SRC
        assert "_po_already = any(" in SRC

    def test_the_model_also_SEES_it(self):
        assert '_tool_content = (_tool_content or "") + "\\n\\n[SYSTEM] " + _po_help' in SRC


class TestTheRealRefusalStringsStillParse:
    """The exact strings the services raise today. If a service rewords one, this notices."""

    @pytest.mark.parametrize(("text", "props", "expected"), [
        ("op=create requires plan_run_id, budget_usd, and pause_after_each_unit",
         {"plan_run_id": {}, "budget_usd": {}, "pause_after_each_unit": {}},
         ["plan_run_id", "budget_usd", "pause_after_each_unit"]),
        ("op=patch requires motif_id and expected_version",
         {"motif_id": {}, "expected_version": {}}, ["motif_id", "expected_version"]),
        ("op=update requires node_id and expected_version",
         {"node_id": {}, "expected_version": {}}, ["node_id", "expected_version"]),
        ("op=assign_chapters requires book_id and chapter_node_ids",
         {"book_id": {}, "chapter_node_ids": {}}, ["book_id", "chapter_node_ids"]),
    ])
    def test_it_extracts_every_argument(self, text, props, expected):
        assert ss._args_named_in_refusal(text, props) == expected

    def test_the_service_strings_have_not_drifted(self):
        """Counted from source 2026-08-25: 45 per-op `requires` strings. A large drop means a
        service reworded them and this parser is quietly reading fewer of them."""
        root = pathlib.Path(ss.__file__).resolve().parents[4]
        n = 0
        for p in root.glob("services/*/app/mcp/*.py"):
            body = p.read_text(encoding="utf-8", errors="replace")
            n += len(re.findall(r'raise ValueError\(f?"[^"]*\bop=[^"]*requires[^"]*"\)', body))
        if n == 0:
            pytest.skip("service sources not in this checkout")
        assert n >= 30, (
            f"only {n} per-op refusal strings found (45 at the time of writing) — if the servers "
            "reworded them, re-measure the parser against the new shape before trusting it")
