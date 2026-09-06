"""CP-6.1 — closed-vocabulary resolution, and the replay that narrowed its own claim.

🔴 **MEASURED, ORGANIC: `glossary_propose_entities` fails in 51 sessions; 88 of its 109 failures
(81%) are `unknown kind`.** The largest remaining defect in the co-writer journey.

🔴 **AND THE FIRST HEADLINE FOR THIS ROW WAS WRONG, CAUGHT BY ITS OWN REPLAY — W2 AGAIN, MINE.**
Counting the 154 historical kind mentions against `system_kinds` said **54% are a standard kind one
adoption call away**, and I reported that number. Replayed against the **live** ontology of each
failing call's own book, it is **1 of 34 refusals (2.9%)**: the surviving books have since adopted
those standards, and the historical majority sits largely in books that no longer exist. Both
numbers are true of different populations; **only the live one describes what the mechanism will
meet.** The pilot-before-build rule caught it before a line was wired.

**What the replay does support:** 34 of 48 measurable calls (70.8%) are refused before the wire, and
the residual is dominated by near-misses of kinds the book ALREADY HAS (`place` ×10 where it has
`location`; `power_systems` where it has `power_system`) and by values that are not kinds at all
(`betrayal` ×8, `cost` ×5, `toll` ×3). Naming the book's actual set is what addresses those.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.agentruntime.vocabulary import (
    Pending, Vocabulary, VocabularyContractViolation, check_vocabulary, codes_from, decide,
    load_registry, refusal_message, values_at,
)

REGISTRY = (pathlib.Path(__file__).resolve().parents[3]
            / "contracts" / "agent-runtime-vocabularies.json")

BOOK_KINDS = {"ontology": {"kinds": [{"code": "character"}, {"code": "location"},
                                     {"code": "power_system"}]}}
STANDARDS = {"kinds": [{"code": "character"}, {"code": "location"}, {"code": "item"},
                       {"code": "terminology"}, {"code": "power_system"}]}


def vocab(**over) -> Vocabulary:
    base = dict(name="BookEntityKind", source_tool="glossary_book_ontology_read",
                source_path="ontology.kinds", value_field="code", scope_params=("book_id",),
                standards_tool="glossary_list_system_standards", standards_path="kinds",
                standards_field="code", adopt_tool="glossary_adopt_standards",
                create_tool="glossary_ontology_upsert")
    base.update(over)
    return Vocabulary(**base)


def pending(*kinds: str) -> Pending:
    return Pending(tool="glossary_propose_entities", param="items[].kind", vocabulary=vocab(),
                   sent=tuple(kinds), source_args={"book_id": "b1"})


class TestTheTwoBranchesAndThereIsNoThird:

    def test_A_VALUE_IN_THE_BOOKS_SET_PASSES(self):
        d = decide(pending("character"), BOOK_KINDS, STANDARDS)
        assert d.is_ok and d.unknown == ()

    def test_A_VALUE_OUTSIDE_IT_IS_REFUSED(self):
        d = decide(pending("cultivation_system"), BOOK_KINDS, STANDARDS)
        assert not d.is_ok
        assert d.unknown == ("cultivation_system",)
        assert d.outcome == "unknown_value"

    def test_THERE_IS_NO_FUZZY_SUBSTITUTION_ARM(self):
        """🔴 **THE PO DECISION, AND THE REASON IS ASYMMETRIC RISK.** `place` is the single largest
        unknown value in the live replay (×10) and the book has `location`. Rewriting it would
        raise the apparent success rate and write a WRONG KIND into canon silently — worse than the
        loud failure it replaces. 5.3-pilot drew the same line on four entities tied at 0.9."""
        d = decide(pending("place"), BOOK_KINDS, STANDARDS)
        assert not d.is_ok, "a near-miss must still refuse"
        assert "location" not in d.sent, "the sent value must never be rewritten"
        assert d.unknown == ("place",)

    def test_A_NORMALISED_NEAR_MISS_IS_SUGGESTED_NEVER_SUBSTITUTED(self):
        """`power_systems` for `power_system` is a plural the model can fix once told. The
        suggestion is prose; the argument is untouched."""
        d = decide(pending("power_systems"), BOOK_KINDS, STANDARDS)
        assert not d.is_ok
        assert d.did_you_mean == (("power_systems", "power_system"),)
        assert d.sent == ("power_systems",)

    def test_ONE_BAD_VALUE_REFUSES_THE_WHOLE_CALL(self):
        """The tool is a batch and its own summary already reports `created: 0` when items fail, so
        letting the good ones through would split one call into a silent partial write."""
        d = decide(pending("character", "cultivation_system"), BOOK_KINDS, STANDARDS)
        assert not d.is_ok and d.unknown == ("cultivation_system",)


class TestTheRefusalCarriesTheVALUESNotOnlyTheMechanism:

    def test_IT_NAMES_THE_BOOKS_ACTUAL_KINDS(self):
        """🔴 **THE ONE THING THE EXISTING MESSAGE DOES NOT DO.** Today the model is told the
        category does not exist and is named the repair TOOLS — never the set it may choose from,
        which is the only part it can act on without another round trip."""
        msg = refusal_message([decide(pending("place"), BOOK_KINDS, STANDARDS)])
        assert "This book has:" in msg
        for k in ("character", "location", "power_system"):
            assert f"'{k}'" in msg

    def test_AN_ADOPTABLE_STANDARD_IS_NAMED_WITH_ITS_ONE_CALL(self):
        d = decide(pending("item"), BOOK_KINDS, STANDARDS)
        msg = refusal_message([d])
        assert d.adoptable == ("item",)
        assert "glossary_adopt_standards" in msg and "STANDARD kind" in msg

    def test_THE_CREATE_PATH_IS_NOT_THE_LEGACY_TOOL(self):
        """🔴 **THE EXISTING MESSAGE ROUTES THE MODEL TO A DEPRECATED TOOL.** It names
        `glossary_propose_kinds`, which carries `visibility: legacy` in its own `_meta` (and no
        `superseded_by`). The live path is `glossary_ontology_upsert`."""
        msg = refusal_message([decide(pending("cultivation_system"), BOOK_KINDS, STANDARDS)])
        assert "glossary_ontology_upsert" in msg
        assert "glossary_propose_kinds" not in msg

        # 🔴 ...AND THE SHIPPED CONTRACT, WHICH IS WHAT THIS TEST'S NAME CLAIMS. Everything
        # above runs on `vocab()`, an inline fixture that hardcodes the create tool — so it
        # asserts the fixture agrees with itself and says nothing about the file the runtime
        # loads. The falsification harness measured it: pointing
        # `contracts/agent-runtime-vocabularies.json` back at `glossary_propose_kinds`, the
        # deprecated tool this test exists to keep out, left the whole test GREEN.
        #
        # `glossary_propose_kinds` carries `visibility: legacy` in its own `_meta` and has no
        # `superseded_by`, so a model routed there is routed at nothing.
        shipped = (pathlib.Path(__file__).resolve().parents[3]
                   / "contracts" / "agent-runtime-vocabularies.json").read_text(encoding="utf-8")
        assert '"create_tool": "glossary_propose_kinds"' not in shipped, (
            "the shipped vocabulary routes creation at the LEGACY tool")
        assert '"create_tool": "glossary_ontology_upsert"' in shipped, (
            "the shipped vocabulary no longer names the live create path")


class TestTheSourceMustBeSafeToDispatchUnasked:

    def test_A_NON_READ_SOURCE_IS_REFUSED_AT_REGISTRATION(self):
        """CP-5.3's safety property, restated: enumerating a vocabulary dispatches a tool the user
        never asked for, so a `W` source would perform an unrequested write on the way to
        validating an argument."""
        with pytest.raises(VocabularyContractViolation, match="lane='write'"):
            check_vocabulary(vocab(), lambda _t: "write")

    def test_AN_UNKNOWN_LANE_FAILS_CLOSED(self):
        with pytest.raises(VocabularyContractViolation, match="cannot determine"):
            check_vocabulary(vocab(), lambda _t: None)

    def test_THE_STANDARDS_SOURCE_IS_CHECKED_TOO(self):
        """It is dispatched on exactly the same terms, so exempting it would leave half the
        mechanism unguarded."""
        with pytest.raises(VocabularyContractViolation, match="standards_tool"):
            check_vocabulary(vocab(), lambda t: "read" if t == "glossary_book_ontology_read"
                             else "write")

    @pytest.mark.parametrize("field", ["source_tool", "source_path", "value_field"])
    def test_A_ROW_MISSING_ITS_SOURCE_TRIPLE_IS_REFUSED(self, field):
        """🔴 **NAMED BY THE CENSUS AS A REFUSAL NOTHING CHECKED**, filed the run after this
        module landed. The lane checks below it were guarded and this one — the check that the
        row says WHERE the values come from at all — was not, so removing it reddened nothing.

        An unguarded emptiness check is the worst one to lose: a row with a blank `source_path`
        does not raise later, it enumerates to an EMPTY legal set, and an empty set refuses every
        value the model sends. The failure would arrive as "unknown kind" on a correct kind."""
        with pytest.raises(VocabularyContractViolation, match=f"declares no {field}"):
            check_vocabulary(vocab(**{field: ""}), lambda _t: "read")


class TestTheRegistryRefusesTheWholeDocumentRatherThanDroppingARow:

    def test_A_BINDING_TO_AN_UNDECLARED_VOCABULARY_IS_REFUSED(self):
        """F-50's shape: a silently dropped row leaves its binding in place, naming nothing."""
        doc = {"vocabularies": {}, "bindings": {"t": {"p": "Nope"}}}
        with pytest.raises(VocabularyContractViolation, match="not declared"):
            load_registry(doc, lambda _t: "read")

    def test_A_MALFORMED_BINDING_BLOCK_IS_REFUSED_NOT_SKIPPED(self):
        """🔴 **THE CENSUS'S SECOND UNCHECKED REFUSAL HERE.** `{"t": "BookEntityKind"}` — a
        binding written as a bare string instead of a `{path: vocabulary}` map — is the shape a
        hand-edited registry actually takes. Unguarded, removing this raise makes the whole block
        iterate over the STRING's characters and bind nothing, so every call the block was meant
        to protect sails through unvalidated with the registry looking fine."""
        doc = {"vocabularies": {}, "bindings": {"glossary_propose_entities": "BookEntityKind"}}
        with pytest.raises(VocabularyContractViolation, match="binding block is not an object"):
            load_registry(doc, lambda _t: "read")

    def test_A_MALFORMED_VOCABULARY_ROW_IS_REFUSED_NOT_SKIPPED(self):
        doc = {"vocabularies": {"BookEntityKind": "not-an-object"}, "bindings": {}}
        with pytest.raises(VocabularyContractViolation, match="is not an object"):
            load_registry(doc, lambda _t: "read")

    def test_THE_COMMITTED_REGISTRY_LOADS_AND_BINDS_THE_MEASURED_PATH(self):
        doc = json.loads(REGISTRY.read_text(encoding="utf-8"))
        vocabs, bindings = load_registry(doc, lambda _t: "read")
        assert "BookEntityKind" in vocabs
        assert bindings[("glossary_propose_entities", "items[].kind")] == "BookEntityKind"


class TestTheArgumentReaderHasNoExpressionSyntax:

    def test_IT_READS_ONE_LIST_HOP(self):
        args = {"items": [{"kind": "character"}, {"kind": "place"}, {"name": "no kind"}]}
        assert values_at(args, "items[].kind") == ["character", "place"]

    def test_A_MISSING_OR_WRONG_SHAPE_YIELDS_NOTHING_RATHER_THAN_RAISING(self):
        assert values_at({}, "items[].kind") == []
        assert values_at({"items": "not a list"}, "items[].kind") == []
        assert values_at({"items": [None, 7]}, "items[].kind") == []
        # 🔴 A DICT, not just a string. The three rows above already feed a non-list, and the
        # falsification harness measured that they cannot see the mutation that matters:
        # replacing `if not isinstance(seq, list): return []` with `seq = [seq]` — a reader that
        # WRAPS a wrong shape instead of refusing it — leaves all three green, because wrapping
        # `"not a list"` still yields nothing when the walk asks it for `.kind`.
        #
        # A mapping is the shape where wrapping changes the answer: `[{"kind": "x"}]` yields
        # `["x"]`, so a single value silently becomes a one-element vocabulary the caller never
        # sent. That is the difference between "yields nothing" and "yields something wrong",
        # which is the whole subject of this test's name.
        assert values_at({"items": {"kind": "x"}}, "items[].kind") == []

    def test_CODES_COME_FROM_THE_DECLARED_FIELD(self):
        assert codes_from(BOOK_KINDS, "ontology.kinds", "code") == (
            "character", "location", "power_system")
        assert codes_from({}, "ontology.kinds", "code") == ()


class TestTheWiringAtTheChokepoint:

    def _src(self) -> str:
        return (pathlib.Path(__file__).resolve().parents[1] / "app" / "services"
                / "stream_service.py").read_text(encoding="utf-8")

    def test_IT_SITS_BEFORE_THE_ONE_REAL_DISPATCH(self):
        """Placement is the mechanism — V-METRIC round 3 was a placement bug, not a null."""
        s = self._src()
        assert s.index("CP-6.1 · CLOSED-VOCABULARY RESOLUTION") < s.index(
            "envelope = await knowledge_client.mcp_execute_tool(")

    def test_IT_SITS_AFTER_IDENTIFIER_RESOLUTION(self):
        """A resolved id may itself be what scopes the vocabulary read, so resolution runs first —
        the same ordering argument that put resolution after the plan."""
        s = self._src()
        assert s.index("CP-5.3 · IDENTIFIER RESOLUTION") < s.index(
            "CP-6.1 · CLOSED-VOCABULARY RESOLUTION")

    def test_A_FAILED_SOURCE_READ_DOES_NOT_BLOCK_THE_CALL(self):
        """🔴 **FAIL OPEN HERE, AGAINST THE USUAL DIRECTION AND FOR A STATED REASON.** If the
        ontology read fails, the runtime does not know the vocabulary — refusing on that state would
        turn one degraded READ into a blocked WRITE, and the call would fail in a new way nobody can
        see. Unchecked, it fails exactly as it does today."""
        s = self._src()
        assert ("# Failing CLOSED here would turn one degraded read into a blocked write."
                in s or "Failing CLOSED here would turn one degraded read into a blocked write"
                in s)

    def test_THE_ENUMERATION_IS_RECORDED_AS_A_REAL_EXECUTION(self):
        """CP-5.3's gate finding applied without having to be caught twice: the read genuinely runs,
        so it is stamped and kept separable by `vocabulary_for`."""
        s = self._src()
        assert '"vocabulary_for"' in s
        assert "instrument.SOURCE_TOOL" in s

    def test_THE_REFUSAL_IS_TYPED_REFUSED_NOT_FAILED(self):
        s = self._src()
        assert 'instrument.stamp_refused(_vfail, "unknown_vocabulary_value")' in s
