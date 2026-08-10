"""CP-5.1 / 5.2 — the tool contract, and rung 2 refusing to promote an incomplete one.

🔴 **§7 is the gate this checkpoint owes ITSELF, and it is what most of this file is:** *every
member must have a **subject** and a test that goes red if the member is dropped.* **"The subject
does not exist yet" is how C-3…C-17 became permanent** — deferred for a real reason, never
revisited, and no gate could notice, because a gate over a clause with no subject is exactly the
vacuity this board has a standard about.

So there is no test here that merely asserts a member is listed. Each one asserts a **consequence**:
drop the member from the registry and a promotion that should be refused starts succeeding.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.agentruntime.contract import Declaration, UntrustedRow
from app.agentruntime.promotion import check_tool_contract, coverage, promote
from app.agentruntime.toolcontract import (
    TOOL_CONTRACT_VERSION, TOOL_CONTRACTS, ToolContract, ToolContractViolation,
    has_untyped_property, properties_of, tool_contract_for,
)

BASELINE = (pathlib.Path(__file__).resolve().parents[3]
            / "contracts" / "agent-runtime-baseline" / "tools-list.snapshot.json")


def catalogue() -> list[dict]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))["tools"]


def tool(name: str) -> dict:
    for t in catalogue():
        fn = t.get("function", t)
        if fn.get("name") == name:
            return t
    raise AssertionError(f"{name} is not in the frozen catalogue")


def _declaring(td: dict, members: dict) -> dict:
    """The same tool definition, carrying a `_meta.contract` block."""
    out = json.loads(json.dumps(td))
    fn = out.get("function", out)
    fn.setdefault("_meta", {})["contract"] = members
    return out


def _satisfying(td: dict) -> dict:
    """A definition declaring every member that applies to it, each with something to say."""
    applicable = check_tool_contract(td).applicable
    return _declaring(td, {m: {"declared": "by this test"} for m in applicable})


class TestEveryMemberHasASubjectThatEXISTS:
    """The C-3…C-17 failure, gated. A member whose trigger selects nothing is a clause with no
    subject, and it is the state this whole checkpoint exists because of."""

    def test_EVERY_MEMBER_APPLIES_TO_AT_LEAST_ONE_REAL_TOOL(self):
        cat = catalogue()
        applies = coverage(cat)["member_applies_to"]
        contract = tool_contract_for(TOOL_CONTRACT_VERSION)
        for m in contract.members:
            assert applies.get(m.name, 0) > 0, (
                f"member {m.name!r} is selected by NO tool in the catalogue of {len(cat)}. That is "
                f"a clause with no subject — the exact shape that made C-3…C-17 permanent. Either "
                f"its trigger is wrong or the member does not belong (§7)."
            )

    def test_EVERY_MEMBER_NAMES_ITS_SUBJECT_AND_ITS_EVIDENCE(self):
        for m in tool_contract_for(TOOL_CONTRACT_VERSION).members:
            assert m.subject.strip(), f"{m.name} declares no subject"
            assert m.evidence.strip(), f"{m.name} declares no evidence"

    def test_A_CONDITIONAL_MEMBER_NAMES_THE_TRIGGER_THAT_MAKES_IT_APPLY(self):
        """Otherwise a report can say a member applied but not WHY, and a producer being refused
        cannot tell which property of its own tool pulled the member in."""
        for m in tool_contract_for(TOOL_CONTRACT_VERSION).members:
            if not m.is_core:
                assert m.trigger_name.strip(), f"conditional member {m.name} names no trigger"

    def test_THE_CATALOGUE_HAS_NO_UNTYPED_PROPERTY_SO_5_3b_HAS_NO_SUBJECT(self):
        """🔴 The spec demotes `typed inputs` to a member covering *"the 120 properties with no
        `type` at all"*. **There are none**, and the 120 is a measurement artifact: `.get("type")`
        returns `None` for `anyOf: [{"type":"string"},{"type":"null"}]` — Pydantic's `Optional[str]`
        — so a correctly-typed union counts as untyped.

        This test is what keeps the member's ABSENCE honest. If a provider ever ships a genuinely
        unconstrained property, the subject appears and this goes red, which is the signal to add
        the member — rather than a clause sitting in the registry waiting for a subject nobody
        re-checks.
        """
        offenders = [t.get("function", t).get("name") for t in catalogue()
                     if has_untyped_property(t)]
        assert offenders == [], (
            f"{len(offenders)} tool(s) now carry a property that constrains its value in no way: "
            f"{offenders[:10]}. 5.3b's subject now EXISTS — add the member."
        )
        assert sum(len(properties_of(t)) for t in catalogue()) > 0, (
            "the predicate above is vacuous if no tool has properties at all"
        )


class TestCoreVsConditionalIsDECLAREDRatherThanBuriedInAValidator:

    #: The members CP-5 §1 marks `core` — required of every tool, unconditionally. Pinned as a
    #: SET rather than derived from the registry, because the registry is the thing under test.
    CORE = {"argument_supplier", "repeat_semantics", "error_contract", "output_contract"}

    def test_A_CORE_MEMBER_APPLIES_TO_EVERY_TOOL(self):
        """🔴 **THE FIRST VERSION OF THIS GUARD COULD NOT FAIL, AND THE FALSIFICATION RUNNER SAID
        SO.** It looped `if m.is_core` and asserted the member applied everywhere — so giving a
        core member a trigger did not break it, it **removed the member from the loop**. Attaching
        `trigger=is_batch` to `error_contract` (312 of 315 tools stop having to declare a message
        on failure) left the guard GREEN: *"the guard requires nothing"*.

        The fix is to pin the core SET. A member silently demoted to conditional is now the
        failure, which is what the guard was always meant to say.
        """
        cat = catalogue()
        contract = tool_contract_for(TOOL_CONTRACT_VERSION)
        actual_core = {m.name for m in contract.members if m.is_core}
        assert actual_core == self.CORE, (
            f"the core member set changed: {sorted(actual_core)} vs {sorted(self.CORE)}. A member "
            f"moving core -> conditional stops applying to almost every tool, which is a release "
            f"decision, not a refactor"
        )
        applies = coverage(cat)["member_applies_to"]
        for name in sorted(self.CORE):
            assert applies.get(name) == len(cat), (
                f"{name} is core but applies to {applies.get(name)} of {len(cat)}"
            )

    def test_A_CONDITIONAL_MEMBER_IS_REQUIRED_ONLY_WHERE_ITS_TRIGGER_FIRES(self):
        """5.1's exit criterion, both halves in one test."""
        paged = tool("book_list")                     # has limit/offset
        assert "result_completeness" in check_tool_contract(paged).applicable

        stripped = json.loads(json.dumps(paged))
        fn = stripped.get("function", stripped)
        for k in ("limit", "offset", "cursor", "page"):
            fn["inputSchema"]["properties"].pop(k, None)
        assert "result_completeness" not in check_tool_contract(stripped).applicable, (
            "a tool that cannot truncate must not be required to declare completeness — requiring "
            "every member of every tool is what made v1's migration impossible"
        )

    def test_THE_REPORT_EXPLAINS_WHY_EACH_MEMBER_APPLIED(self):
        because = dict(check_tool_contract(tool("book_list")).because)
        assert because["argument_supplier"].startswith("core")
        assert "truncated" in because["result_completeness"]


class TestRung2RefusesToPromoteAnIncompleteContract:
    """5.2's exit: strip one core member ⇒ promotion refuses ⇒ the tool does not serve."""

    def _draft(self, tool_id: str) -> Declaration:
        return Declaration(id=tool_id, kind="tool", source_path="services/book-service/",
                           lifecycle="draft")

    def test_A_TOOL_DECLARING_NO_CONTRACT_CANNOT_BE_PROMOTED(self):
        """The state of the entire catalogue today, and the reason rung 2 needs no other team: an
        unmigrated tool registers `draft` and simply never reaches the wire."""
        with pytest.raises(ToolContractViolation) as exc:
            promote(self._draft("book_list"), tool("book_list"))
        assert "book_list" in str(exc.value)

    def test_A_COMPLETE_CONTRACT_PROMOTES_AND_THE_RESULT_IS_ADMITTED(self):
        promoted = promote(self._draft("book_list"), _satisfying(tool("book_list")))
        assert promoted.lifecycle == "admitted"
        assert promoted.id == "book_list"

    @pytest.mark.parametrize("victim", ["argument_supplier", "repeat_semantics",
                                        "error_contract", "output_contract"])
    def test_STRIPPING_ANY_ONE_CORE_MEMBER_REFUSES_THE_PROMOTION(self, victim):
        """🔴 **The injection §7 asks for, one member at a time.** A single test that strips
        everything would pass even if only one member were ever checked."""
        td = _satisfying(tool("book_list"))
        del td.get("function", td)["_meta"]["contract"][victim]
        with pytest.raises(ToolContractViolation) as exc:
            promote(self._draft("book_list"), td)
        assert victim in str(exc.value), "the refusal must name the member that is missing (C-12)"

    def test_STRIPPING_A_CONDITIONAL_MEMBER_THE_TOOL_TRIGGERS_ALSO_REFUSES(self):
        td = _satisfying(tool("book_list"))
        del td.get("function", td)["_meta"]["contract"]["result_completeness"]
        with pytest.raises(ToolContractViolation, match="result_completeness"):
            promote(self._draft("book_list"), td)

    def test_AN_EMPTY_MEMBER_IS_NOT_A_DECLARATION(self):
        """`{}` and `null` would both pass a key-presence check while stating nothing — the
        *documented in a docstring* failure this checkpoint exists to end."""
        for empty in ({}, None, [], "", False):
            td = _satisfying(tool("book_list"))
            td.get("function", td)["_meta"]["contract"]["error_contract"] = empty
            with pytest.raises(ToolContractViolation, match="error_contract"):
                promote(self._draft("book_list"), td)

    def test_AN_UNDERSCORE_KEY_IS_AN_ANNOTATION_NOT_A_MEMBER(self):
        """🔴 Rung 2 refused `_why` on the first real contract authored for `glossary_search`, and
        it was right to ask. A contract that cannot carry its own reasoning gets that reasoning
        kept somewhere else, and the declaration and the argument for it drift apart. The
        convention is deliberately narrow — see the guard below, which still refuses a typo."""
        td = _satisfying(tool("book_list"))
        td.get("function", td)["_meta"]["contract"]["_why"] = "the rationale, for a human"
        assert promote(self._draft("book_list"), td).lifecycle == "admitted"

    def test_AN_UNKNOWN_MEMBER_IS_REFUSED_RATHER_THAN_IGNORED(self):
        """A typo that silently satisfies nothing is worse than a rejection: the producer believes
        the member is declared."""
        td = _satisfying(tool("book_list"))
        td.get("function", td)["_meta"]["contract"]["error_contact"] = {"typo": True}
        with pytest.raises(ToolContractViolation, match="error_contact"):
            promote(self._draft("book_list"), td)

    def test_PROMOTION_STILL_OBEYS_THE_LIFECYCLE_STATE_MACHINE(self):
        """Rung 2 is an ADDITIONAL gate, never a replacement — a retired declaration coming back is
        a new admission against the current contract, not a status edit."""
        retired = Declaration(id="book_list", kind="tool", source_path="services/book-service/",
                              lifecycle="retired")
        with pytest.raises(UntrustedRow, match="terminal"):
            promote(retired, _satisfying(tool("book_list")))

    #: 🔴 **FOUND BY THE CENSUS: `check_transition`'s two UNKNOWN-LIFECYCLE refusals had never been
    #: exercised.** They were written at CP-1 and had **zero production callers** until `promote()`
    #: became the first one — so a refusal guarding the state machine CP-5.2 stands on could have
    #: been deleted with the whole suite green. `Lifecycle` is a `Literal`, which Python does not
    #: enforce at runtime, so a bogus value genuinely reaches here.
    def test_AN_UNKNOWN_CURRENT_LIFECYCLE_IS_REFUSED(self):
        bogus = Declaration(id="book_list", kind="tool", source_path="services/book-service/",
                            lifecycle="banana")
        with pytest.raises(UntrustedRow, match="unknown current lifecycle"):
            promote(bogus, _satisfying(tool("book_list")))

    def test_AN_UNKNOWN_TARGET_LIFECYCLE_IS_REFUSED(self):
        """`promote` always targets `admitted`, so this refusal is unreachable through it — the
        other movers (a store edit, a migration, an admission script) are why `check_transition`
        lives in `contract.py` rather than at the writer."""
        from app.agentruntime.contract import check_transition
        with pytest.raises(UntrustedRow, match="unknown target lifecycle"):
            check_transition("book_list", "draft", "banana")

    def test_THERE_IS_NO_ESCAPE_HATCH_ON_PROMOTE(self):
        """`admit()` deliberately has no `force=`/`skip_checks=`; a hatch here would make every
        guarantee above advisory."""
        import inspect
        params = set(inspect.signature(promote).parameters)
        assert params == {"declaration", "tool_def", "version", "registry"}, (
            f"promote() grew a parameter: {params}. §6.4 — a declaration that fails admission is "
            f"not patched into compliance and re-run. `registry` and `version` are DATA SOURCES "
            f"(where the contract is read from, and which generation checks it); a parameter that "
            f"changes the VERDICT is the thing this pins against"
        )
        hatch = {p for p in params
                 if any(w in p for w in ("force", "skip", "strict", "allow", "bypass", "ignore"))}
        assert not hatch, (
            f"promote() has a bypass-shaped parameter {hatch}. `require_meta` in this repository "
            f"already demonstrates the shape: a validator that ships its own documented exemption"
        )


class TestWhereTheContractLivesOnDayOne:
    """PO 2026-08-09. `_meta` is the END state (§4); a registry row is what makes a contract
    authorable *today*, exactly the correction §3a/W1 already took for the ref/resolver map."""

    def _draft(self) -> Declaration:
        return Declaration(id="book_list", kind="tool", source_path="services/book-service/",
                           lifecycle="draft")

    def test_A_REGISTRY_CONTRACT_PROMOTES_AND_THE_SOURCE_IS_RECORDED(self):
        td = tool("book_list")
        reg = {"contracts": {"book_list": {m: {"x": 1}
                                           for m in check_tool_contract(td).applicable}}}
        assert promote(self._draft(), td, registry=reg).lifecycle == "admitted"
        assert check_tool_contract(td, registry=reg).source == "registry"

    def test_META_WINS_OVER_THE_REGISTRY_SO_AN_OWNER_CAN_TAKE_IT_BACK(self):
        """The registry is interim authoring. The owning service's own declaration is the truth,
        and the moment one arrives it takes precedence — which is what makes the registry row
        removable rather than a second permanent home."""
        td = _satisfying(tool("book_list"))
        reg = {"contracts": {"book_list": {"error_contract": {"from": "registry"}}}}
        rep = check_tool_contract(td, registry=reg)
        assert rep.source == "_meta"
        assert rep.is_complete

    def test_NO_CONTRACT_ANYWHERE_IS_SOURCE_NONE_NOT_A_SILENT_EMPTY_PASS(self):
        rep = check_tool_contract(tool("book_list"), registry={"contracts": {}})
        assert rep.source == "none"
        assert not rep.is_complete


class TestCostMeasuresWhatTheModelActuallyRECEIVES:
    """🔴 CP-4's `token_cost` serialised `_meta`, which `strip_tool_meta` removes **before the wire
    request** — so the ranking key counted bytes the model never sees. Measured over the frozen
    catalogue at the time of the fix: **9.6% of the whole key**, all 315 tools inflated, median
    rank movement 6 and max 38. It is a sort key against a budget ending in a hard `break`."""

    def test_COST_IGNORES_META_BECAUSE_THE_WIRE_DOES(self):
        from app.agentruntime.derive import token_cost
        td = tool("book_list")
        bloated = json.loads(json.dumps(td))
        bloated.get("function", bloated)["_meta"]["contract"] = {"x": "y" * 5000}
        assert token_cost(bloated) == token_cost(td), (
            "adding metadata the model never receives must not change a tool's rank — this is why "
            "CP-4 refused `_meta.served_by` and why CP-5's contract could not live in `_meta`"
        )

    def test_THE_TWO_STRIPS_AGREE_ON_THE_SHAPE_THE_WIRE_USES(self):
        """`derive.wire_form` is a COPY of `tool_discovery.strip_tool_meta` — the package may not
        import `app.services`, so a drift between them would make `cost` measure a form nothing
        sends.

        🔴 **They have DIFFERENT DOMAINS, and comparing them naively fails.** `strip_tool_meta`
        reads `_fn`, which returns `{}` for a definition with no `function` wrapper — so on the
        FLAT shape the frozen catalogue stores it is a no-op and leaves `_meta` in place. That is
        harmless because production only ever hands it the wrapped OpenAI shape (`stream_service`
        reads `td["function"]` on the line before), but `token_cost` runs over the flat catalogue,
        so `wire_form` must handle both. This asserts agreement where they overlap.
        """
        from app.agentruntime.derive import wire_form
        from app.services.tool_discovery import strip_tool_meta
        cat = catalogue()
        assert cat, "the corpus must be non-empty or this guard is vacuous"
        wrapped = [{"type": "function", "function": t} for t in cat]
        for td in wrapped:
            assert wire_form(td) == strip_tool_meta(td), td["function"].get("name")
        assert any("_meta" in t for t in cat), (
            "the corpus must actually contain `_meta` or this proves nothing"
        )

    def test_WIRE_FORM_ALSO_HANDLES_THE_FLAT_CATALOGUE_SHAPE(self):
        """The shape `token_cost` actually runs over. `strip_tool_meta` does not reach it."""
        from app.agentruntime.derive import wire_form
        flat = tool("book_list")
        assert "_meta" in flat
        assert "_meta" not in wire_form(flat)
        assert wire_form(flat)["name"] == "book_list"
        # A definition carrying no `_meta` at all must come back untouched — folded in here rather
        # than standing alone, because as its own guard it asserted a no-op and no edit could red it.
        bare = {"name": "x", "description": "d"}
        assert wire_form(bare) == bare


class TestTheContractIsVersionedData:

    def test_AN_UNKNOWN_GENERATION_IS_REFUSED_NOT_SILENTLY_CURRENT(self):
        with pytest.raises(ToolContractViolation, match="does not have"):
            tool_contract_for("9.9.9")

    def test_THE_CURRENT_VERSION_IS_A_GENERATION_THIS_RUNTIME_HOLDS(self):
        assert isinstance(tool_contract_for(TOOL_CONTRACT_VERSION), ToolContract)
        assert TOOL_CONTRACT_VERSION in TOOL_CONTRACTS


class TestTheCoverageDenominatorComesFromTheInput:

    def test_PROMOTABLE_PLUS_BLOCKED_EQUALS_THE_CATALOGUE(self):
        cat = catalogue()
        c = coverage(cat)
        assert c["total"] == len(cat)
        assert c["promotable"] + c["blocked"] == len(cat), (
            "a tool that reached neither count would make the coverage figure describe a set the "
            "caller did not hand in — the self-derived denominator this run has been burned by"
        )

    def test_NOTHING_IN_THE_CATALOGUE_IS_PROMOTABLE_TODAY_AND_THAT_IS_THE_POINT(self):
        """Rung 2's fail-closed state, stated as a measurement rather than assumed. When a provider
        starts emitting `_meta.contract` this goes red, which is the moment to celebrate and
        update it."""
        c = coverage(catalogue())
        assert c["promotable"] == 0, (
            f"{c['promotable']} tool(s) now declare a complete contract — rung 2 has its first "
            f"migrated tool. Update this test with the count and the tool names."
        )
        assert c["blocked_by_member"]["error_contract"] == c["total"]
