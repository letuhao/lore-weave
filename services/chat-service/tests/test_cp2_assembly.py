"""CP-2.1 — P4 assembly on the bought toolset. Spec: BUILD-VS-BUY.md §2/§4.4, ARCHITECTURE §0.1/§3.

**A test may REJECT; it may never ADMIT.** Same rule as `test_cp1_membrane.py`, and it bites harder
here: this is the first file in the effort that runs a real third-party agent loop, and a green
loop is the easiest possible way to feel finished.

The item is one sentence — *it must be the deferring API, not the filtering one* — and the guards
below are built so that **the two APIs are compared against each other**, not so that our choice is
asserted. `TestTheTwoApisDiffer` builds the same surface both ways and measures the difference at
the model boundary. If that difference ever stops existing, every other guard in this file becomes
theatre, and it is the one that says so.
"""
from __future__ import annotations

import ast
import asyncio
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.capabilities import ToolSearch
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agentruntime import (
    AssemblyMismatch,
    Declaration,
    Guardrail,
    NotObservable,
    Observation,
    observe,
    prompt_hash,
    DeclarationToolset,
    DenyList,
    admit,
    build,
    NarrowingLog,
    OrderBy,
    RequirementNotAdmitted,
    Score,
    TakeWhileBudget,
    rows_of,
    Surface,
    SurfaceAssembler,
    TopK,
    UnresolvedReference,
    UntrustedRow,
    advertised_names,
    deferred_names,
    discover,
    excluded_by,
    toolset_for,
    withholding_notice,
)
from app.agentruntime import assembly as _assembly
from app.agentruntime import observation as _observation

_REPO = Path(__file__).resolve().parents[3]
_PACKAGE = _REPO / "services" / "chat-service" / "app" / "agentruntime"


def _row(name: str, service: str = "book-service") -> dict:
    return {
        "id": name,
        "kind": "tool",
        "owning_service": service,
        "lifecycle": "admitted",
        "contract_version": "1.0.0",
        "admitted_against": "1.0.0",
        "members": [],
    }


def _doc(*names: str) -> dict:
    return {
        "manifest_version": 1,
        "contract_version": "1.0.0",
        "declarations": [_row(n, f"svc-{i}") for i, n in enumerate(names)],
    }


def _split(doc: dict, withhold: tuple[str, ...]) -> Surface:
    """Assemble one pass, withholding `withhold` through a real narrowing stage.

    Deliberately NOT a hand-built `Surface`: the withheld records have to be the ones the narrowing
    actually wrote, or the reason channel is tested against text this file invented.
    """
    asm = SurfaceAssembler(doc, log=NarrowingLog())
    pipeline = [DenyList(names=withhold, stage="probe_budget", reason="over budget")] if withhold else []
    return asm.assemble(pass_number=1, pipeline=pipeline)


async def _executor(name: str, args: dict, ctx) -> str:
    return f"ran {name}"


def _defs(toolset) -> list:
    """The tool defs the assembled toolset yields, through the library's own `get_tools`."""
    tools = asyncio.run(toolset.get_tools(None))
    return [t.tool_def for t in tools.values()]


# ── the API choice, which IS the item ───────────────────────────────────────────────────────────

class TestTheTwoApisDiffer:
    """REJECTS: an assembly whose choice of reduction API cannot be observed.

    🔴 **THIS IS THE ONLY GUARD IN THE FILE THAT MEASURES THE ITEM RATHER THAN OUR IMPLEMENTATION
    OF IT.** Every other test here would stay green if `.defer_loading()` silently became a
    synonym for `.filtered()` in some future version of the library — they assert flags we set.
    This one runs both surfaces through a real agent loop and requires the withheld declaration to
    be **unreachable under the ceiling API and reachable under the deferring one**. It is
    deliberately expensive and deliberately first.
    """

    def _run(self, make_toolset) -> tuple[list[list[str]], list[str]]:
        """Drive a real agent: search for the withheld name, then try to call it.

        `make_toolset(executor)` builds the toolset under test, so the executor handed to it is
        this method's spy. Returns the tool names offered at each model turn and the declarations
        the executor actually RAN — **and the second is not decoration.** A revealed definition the
        model cannot call is a screen disagreeing with the runtime, which is exactly the failure
        V-LIVE recorded at CP-1: the row said `withheld` and the model said the tool *"does not
        exist at all"*. Only the executor can say whether the call landed.
        """
        ran: list[str] = []
        turns: list[list[str]] = []

        async def spy(name, args, ctx):
            ran.append(name)
            return f"ran {name}"

        def model_fn(messages, info: AgentInfo):
            turns.append(sorted(t.name for t in info.function_tools))
            if len(turns) == 1:
                return ModelResponse(parts=[ToolCallPart("search_tools", {"queries": ["glossary"]})])
            if len(turns) == 2 and "glossary_search" in turns[-1]:
                return ModelResponse(parts=[ToolCallPart("glossary_search", {})])
            return ModelResponse(parts=[TextPart("done")])

        agent = Agent(FunctionModel(model_fn), toolsets=[make_toolset(spy)],
                      capabilities=[ToolSearch()])
        asyncio.run(agent.run("find the glossary tool"))
        return turns, ran

    def test_THE_DEFERRING_API_KEEPS_A_WITHHELD_DECLARATION_REACHABLE(self):
        doc = _doc("book_list", "glossary_search")
        surface = _split(doc, ("glossary_search",))
        turns, ran = self._run(lambda ex: toolset_for(doc, surface, executor=ex))

        assert turns[0] == ["book_list"], (
            "the withheld declaration was on the wire at pass 1 - deferring must HIDE it"
        )
        assert "glossary_search" in turns[1], (
            "the withheld declaration never became reachable. `defer_loading` that cannot be "
            "revealed is `filtered` with extra steps, and CP-2.4 has no subject"
        )
        assert ran == ["glossary_search"], (
            f"the revealed declaration was shown but never executed: {ran}. Visible is not "
            f"reachable, and asserting the weaker one was this guard's first draft"
        )

    def test_THE_CEILING_API_MAKES_IT_UNREACHABLE__the_control_that_gives_the_test_above_meaning(self):
        """The same surface, assembled the way the item forbids.

        🔴 **A control that agrees with its seed is theatre**, and this run has shipped two of
        those. So this one is required to DISAGREE: under `.filtered()` the search returns nothing,
        the declaration never appears at any turn, and nothing is executed. If this ever goes green
        alongside the test above, both are meaningless and this docstring is the notice.
        """
        doc = _doc("book_list", "glossary_search")
        surface = _split(doc, ("glossary_search",))
        offered = frozenset(surface.names)

        # The forbidden assembly, written HERE (in the test tree) precisely because the gate
        # refuses it inside the package. Building it is how the comparison exists at all.
        def ceiling(ex):
            full = toolset_for(doc, surface, executor=ex)
            return DeclarationToolset(
                [d for d in _defs(full) if d.name in offered], executor=ex
            )

        turns, ran = self._run(ceiling)

        assert turns[0] == ["book_list"]
        assert all("glossary_search" not in t for t in turns), (
            "a FILTERED declaration became reachable - then the two APIs do not differ and the "
            "item cannot be scored"
        )
        assert ran == [], f"a filtered declaration was executed: {ran}"


# ── the assembly's own properties ───────────────────────────────────────────────────────────────

class TestWithheldIsNotAbsent:
    """REJECTS: an assembly that drops the withheld declarations out of the toolset."""

    def test_THE_TOOLSET_HOLDS_EVERY_ADMITTED_DECLARATION_NOT_ONLY_THE_OFFERED_ONES(self):
        doc = _doc("a", "b", "c")
        surface = _split(doc, ("b",))
        defs = _defs(toolset_for(doc, surface, executor=_executor))
        assert sorted(d.name for d in defs) == ["a", "b", "c"], (
            "membership is the ceiling: a declaration missing from `get_tools` cannot be revealed "
            "by any later mechanism"
        )

    def test_THE_WITHHELD_ONE_IS_MARKED_AND_THE_OFFERED_ONES_ARE_NOT(self):
        doc = _doc("a", "b", "c")
        defs = _defs(toolset_for(doc, _split(doc, ("b",)), executor=_executor))
        assert advertised_names(defs) == ("a", "c")
        assert deferred_names(defs) == ("b",)

    def test_WITH_NOTHING_WITHHELD_NOTHING_IS_DEFERRED__tool_names_None_would_defer_EVERYTHING(self):
        """🔴 The library's default for `tool_names` is `None`, which means *mark them all*.

        An empty withheld set reaching that default hides the entire surface while every count in
        this file still balances - the failure would be invisible to conservation and total to the
        model. The empty case is passed explicitly for that reason, and this is the guard on it.
        """
        doc = _doc("a", "b")
        defs = _defs(toolset_for(doc, _split(doc, ()), executor=_executor))
        assert deferred_names(defs) == ()
        assert advertised_names(defs) == ("a", "b")

    def test_EACH_PASS_DEFERS_ITS_OWN_WITHHELD_SET_NOT_A_PREVIOUS_PASSES(self):
        """🔴 The contradiction `pass_number` was added to make detectable, now at the toolset.

        A verifier once found **19 of 303 withheld declarations simultaneously advertised on every
        pass**, and could not tell a contradiction from a sequence because the record was timeless.
        The assembler's own fix was to count only what THIS assembly registered (`_log_mark`); this
        checks that the property survives the trip through `toolset_for`, across three passes of
        one turn that share one log — the arrangement the module docstring explicitly blesses and
        the one where a shared counter goes wrong.
        """
        doc = _doc("a", "b", "c")
        log = NarrowingLog()
        asm = SurfaceAssembler(doc, log=log)
        seen = []
        for pass_number, drop in ((1, ("b",)), (2, ("c",)), (3, ())):
            pipeline = ([DenyList(names=drop, stage="probe_budget", reason="over budget")]
                        if drop else [])
            surface = asm.assemble(pass_number=pass_number, pipeline=pipeline)
            defs = _defs(toolset_for(doc, surface, executor=_executor))
            seen.append((advertised_names(defs), deferred_names(defs)))

        assert seen == [
            (("a", "c"), ("b",)),
            (("a", "b"), ("c",)),
            (("a", "b", "c"), ()),
        ], f"a pass carried another pass's withholding: {seen}"
        # The turn-level record still accumulates - the two answer different questions.
        assert [(e.declaration_id, e.pass_number) for e in log.entries] == [("b", 1), ("c", 2)]

    def test_A_QUERY_FILTER_SHARING_THE_LOG_DOES_NOT_DEFER_WHAT_THE_ASSEMBLY_OFFERS(self):
        """🔴 The **same-pass** case, which is the one `_log_mark` exists for and the one the
        three-pass sequence above cannot reach.

        `discover(kind=…)` filters a QUERY and registers its removals on the shared log at pass 1;
        the assembler then advertises those very declarations at pass 1. An assembly that read the
        whole log instead of its own contribution would defer what it is simultaneously offering —
        which is the contradiction a verifier measured at 19 of 303, recreated here on purpose so
        that the production post-condition is what stops it.
        """
        doc = _doc("a", "b", "c")
        log = NarrowingLog()
        discover(doc, kind="skill", log=log, pass_number=1)   # every row is a tool: all 3 filtered
        assert len(log.entries) == 3, "the query filter registered nothing; the case is not set up"

        surface = SurfaceAssembler(doc, log=log).assemble(pass_number=1)
        defs = _defs(toolset_for(doc, surface, executor=_executor))
        assert deferred_names(defs) == (), (
            "the assembly deferred declarations that a QUERY filter removed, at the same pass it "
            "advertises them"
        )
        assert advertised_names(defs) == ("a", "b", "c")

    def test_A_DECLARATION_THAT_WAS_NEVER_ADMITTED_IS_ABSENT_RATHER_THAN_DEFERRED(self):
        """The membrane, restated at the new boundary: deferring is for the withheld, not a way
        for an un-admitted declaration to arrive hidden."""
        doc = _doc("a", "b")
        defs = _defs(toolset_for(doc, _split(doc, ("b",)), executor=_executor))
        names = {d.name for d in defs}
        assert "legacy_tool" not in names and names == {"a", "b"}


class TestTheReasonTravelsWithoutReachingTheModel:
    """REJECTS: a withholding whose reason is lost, or one that leaks into the model's prose.

    Both directions matter. §0.14.3 requires the record; §5 requires the model to be *told* it is
    withholding something — but told through a mechanism, not by our reason text riding in a
    description field where it becomes prose the model has to interpret (58-66% of what the model
    sees as an error is already our own prose).
    """

    def test_THE_WITHHELD_RECORD_IS_CARRIED_ON_THE_META_CHANNEL(self):
        doc = _doc("a", "b")
        surface = _split(doc, ("b",))
        defs = _defs(toolset_for(doc, surface, executor=_executor))
        assert excluded_by(defs) == {
            "b": {"tool": "b", "stage": "probe_budget", "reason": "over budget", "pass": 1}
        }

    def test_AN_OFFERED_DECLARATION_CARRIES_NO_EXCLUSION_RECORD(self):
        doc = _doc("a", "b")
        defs = _defs(toolset_for(doc, _split(doc, ("b",)), executor=_executor))
        assert "a" not in excluded_by(defs)

    def test_NO_REASON_TEXT_IS_ON_ANY_DESCRIPTION(self):
        doc = _doc("a", "b")
        defs = _defs(toolset_for(doc, _split(doc, ("b",)), executor=_executor))
        assert all(d.description is None for d in defs), (
            "a generated description is this module's words wearing the declaration's voice"
        )


class TestTheSurfaceAndTheManifestAreReconciled:
    """REJECTS: a toolset assembled from a surface that does not match the manifest it names."""

    def test_A_STALE_SURFACE_IS_REFUSED_RATHER_THAN_RECONCILED(self):
        """The manifest was regenerated under the surface: same number of declarations, one of
        them a different one. Cardinality is deliberately unchanged so the IDENTITY check is what
        fires — a fixture that also breaks the count would red on the clause above and leave this
        one unexercised while reading green."""
        surface = _split(_doc("a", "b"), ("b",))
        with pytest.raises(AssemblyMismatch, match="not admitted"):
            toolset_for(_doc("a", "c"), surface, executor=_executor)

    def test_A_DECLARATION_BOTH_OFFERED_AND_WITHHELD_IS_CAUGHT_BY_THE_COUNT_NOT_THE_SET(self):
        """🔴 The contradiction `pass_number` exists to catch: 19 of 303 withheld declarations were
        once simultaneously advertised on every pass. `set(offered) | set(withheld)` equals the
        admitted set in that state - only the cardinality check fires."""
        doc = _doc("a", "b")
        contradictory = Surface(
            names=("a", "b"),
            pass_number=1,
            withheld=({"tool": "b", "stage": "s", "reason": "r", "pass": 1},),
        )
        with pytest.raises(AssemblyMismatch, match="balances the SET"):
            toolset_for(doc, contradictory, executor=_executor)

    def test_A_SURFACE_NAMING_AN_UNADMITTED_DECLARATION_IS_REFUSED(self):
        doc = _doc("a", "b")
        # Cardinality deliberately BALANCED (2 named, 2 admitted) so the set check is what fires.
        # With an unbalanced fixture the count check would raise first and this guard would be
        # green over a clause it never reached - the bystander shape R26 found twice.
        forged = Surface(names=("a", "legacy_tool"), pass_number=1, withheld=())
        with pytest.raises(AssemblyMismatch, match="not admitted"):
            toolset_for(doc, forged, executor=_executor)


class TestTheToolsetCanExecuteOnlyWhatItWasHanded:
    """REJECTS: a toolset that can reach an executor it was not given. That would be a code path
    from this package to whatever it found, which is the one thing §3 forbids."""

    def test_THE_EXECUTOR_IS_A_REQUIRED_KEYWORD(self):
        with pytest.raises(TypeError):
            DeclarationToolset([])            # type: ignore[call-arg]

    def test_A_CALL_GOES_TO_THE_INJECTED_EXECUTOR_AND_NOWHERE_ELSE(self):
        seen: list[str] = []

        async def spy(name, args, ctx):
            seen.append(name)
            return "ok"

        doc = _doc("a")
        toolset = toolset_for(doc, _split(doc, ()), executor=spy)
        tools = asyncio.run(toolset.get_tools(None))
        out = asyncio.run(toolset.call_tool("a", {}, None, tools["a"]))
        assert seen == ["a"] and out == "ok"

    def test_EVERY_TOOL_IS_BUILT_WITH_ZERO_RETRIES(self):
        """A retried call is a second call the manifest never authorised; whether a declaration is
        safe to re-run is C-13's question and no row can answer it yet."""
        doc = _doc("a", "b")
        tools = asyncio.run(toolset_for(doc, _split(doc, ("b",)), executor=_executor).get_tools(None))
        assert {t.max_retries for t in tools.values()} == {0}

    def test_THE_PARAMETER_SCHEMA_IS_CLOSED_NOT_OPEN(self):
        """`{}` means *anything goes*, which is a claim no manifest row has ever made. A row with
        no declared parameters means the arguments are UNKNOWN, and those are different."""
        doc = _doc("a")
        defs = _defs(toolset_for(doc, _split(doc, ()), executor=_executor))
        assert defs[0].parameters_json_schema["additionalProperties"] is False


# ── 2.2 · the widening rule (§4.3) ──────────────────────────────────────────────────────────────

class TestAPlanStepsDeclarationIsAdvertised:
    """REJECTS: a plan step whose declaration the budget removed — the class the three heuristics
    in `tool_surface.py` each patch at one site.

    The measured instance is the `co_write` incident: **6,948 characters of plan prose, zero tool
    calls**, because `plan_propose_spec` and `plan_compile` were named only in signature form and
    the backtick scraper required a closing backtick. §4.3 states the obligation once, at assembly,
    where it cannot be blind to a stage it has never heard of.
    """

    def _assemble(self, *, drop, required):
        """🔴 **THE EMPTY `drop` MUST PRODUCE AN EMPTY PIPELINE, NOT AN EMPTY `DenyList`.**

        The first version built `DenyList(names=())` unconditionally, and the module refuses that
        outright — *"a deny-list with no names removes nothing and registers nothing"*. So two
        guards below went green on **that** `ValueError` instead of the one they name: the bound on
        `required`, and the un-admitted refusal. A control satisfied by a different clause has
        measured a bystander, which is R26's finding reproduced inside the guards written for it.
        """
        doc = _doc("a", "b", "c")
        log = NarrowingLog()
        pipeline = ([DenyList(names=drop, stage="token_budget", reason="over budget")]
                    if drop else [])
        return log, SurfaceAssembler(doc, log=log).assemble(
            pass_number=1, pipeline=pipeline, required=required)

    def test_A_REQUIRED_DECLARATION_SURVIVES_A_STAGE_THAT_REMOVED_IT(self):
        _, surface = self._assemble(drop=("b", "c"), required=["b"])
        assert surface.names == ("a", "b")
        assert [w["tool"] for w in surface.withheld] == ["c"], (
            "a widened declaration is still listed as WITHHELD - the column would then say the "
            "model could not see something it was offered"
        )

    def test_A_REQUIRED_DECLARATION_SURVIVES_A_RANK_DEPENDENT_CUT_TOO(self):
        """The budget stage, not just a name list — a running accumulator is the shape §4.3's
        motivating incident actually died on."""
        doc = {
            "manifest_version": 1, "contract_version": "1.0.0",
            "declarations": [{**_row(n), "members": []} for n in ("a", "b", "c")],
        }
        log = NarrowingLog()
        surface = SurfaceAssembler(doc, log=log).assemble(
            pass_number=1,
            pipeline=[OrderBy(keys=(("id", "asc"),)), TopK(k=1, stage="top_k", reason="rank")],
            required=["c"],
        )
        assert surface.names == ("a", "c")
        assert [w["tool"] for w in surface.withheld] == ["b"]

    def test_THE_NARROWING_RECORD_SURVIVES_THE_WIDENING(self):
        """🔴 **THE DESIGN DECISION, GUARDED.** Deleting the narrowing would be shorter and would
        balance the conservation law just as well — and it would erase the only evidence that a
        stage wanted this declaration gone and the plan overruled it. Each of the three legacy
        heuristics was written blind to the other two because nobody could see that."""
        log, _ = self._assemble(drop=("b",), required=["b"])
        assert [(e.declaration_id, e.stage) for e in log.entries] == [("b", "token_budget")]

    def test_THE_WIDENING_RECORD_NAMES_WHAT_IT_OVERRULED(self):
        log, _ = self._assemble(drop=("b",), required=["b"])
        assert log.widening_records() == [{
            "tool": "b", "stage": "widening",
            "reason": "named by the current plan step (§4.3)", "pass": 1,
            "over": {"stage": "token_budget", "reason": "over budget"},
        }]

    def test_CONSERVATION_STILL_HOLDS_WITH_A_WIDENING_IN_PLAY(self):
        """`offered + registered == admitted` is evaluated in production code, so this checks the
        widened declaration moved sides rather than being counted twice or not at all."""
        _, surface = self._assemble(drop=("b", "c"), required=["b"])
        assert len(surface.names) + len(surface.withheld) == 3

    def test_A_REQUIRED_DECLARATION_THE_MANIFEST_DOES_NOT_ADMIT_IS_REFUSED(self):
        """§4.3 widens the ADVERTISED set within the ADMITTED set. A step naming something
        un-admitted is asking the assembler to invent, and that is §0.1's clause, not §4.3's."""
        with pytest.raises(RequirementNotAdmitted, match="not a licence to invent"):
            self._assemble(drop=(), required=["ghost"])

    def test_THE_REFUSAL_IS_ITS_OWN_CLASS_NOT_UNRESOLVED_REFERENCE(self):
        """C-11/M5's `UnresolvedReference` is a *member* of an admitted declaration, resolved at
        GENERATION. This is a plan step, at ASSEMBLY, from outside the manifest — a different
        actor at a different moment. One class for both would be `ok=true` again."""
        assert RequirementNotAdmitted is not UnresolvedReference
        assert issubclass(RequirementNotAdmitted, UntrustedRow), (
            "a new refusal type outside the documented one breaks every caller's `except`"
        )

    @pytest.mark.parametrize("bad", [b"a", 42, None, ["a"]])
    def test_A_REQUIRED_NAME_IS_BOUNDED_LIKE_EVERY_OTHER_OPERAND(self, bad):
        """It is compared against every row, so a custom `__eq__` is a regex stage with zero new
        operators — and its `__repr__` reaches a persisted record through `reason`.

        🔴 **`pytest.raises(ValueError)` ALONE IS GREEN WITHOUT THE BOUND.** `RequirementNotAdmitted`
        subclasses `UntrustedRow`, which subclasses `ValueError` — so deleting the type bound leaves
        this raising a *different* ValueError from the un-admitted check two lines later, and the
        guard never notices. The message is what separates them.
        """
        with pytest.raises(ValueError, match="plain str"):
            self._assemble(drop=(), required=[bad])

    def test_AN_EMPTY_REQUIREMENT_CHANGES_NOTHING(self):
        _, surface = self._assemble(drop=("b",), required=[])
        assert surface.names == ("a", "c") and [w["tool"] for w in surface.withheld] == ["b"]

    def test_THE_REQUIREMENT_IS_MATERIALISED_BEFORE_IT_IS_CHECKED(self):
        """🔴 A verifier already drove a four-line rogue class through `pipeline`: an object
        yielding different stages on its second iteration was validated as one pipeline and
        executed as another. `required` is iterated twice for the same reason and gets the same
        defence."""
        class Rogue:
            def __init__(self):
                self.n = 0

            def __iter__(self):
                self.n += 1
                return iter(["b"] if self.n == 1 else ["ghost"])

        doc = _doc("a", "b")
        surface = SurfaceAssembler(doc, log=NarrowingLog()).assemble(
            pass_number=1,
            pipeline=[DenyList(names=("b",), stage="token_budget", reason="over budget")],
            required=Rogue(),
        )
        assert surface.names == ("a", "b"), (
            "the obligation that was CHECKED is not the one that RAN"
        )

    def test_THE_WIDENED_DECLARATION_REACHES_THE_TOOLSET_AS_ADVERTISED(self):
        """End to end: §4.3's obligation has to survive the trip through CP-2.1's assembly, or the
        rule holds in a dataclass and not on the wire."""
        doc = _doc("a", "b", "c")
        surface = SurfaceAssembler(doc, log=NarrowingLog()).assemble(
            pass_number=1,
            pipeline=[DenyList(names=("b", "c"), stage="token_budget", reason="over budget")],
            required=["b"],
        )
        defs = _defs(toolset_for(doc, surface, executor=_executor))
        assert advertised_names(defs) == ("a", "b")
        assert deferred_names(defs) == ("c",)


# ── 2.10 · a pipeline ranks by a relevance ITS OWN scoring stage produced ───────────────────────

class TestRelevanceCanOnlyComeFromTheScoringStage:
    """REJECTS: a rank steered by a value nobody computed.

    🔴 **THE MEASURED DEFECT:** a hand-typed `"relevance": 9999` **selected which single
    declaration the model sees** under `OrderBy(relevance) → TopK(1)`. CP-1's answer was to remove
    the field from `ROW_FIELDS` entirely — *"§0.14.1c owns the producers: **CP-2 for `relevance`**...
    the field arrives WITH its producer, in the same change"*. This is that change.
    """

    _DOC = None

    def _doc3(self):
        return {
            "manifest_version": 1, "contract_version": "1.0.0",
            "declarations": [_row(n) for n in ("a", "b", "c")],
        }

    def test_A_PIPELINE_RANKS_BY_THE_RELEVANCE_ITS_OWN_STAGE_PRODUCED(self):
        doc = self._doc3()
        surface = SurfaceAssembler(doc, log=NarrowingLog()).assemble(
            pass_number=1,
            pipeline=[Score(scores=(("a", 1), ("b", 9), ("c", 5))),
                      OrderBy(keys=(("relevance", "desc"),)),
                      TopK(k=2, stage="top_k", reason="over rank")])
        assert surface.names == ("b", "c")

    def test_A_HAND_TYPED_RELEVANCE_ON_DISK_IS_STILL_REFUSED(self):
        """🔴 **THE FIELD DID NOT COME BACK.** `relevance` is absent from `ROW_FIELDS`, so the
        forgery CP-1 removed it for is refused at every door — and that is *why* the guarantee
        above needs no extra check: the only thing that can put `relevance` on a row is the stage."""
        forged = {
            "manifest_version": 1, "contract_version": "1.0.0",
            "declarations": [{**_row("a"), "relevance": 9999}],
        }
        with pytest.raises(UntrustedRow, match="relevance"):
            rows_of(forged)

    def test_RANKING_ON_RELEVANCE_WITH_NO_PRODUCER_RAISES(self):
        """The third leg. Together with the two above: a pipeline that ranks on `relevance` either
        ran the stage or raises, and there is no third outcome."""
        with pytest.raises(ValueError, match="does not carry"):
            SurfaceAssembler(self._doc3(), log=NarrowingLog()).assemble(
                pass_number=1, pipeline=[OrderBy(keys=(("relevance", "desc"),))])

    def test_A_PARTIAL_SCORE_SET_IS_A_REJECTION_NOT_A_ZERO(self):
        """Ranking a declaration last because **nobody scored it** is indistinguishable in the
        record from ranking it last because it **scored badly** — and a budget cuts on rank."""
        with pytest.raises(ValueError, match="no score for"):
            SurfaceAssembler(self._doc3(), log=NarrowingLog()).assemble(
                pass_number=1, pipeline=[Score(scores=(("a", 1),))])

    def test_A_SCORE_FOR_A_DECLARATION_THIS_PASS_DOES_NOT_CARRY_IS_REFUSED(self):
        """The other direction: a score for something absent ranks nothing and hides a stale
        producer, which is a defect that would otherwise never surface."""
        with pytest.raises(ValueError, match="does not carry"):
            SurfaceAssembler(self._doc3(), log=NarrowingLog()).assemble(
                pass_number=1,
                pipeline=[Score(scores=(("a", 1), ("b", 2), ("c", 3), ("ghost", 4)))])

    @pytest.mark.parametrize("bad", [True, 1.0, "9", None])
    def test_A_SCORE_IS_A_PLAIN_INT(self, bad):
        """`True` is in the list on purpose: `bool` is an `int` subclass, so `isinstance` admits it.
        A rank computed from a value with a custom `__lt__` is arbitrary logic wearing a number's
        clothes — the same route §0.14.1 closes for stage parameters."""
        with pytest.raises(ValueError):
            Score(scores=(("a", bad),))

    @pytest.mark.parametrize("kind", ["list", "set", "generator"])
    def test_THE_SCORE_SET_IS_A_TUPLE_NOT_A_LAZY_OR_MUTABLE_CONTAINER(self, kind):
        """🔴 Census-found: this refusal shipped with nothing checking it. A container with a custom
        `__iter__` decides the ranking, which is arbitrary logic — the same route §0.14.1 closes for
        every other stage parameter — and a **generator** is empty the second time anyone reads it,
        so the first consumer ranks and every later one sees nothing.

        🔴 **THE VEHICLE IS BUILT HERE, NOT IN THE `parametrize` LIST.** The first version passed
        `(p for p in [...])` as a parameter value, and a generator in a parametrize list is created
        **once at collection** and shared for the whole session — so it is exhausted after its first
        use and any re-run tests something else. That is the same latent defect this guard is
        written about, in the guard itself.
        """
        bad = {"list": [("a", 1)], "set": {("a", 1)},
               "generator": (p for p in [("a", 1)])}[kind]
        with pytest.raises(ValueError, match="Score.scores"):
            Score(scores=bad)

    @pytest.mark.parametrize("bad", [("a",), ("a", 1, 2), ["a", 1], "ab"])
    def test_A_SCORE_ENTRY_IS_AN_ID_AND_A_SCORE_AND_NOTHING_ELSE(self, bad):
        """🔴 **CENSUS-FOUND, and I mis-read it once.** It reported ordinal 2 of
        `Score.__post_init__` SILENT; I assumed that was the tuple bound — which *is* guarded and
        reds when neutered, measured — and only counting the `raise` statements showed ordinal 2 is
        the **malformed-pair** refusal, which nothing tested.

        The three-element entry is the interesting vehicle: it unpacks nowhere, so without this
        clause it would reach `name, value = pair` as a bare tuple-unpacking `ValueError` — a crash
        rather than a stated refusal.
        """
        with pytest.raises(ValueError, match="not an .id, score. pair"):
            Score(scores=(bad,))

    def test_TWO_SCORES_FOR_ONE_DECLARATION_IS_REFUSED(self):
        """🔴 Also census-found. *Which one ranks?* — and whichever a reader assumes, the other
        consumer assumes the opposite. The same ambiguity `advertised` refuses for a duplicate
        pass."""
        with pytest.raises(ValueError, match="two entries"):
            Score(scores=(("a", 1), ("a", 2)))

    def test_THE_SCORES_ARE_DATA_NOT_A_CALLABLE(self):
        """§0.14.1: *a stage that merely answers a question is a closure with a different name*, and
        a narrowing must have **an identity a reader can hash and compare**. A `Callable` field
        would make two pipelines that rank differently indistinguishable in a record."""
        import dataclasses

        field = {f.name: f for f in dataclasses.fields(Score)}["scores"]
        assert "Callable" not in str(field.type)
        assert hash(Score(scores=(("a", 1),))) == hash(Score(scores=(("a", 1),)))

    def test_THE_SCORING_STAGE_REMOVES_NOTHING__it_is_a_producer(self):
        """It neither registers nor touches the conservation law, because it drops no declaration.
        A producer that could remove would be a narrowing with no `{tool, stage, reason, pass}`."""
        doc = self._doc3()
        surface = SurfaceAssembler(doc, log=NarrowingLog()).assemble(
            pass_number=1, pipeline=[Score(scores=(("a", 1), ("b", 2), ("c", 3)))])
        assert len(surface.names) == 3 and surface.withheld == ()

    def test_THE_BUDGET_ARRIVES_AS_A_PARAMETER_AND_NOTHING_READS_THE_ENVIRONMENT(self):
        """§0.14.1's other half: *the budget arrives as a parameter rather than as `os.environ`
        read at import.*

        🔴 **THE FIRST DRAFT ASSERTED THAT NO MODULE IMPORTS `os` AND WENT RED ON `ambient.py`** —
        which is the package's **designated** ambient boundary (§0.14.4), the one file that exists
        so every ambient capability lives in one place. A guard convicting the mechanism built to
        contain the thing it is guarding against. The claim is narrower and truer: `os` lives in
        `ambient.py` **and nowhere else**, and what it reads there is a manifest **path**, not a
        budget."""
        import dataclasses

        assert "budget" in {f.name for f in dataclasses.fields(TakeWhileBudget)}, (
            "the budget stopped being a constructor parameter"
        )
        importers = []
        for path in sorted(_PACKAGE.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text("utf-8"))):
                mods = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                        else [a.name for a in node.names] if isinstance(node, ast.Import) else [])
                if any(m.split(".", 1)[0] == "os" for m in mods):
                    importers.append(path.name)
        assert importers == ["ambient.py"], (
            f"`os` is imported by {importers}; §0.14.4 keeps every ambient capability in ONE file, "
            f"and a budget read from the environment anywhere else is exactly what §0.14.1 forbids"
        )
        # 🔴 **OVER THE AST, NOT THE TEXT.** A substring check said `ambient.py` "grew a budget
        # reader" because the word appears in its PROSE. That is the same crude-gate class this run
        # has already recorded — a substring gate over SQL that was green over wrong data — arriving
        # from the other side: red over a docstring. What is forbidden is a budget-shaped READ.
        tree = ast.parse((_PACKAGE / "ambient.py").read_text("utf-8"))
        env_reads = [
            c.value for c in ast.walk(tree)
            if isinstance(c, ast.Constant) and isinstance(c.value, str)
            and c.value.isupper() and "BUDGET" in c.value
        ]
        assert env_reads == [], (
            f"the ambient boundary reads {env_reads}; §0.14.1 requires the budget to arrive as a "
            f"parameter, and an env-read one cannot be varied per pipeline"
        )
        assert not [f for f in ast.walk(tree)
                    if isinstance(f, ast.FunctionDef) and "budget" in f.name.lower()], (
            "the ambient boundary grew a budget reader"
        )


# ── 2.8 · runtime_variant at a structural chokepoint ────────────────────────────────────────────

class TestTheArmLabelCannotBeOmittedOrPassedWrongly:
    """REJECTS: an unlabelled new-runtime row, which is survivorship bias rather than caution.

    🔴 **`legacy` AS A DEFAULT IS FAIL-SAFE IN ONLY ONE DIRECTION.** A missing label protects the
    new arm from **false credit** — it never counts as a success. It does **not** protect the new
    arm's own **failure rate**: an unlabelled new-runtime row loses its numerator too, and
    **label-omission correlates with crash and cancel**, the terminal paths a hand-passed label is
    most likely to miss. The arm would measure as safer than it is, by construction.
    """

    def _stamp(self, **over):
        from app.services import instrument

        chunk = {"tool": "book_list", **over}
        return instrument.stamp_tool_call(chunk, source=instrument.SOURCE_TOOL)

    def test_THE_LABEL_IS_NOT_A_PARAMETER_A_CALLER_CAN_PASS_AT_ALL(self):
        """The strongest available form: it cannot be omitted **because it cannot be supplied.**
        Five production call sites stamp tool calls and **not one passes a variant** — under a
        keyword default every one of them wrote `legacy` no matter which arm ran."""
        import inspect

        from app.services import instrument

        params = inspect.signature(instrument.stamp_tool_call).parameters
        assert "runtime_variant" not in params, (
            "the arm label is passable again; a label a caller can pass is one a caller can pass "
            "WRONGLY, and one they can forget on the crash path"
        )

    def test_ON_THE_NEW_ARM_EVERY_STAMP_SAYS_AGENTRUNTIME(self, monkeypatch):
        from app.config import settings
        from app.services import instrument

        monkeypatch.setattr(settings, "agentruntime_arm", True)
        assert self._stamp()["runtime_variant"] == instrument.RUNTIME_AGENTRUNTIME

    def test_THE_CONTROL_ARM_IS_BYTE_IDENTICAL__the_reason_this_row_could_be_built_at_all(
            self, monkeypatch):
        """🔴 CP-1.9 established that a control moved by a change nobody decided invalidates the
        comparison before it starts — **2.2 and 2.3 both declined to touch the control for that
        reason.** This row does not have to: with the flag off, the derived value is the same
        constant the default wrote."""
        from app.config import settings
        from app.services import instrument

        monkeypatch.setattr(settings, "agentruntime_arm", False)
        assert self._stamp()["runtime_variant"] == instrument.RUNTIME_LEGACY

    def test_THE_BACKFILL_PATH_DERIVES_IT_TOO__not_only_the_stamping_one(self, monkeypatch):
        """🔴 **TWO SITES WROTE THE CONSTANT, AND FIXING ONE IS THE PAIR-AT-ONE-END FAILURE** this
        run has now recorded thirteen times. The second is a `setdefault` in the derive path — the
        one that runs for a chunk nobody stamped, which is precisely the crash-and-cancel shape."""
        from app.config import settings
        from app.services import instrument

        monkeypatch.setattr(settings, "agentruntime_arm", True)
        derived = instrument.ensure_tool_call_instrumented(
            {"tool": "book_list", "source": "tool"})
        assert derived["runtime_variant"] == instrument.RUNTIME_AGENTRUNTIME

    def test_NO_SITE_IN_THE_SERVICE_STILL_WRITES_THE_CONSTANT(self):
        """The enumeration, because every ratio published in this run has been a lower bound: no
        module may assign `runtime_variant` from a bare constant any more."""
        import ast

        offenders = []
        root = _REPO / "services" / "chat-service" / "app"
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text("utf-8"))):
                is_assign = (isinstance(node, ast.Assign)
                             and any(isinstance(t, ast.Subscript)
                                     and isinstance(t.slice, ast.Constant)
                                     and t.slice.value == "runtime_variant" for t in node.targets))
                if is_assign and isinstance(node.value, ast.Name):
                    offenders.append(f"{path.name}:{node.lineno}")
        assert offenders == [], f"a bare constant is assigned to runtime_variant at {offenders}"


# ── 2.9 · prompt_hash ───────────────────────────────────────────────────────────────────────────

class TestAPromptCanChangeAndSomethingNotices:
    """REJECTS: a turn whose instructions changed with no column that could tell.

    The failure is **currently undetectable**: nothing answers *"was this turn assembled from the
    same instructions as that one"*, so a regression caused by an edited system prompt is
    indistinguishable from a model getting worse.
    """

    def test_AN_EDITED_PROMPT_PRODUCES_A_DIFFERENT_DIGEST(self):
        a = "You are a co-writer."
        assert prompt_hash(a) != prompt_hash(a + " Be brief.")

    def test_THE_SAME_PROMPT_PRODUCES_THE_SAME_DIGEST(self):
        a = "You are a co-writer."
        assert prompt_hash(a) == prompt_hash(a)

    def test_NFD_AND_NFC_OF_ONE_PROMPT_ARE_ONE_DIGEST(self):
        """🔴 **TWO BYTE-SEQUENCES THAT RENDER IDENTICALLY MUST NOT PRODUCE TWO DIGESTS** (§0.14.2).
        This repository has a measured **1.44× NFD/NFC token swing**, so without normalisation a
        prompt that round-trips through a normalising editor reads as *changed* on every turn and
        the column is noise from the day it ships."""
        import unicodedata

        composed = "You are a co-writer for Mị Đế."
        decomposed = unicodedata.normalize("NFD", composed)
        assert composed != decomposed, "the fixture has no combining marks; it cannot see the bug"
        assert prompt_hash(composed) == prompt_hash(decomposed)

    @pytest.mark.parametrize("excluded", ["code_revision", "seed", "block_hashes"])
    def test_THE_THREE_RED_TEAM_KILLED_ARE_STILL_ABSENT(self, excluded):
        """🔴 The first draft of this row bundled four things and red team killed three, **each for
        a measured reason** — `GIT_SHA` is `None` in every scenario, `seed` is already forwarded and
        consumes no randomness at `temperature=0.0`, and `block_hashes` cannot be computed correctly
        on this side of a schema translation. A hash that can be right for the wrong reason is worse
        than none.

        Guarded because *"we decided not to"* is exactly the kind of decision that gets quietly
        re-litigated by whoever next wants a fingerprint column."""
        import dataclasses

        names = {f.name for f in dataclasses.fields(Observation)}
        assert excluded not in names
        assert excluded in (_observation.prompt_hash.__doc__ or ""), (
            f"{excluded} was dropped from the record AND from the reasons - a deletion with no "
            f"stated cause is one the next reader will undo"
        )


# ── 2.7 · THE ROUTE — a turn's advertised set comes from the manifest ───────────────────────────

class TestTheRouteServesFromTheManifestAndNothingElse:
    """REJECTS: an arm that quietly keeps the legacy core, and a control arm this route perturbed.

    🔴 **THIS IS THE ROW EVERY `CANNOT DETERMINE` IN CP-2 HAS BEEN WAITING ON.** 2.1–2.5 are all
    QC2 `CANNOT DETERMINE` for one mechanical reason — no request path reached the package. This
    branch is that path, at the **single ADVERTISE chokepoint** (three callers, one edit).
    """

    def _advertise(self, **over):
        from app.services import stream_service

        kwargs = dict(catalog_index={}, active_tool_names=set(), extra_frontend=[])
        kwargs.update(over)
        return stream_service._advertise_discovery_tools(**kwargs)

    def test_THE_CONTROL_ARM_IS_UNTOUCHED_WHEN_THE_FLAG_IS_OFF(self, monkeypatch):
        """🔴 **CP-1.9 SPENT A WHOLE ITEM ON THIS**: a control perturbed by changes nobody decided
        invalidates the comparison before it starts. Measured as byte-identity of the advertised
        payload with the flag off, against the legacy catalogue's real core."""
        from app.config import settings

        legacy_catalog = {
            n: {"type": "function", "function": {"name": n, "parameters": {}}}
            for n in ("glossary_search", "book_read")
        }
        args = dict(catalog_index=legacy_catalog, active_tool_names=set(legacy_catalog),
                    extra_frontend=[])

        monkeypatch.setattr(settings, "agentruntime_arm", False)
        control = self._advertise(**args)
        monkeypatch.setattr(settings, "agentruntime_arm", True)
        new_arm = self._advertise(**args)

        # 🔴 The property is the DIFFERENCE, on identical inputs. An earlier draft asserted that
        # `find_tools` is in the control payload — a proxy for "the core is there" that is coupled
        # to which core tools exist today, and it went red for a reason that had nothing to do
        # with the route. What matters is that the control arm still serves the legacy catalogue
        # and the new arm serves none of it.
        assert control, "the control arm advertised nothing - the fixture cannot see a difference"
        assert {d["function"]["name"] for d in control} >= set(legacy_catalog), (
            "the control arm stopped serving the legacy catalogue - CP-2's control group moved"
        )
        assert new_arm == [], f"the new arm served legacy declarations: {new_arm}"

    def test_ON_THE_NEW_ARM_AN_EMPTY_MANIFEST_ADVERTISES_NOTHING_AT_ALL(self, monkeypatch):
        """`declarations: []` → `[]`. **Not the core, not `find_tools`, not the frontend extras.**
        An arm that kept them would be the membrane leaking through its own route on day one."""
        from app.config import settings

        monkeypatch.setattr(settings, "agentruntime_arm", True)
        assert self._advertise() == []

    def test_NO_LEGACY_DECLARATION_SURVIVES_THE_ROUTE__item_B(self, monkeypatch):
        """Item **B**, at the one place it can be checked structurally: the legacy catalogue is
        handed in, richly populated, and **nothing from it reaches the wire**."""
        from app.config import settings

        legacy_catalog = {
            n: {"type": "function", "function": {"name": n, "parameters": {}}}
            for n in ("glossary_search", "book_read", "kg_build", "propose_edit")
        }
        monkeypatch.setattr(settings, "agentruntime_arm", True)
        payload = self._advertise(catalog_index=legacy_catalog,
                                  active_tool_names=set(legacy_catalog),
                                  extra_frontend=[legacy_catalog["propose_edit"]])
        assert payload == [], f"a legacy declaration reached the wire on the new arm: {payload}"

    def test_THE_BRANCH_READS_NOTHING_FROM_THE_LEGACY_CATALOG(self):
        """🔴 **THE MEMBRANE GATE CANNOT SEE THIS FILE**, so the separation rests on the branch
        returning before any legacy read. Asserted over the AST rather than by behaviour: a
        `return` that happens to be first today is a code path that can stop being first."""
        src = (_REPO / "services" / "chat-service" / "app" / "services"
               / "stream_service.py").read_text("utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "_advertise_discovery_tools")
        branch = next(n for n in fn.body
                      if isinstance(n, ast.If)
                      and "agentruntime_arm" in ast.dump(n.test))
        legacy_args = {"catalog_index", "active_tool_names", "extra_frontend"}

        # 🔴 **THE PROPERTY IS "NOTHING LEGACY IS READ BEFORE IT", NOT "IT IS FIRST".** An earlier
        # draft asserted `index == 0` and went red on a docstring plus a pure local
        # (`restricted = permission_mode in (...)`) — a guard convicting a position rather than
        # the thing the position was standing in for.
        before = fn.body[:fn.body.index(branch)]
        read_before = {x.id for st in before for x in ast.walk(st) if isinstance(x, ast.Name)}
        assert not (read_before & legacy_args), (
            f"{sorted(read_before & legacy_args)} is read before the agentruntime branch, so it "
            f"runs on the new arm too - and `catalog_index` IS the legacy catalog"
        )
        assert all(not isinstance(st, ast.Return) for st in before), (
            "a return precedes the branch, so some path leaves before the route can take it"
        )
        reads = {x.id for x in ast.walk(branch) if isinstance(x, ast.Name)}
        assert not (reads & legacy_args), (
            f"the new arm reads {sorted(reads & legacy_args)} - §3 forbids the code path, not "
            f"merely the wrong result"
        )

    def test_THE_MODEL_IS_TOLD_WHICH_EMPTINESS_THIS_IS__item_A(self):
        """Item **A** — the agent must **say** it has no declarations rather than answering as if
        none were needed. Two emptinesses, and collapsing them is §0.14.3's failure: *nothing
        admitted* has no search that would find anything; *something withheld* does."""
        from app.agentruntime.serve import NO_DECLARATIONS, statement_for

        empty = _split(_doc(), ())
        assert statement_for(empty) == NO_DECLARATIONS
        assert "zero admitted declarations" in NO_DECLARATIONS
        assert "Do not describe a tool call as performed" in NO_DECLARATIONS

        withheld = _split(_doc("a", "b"), ("b",))
        assert statement_for(withheld) != NO_DECLARATIONS, (
            "a withheld surface was described as having no declarations at all - then the model "
            "cannot tell 'nothing exists' from 'something is hidden'"
        )

    def test_THE_ROUTE_RETURNS_THE_SURFACE_SO_P1_IS_RECORDABLE__items_C_and_D(self):
        """Items **C** and **D**. `advertise` returns the payload **and** the `Surface` the
        conservation law already checked — so *what was advertised* and *what was registered* are
        one computation, not a record built somewhere else from something else (the eight-frame
        defect this package exists to make impossible)."""
        from app.agentruntime.serve import advertise

        doc = _doc("a", "b")
        payload, surface = advertise(
            doc, pass_number=1, log=NarrowingLog(),
            pipeline=[DenyList(names=("b",), stage="token_budget", reason="over budget")])
        assert [d["function"]["name"] for d in payload] == list(surface.names)
        assert [w["tool"] for w in surface.withheld] == ["b"]
        # C — the EMPTY state is recordable as `[]`, which is not the same fact as NULL.
        empty_payload, empty_surface = advertise(_doc(), pass_number=1)
        assert empty_payload == [] and empty_surface.names == ()
        record = observe([empty_surface], source="tool", outcome="empty")
        assert record.advertised == (
            {"pass": 1, "tool_choice": "auto", "names": ()},
        ), "an empty pass produced no row - NULL and [] mean different things"

    def test_A_DEFERRED_DECLARATION_IS_NOT_ON_THE_WIRE(self):
        """The route advertises the offered set only; the withheld ones stay in the toolset for
        the reveal path. A payload that carried them would undo CP-2.1 at the last step."""
        from app.agentruntime.serve import advertise

        doc = _doc("a", "b")
        payload, _ = advertise(
            doc, pass_number=1, log=NarrowingLog(),
            pipeline=[DenyList(names=("b",), stage="s", reason="r")])
        assert [d["function"]["name"] for d in payload] == ["a"]


# ── 2.7 (part) · M4 — the registration entry point refuses to boot ──────────────────────────────

class TestTheRuntimeRefusesToBootOnAnIncompleteContract:
    """REJECTS: a service that starts with a manifest it cannot serve.

    🔴 **M4 HAS BEEN RECORDED AS FALSE SINCE CP-1, BY NAME.** *"Nothing imports
    `app.agentruntime`, so there is no boot to refuse — wiring an import so the phrase becomes true
    would be pulling CP-2 forward. Recorded as unmet rather than reworded."* This is the change
    that makes it true, and §3's acceptance test for it is literal: **remove one required clause,
    watch the service fail to start.**
    """

    _ROW = {
        "id": "book_list", "kind": "tool", "owning_service": "book-service",
        "lifecycle": "admitted", "contract_version": "1.0.0", "admitted_against": "1.0.0",
        "members": [],
    }

    def _boot_at(self, tmp_path: Path, declarations, *, write_manifest=True):
        """Boot the package **in a fresh interpreter**, against a manifest we control.

        A subprocess rather than an in-process call, because *"fails to start"* is a claim about a
        process. Measuring it with a `pytest.raises` would establish that a function raises, which
        is a different sentence.
        """
        import json
        import shutil

        root = tmp_path
        shutil.copytree(_PACKAGE, root / "app" / "agentruntime")
        (root / "app" / "__init__.py").write_text("", encoding="utf-8")
        if write_manifest:
            (root / "contracts").mkdir(exist_ok=True)
            (root / "contracts" / "agent-runtime-manifest.json").write_text(
                json.dumps({"manifest_version": 1, "contract_version": "1.0.0",
                            "declarations": declarations}), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-c",
             "from app.agentruntime.boot import boot; boot(); print('BOOTED')"],
            cwd=root, capture_output=True, text=True)

    def test_A_COMPLETE_MANIFEST_BOOTS(self, tmp_path):
        r = self._boot_at(tmp_path, [self._ROW])
        assert r.returncode == 0 and "BOOTED" in r.stdout, r.stderr

    @pytest.mark.parametrize("clause", sorted(_ROW))
    def test_REMOVE_ONE_REQUIRED_CLAUSE_AND_THE_SERVICE_FAILS_TO_START(self, tmp_path, clause):
        """§3's acceptance test, run once **per required clause** rather than once.

        🔴 A single-clause version would establish that ONE omission is caught, and every
        enumeration published in this run has turned out to be a lower bound. Parametrising over
        the contract's own required set means a clause added later is covered on arrival."""
        incomplete = {k: v for k, v in self._ROW.items() if k != clause}
        r = self._boot_at(tmp_path, [incomplete])
        assert r.returncode != 0, f"the service started with `{clause}` missing:\n{r.stdout}"
        assert "WillNotBoot" in r.stderr, r.stderr

    def test_AN_ABSENT_MANIFEST_IS_A_LEGITIMATE_EMPTY_STATE_NOT_A_REFUSAL(self, tmp_path):
        """🔴 **THE FAIL-SAFE DIRECTION, AND THE ONE THAT WOULD MAKE THE MEMBRANE UNSHIPPABLE.**
        `load()` reads an absent manifest as `declarations: []` — *no declarations* — which is
        today's state and the state CP-1 shipped. Refusing to boot on it would confuse *"nothing is
        declared"* with *"something is wrong"*, the two facts this effort keeps separating."""
        r = self._boot_at(tmp_path, None, write_manifest=False)
        assert r.returncode == 0, f"an empty membrane could not start:\n{r.stderr}"

    def test_THE_SERVICE_STARTUP_ACTUALLY_CALLS_IT(self):
        """🔴 **A GATE PRESENT IN THE TREE AND ABSENT FROM THE PATH IS THE RECURRING DEFECT** — it
        is why `agentruntime-membrane-gate` has its own CI-wiring guard, and why R21 found a census
        whose CI job could never pass. `boot()` that nothing calls is M4 still false, with a file."""
        src = (_REPO / "services" / "chat-service" / "app" / "main.py").read_text("utf-8")
        tree = ast.parse(src)
        lifespan = next(n for n in ast.walk(tree)
                        if isinstance(n, ast.AsyncFunctionDef) and n.name == "lifespan")
        calls = [n for n in ast.walk(lifespan)
                 if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "boot"]
        assert calls, "chat-service's lifespan does not call boot()"
        imports = [n for n in ast.walk(lifespan) if isinstance(n, ast.ImportFrom)
                   and (n.module or "").startswith("app.agentruntime")]
        assert imports, "the call is there but the import is not this package's"

    def test_BOOT_DOES_NOT_REIMPLEMENT_WHAT_VALIDITY_MEANS(self):
        """🔴 A second definition of *valid* is how `rows_of` and `load()` came to disagree about
        **nine shapes** while a docstring said they were one door. `boot()` adds a WHEN, not a
        WHAT: exactly one refusal of its own, and it is the boot failure."""
        src = (_PACKAGE / "boot.py").read_text("utf-8")
        raised = {n.exc.func.id for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call)
                  and isinstance(n.exc.func, ast.Name)}
        assert raised == {"WillNotBoot"}, (
            f"boot.py raises {raised}; a clause of its own is a second definition of validity"
        )


# ── 2.5 · P5 on every path, and the guardrail shadow arm ────────────────────────────────────────

class TestTheFourFieldsCannotBeSkipped:
    """REJECTS: a terminal path that ends a turn with a partial record.

    🔴 **P5 FAILED AS A RETROFIT FOR ELEVEN CONSECUTIVE ROUNDS.** Eight fixes, each correct at the
    layer it named and blind to the next; `finish_reason` covers 9.4% of turns today. So the
    property is not enforced here, it is made **inexpressible**: four required fields, no defaults,
    so a path that cannot answer one does not produce a partial `Observation` — it produces none.
    """

    def test_A_TURN_THAT_CANNOT_ANSWER_ALL_FOUR_FIELDS_PRODUCES_NO_RECORD_AT_ALL(self):
        for missing in ("advertised", "withheld", "source", "outcome"):
            kwargs = {"advertised": (), "withheld": (), "source": "tool", "outcome": "done"}
            kwargs.pop(missing)
            with pytest.raises(TypeError):
                Observation(**kwargs)                      # type: ignore[arg-type]

    def test_EVERY_PLAUSIBLE_DEFAULT_IS_A_CONSTANT_AT_A_WRITE_BOUNDARY(self):
        """🔴 The reason none of the four has a default is P4, not tidiness. `source="tool"`,
        `outcome="done"`, `advertised=()` are each a **constant written at every write** — the exact
        violation CP-1 repaired at eight asserted values, the last being `outcome_source='path'`
        written from a checkpoint no terminal path reaches."""
        import dataclasses

        required = {f.name for f in dataclasses.fields(Observation)
                    if f.default is dataclasses.MISSING
                    and f.default_factory is dataclasses.MISSING}
        assert required == {"advertised", "withheld", "source", "outcome"}

    def test_ADVERTISED_IS_PER_PASS__and_a_scalar_would_lose_the_mid_turn_change(self):
        """§5 field 1. **A scalar `text[]` records only the LAST pass**, and the mid-turn deletion
        is the thing the field exists to catch — arm E's silent deletion is invisible in production
        today precisely because no column answers *what did this turn advertise, and when*."""
        doc = _doc("a", "b", "c")
        asm = SurfaceAssembler(doc, log=NarrowingLog())
        first = asm.assemble(
            pass_number=1,
            pipeline=[DenyList(names=("b",), stage="token_budget", reason="over budget")])
        second = asm.assemble(pass_number=2)
        record = observe([first, second], source="tool", outcome="done")

        assert [e["pass"] for e in record.advertised] == [1, 2]
        assert record.advertised[0]["names"] == ("a", "c")
        assert record.advertised[1]["names"] == ("a", "b", "c")
        # The scalar view - what a `text[]` column would have held - cannot see the difference.
        assert record.advertised[-1]["names"] != record.advertised[0]["names"], (
            "the fixture does not actually change between passes, so this guard would pass over a "
            "scalar column too"
        )

    @pytest.mark.parametrize("entry", [
        {"pass": 1, "names": ()},                                   # missing `tool_choice`
        {"pass": 1, "tool_choice": "auto"},                          # missing `names`
        {"pass": 1, "tool_choice": "auto", "names": (), "extra": 1},  # a field nobody defined
        ({"pass": 1, "tool_choice": "auto", "names": ()},),           # not a dict at all
    ])
    def test_AN_ADVERTISED_ENTRY_IS_EXACTLY_THREE_KEYS(self, entry):
        """🔴 Found by the census, not by me: this refusal shipped with no guard at all.

        The closed shape is the same rule `ROW_FIELDS` enforces one module over — **a record
        carrying a field the contract never defined passed no clause**, and every consumer that
        reads it is reading something nobody decided."""
        with pytest.raises(NotObservable, match="advertised"):
            Observation(advertised=(entry,), withheld=(), source="tool", outcome="done")

    @pytest.mark.parametrize("bad", [0, -1, "1", True, 1.0, None])
    def test_A_PASS_NUMBER_IS_A_1_BASED_INT(self, bad):
        """Also census-found. `True` is in the list on purpose: `bool` is an `int` subclass, so
        `isinstance` would admit it and `type(p) is not int` does not — the one comparison Python
        does not dispatch, and the same argument that pinned `check_contract`."""
        with pytest.raises(NotObservable, match="pass"):
            Observation(
                advertised=({"pass": bad, "tool_choice": "auto", "names": ()},),
                withheld=(), source="tool", outcome="done")

    @pytest.mark.parametrize("bad", [["a"], {"a"}, "a", (n for n in ("a",))])
    def test_ADVERTISED_NAMES_IS_A_TUPLE_NOT_A_MUTABLE_OR_LAZY_CONTAINER(self, bad):
        """Census-found, and the third of three. A record that can change after it is written is
        not a record — and a **generator** is worse: it is empty the second time anyone reads it,
        so the first consumer sees the names and every later one sees none."""
        with pytest.raises(NotObservable, match="names"):
            Observation(
                advertised=({"pass": 1, "tool_choice": "auto", "names": bad},),
                withheld=(), source="tool", outcome="done")

    def test_TWO_ENTRIES_FOR_ONE_PASS_IS_REFUSED(self):
        """A duplicate makes *"what was advertised at pass 2"* answer two things, so every consumer
        reading the first silently disagrees with every consumer reading the last."""
        with pytest.raises(NotObservable, match="two entries for pass"):
            Observation(
                advertised=({"pass": 1, "tool_choice": "auto", "names": ("a",)},
                            {"pass": 1, "tool_choice": "auto", "names": ("b",)}),
                withheld=(), source="tool", outcome="done")

    @pytest.mark.parametrize("bad", ["wire", "TOOL", "", None, 1])
    def test_SOURCE_IS_ONE_OF_THREE_AND_NOT_A_FREE_STRING(self, bad):
        """58–66% of what the model sees as an error is our own prose; until `source` exists that
        fraction of the signal is uninterpretable."""
        with pytest.raises(NotObservable, match="source is"):
            Observation(advertised=(), withheld=(), source=bad, outcome="done")

    @pytest.mark.parametrize("bad", ["ok", True, "success", "DONE"])
    def test_OUTCOME_IS_C14s_TYPED_ENUM_NOT_OK_BOOL(self, bad):
        """`ok=true` is untyped and meant seven different things: **358 refusals rode the success
        channel**, 400 empty results had four indistinguishable causes."""
        with pytest.raises(NotObservable, match="outcome is"):
            Observation(advertised=(), withheld=(), source="tool", outcome=bad)

    def test_THE_RECORD_IS_DERIVED_FROM_THE_SURFACES_NOT_HAND_TYPED(self):
        """Every denominator a person maintained in this run turned out to be a lower bound. A pass
        that happened and was not recorded must be **inexpressible**, not discouraged."""
        doc = _doc("a", "b")
        asm = SurfaceAssembler(doc, log=NarrowingLog())
        surfaces = [
            asm.assemble(pass_number=1,
                         pipeline=[DenyList(names=("b",), stage="s", reason="r")]),
            asm.assemble(pass_number=2),
        ]
        record = observe(surfaces, source="tool", outcome="partial")
        assert len(record.advertised) == len(surfaces)
        assert [w["tool"] for w in record.withheld] == ["b"]

    def test_THE_WRONG_OBJECT_COUNTER_IS_NOT_A_P5_FIELD(self):
        """§0.6: **a counter without a detector ships reading zero.** Only substitution-shaped cases
        are detectable at the call; the 61.8% carry-forward class is detectable only from
        plan-binding state, so its detector belongs with the plan and P5 carries the output."""
        import dataclasses

        names = {f.name for f in dataclasses.fields(Observation)}
        assert not any("wrong" in n or "object_count" in n for n in names), (
            f"a wrong-object counter was added to P5: {names}"
        )
        assert "manifest_revision" not in names, (
            "hashing an empty manifest is a constant-valued column at every write - the P4 "
            "violation CP-1 repaired (CP-1.8)"
        )


class TestTheGuardrailIsAShadowArmStructurally:
    """REJECTS: a v1 guardrail that acts.

    🔴 **PROPERTY 3 IS UNOBSERVABLE ONCE THE GUARDRAIL BLOCKS.** The property is *a strong model
    reaches the transition before the guardrail fires*, measurable only as **fire-rate falling
    toward zero as model strength rises**. A guardrail that acts destroys its own denominator: the
    turns where the model would have recovered never happen. *If it does not fall, we built a
    ceiling and mislabelled it* — and that sentence cannot be tested once the ceiling is in place.

    **Un-retrofittable**: the data for a v2 decision only exists if v1 does not act.
    """

    def test_A_GUARDRAIL_THAT_ACTED_CANNOT_BE_CONSTRUCTED(self):
        with pytest.raises(NotObservable, match="SHADOW ARM"):
            Guardrail(fired=True, evidence="the same call 3 times", transition="step 2 -> blocked",
                      acted=True)

    def test_THE_DEFAULT_IS_NOT_ACTING__not_a_flag_someone_must_remember(self):
        assert Guardrail(False, "", "").acted is False

    def test_A_FIRE_WITHOUT_DETERMINISTIC_EVIDENCE_IS_REFUSED(self):
        """§0.5 property 1: it fires on an identical call repeated or a budget spent — **never on a
        judgement about whether the model seems confused.** A guardrail that fires on a judgement is
        the sixth breaker with a new name."""
        with pytest.raises(NotObservable, match="DETERMINISTIC"):
            Guardrail(fired=True, evidence="   ", transition="step 2 -> blocked")

    def test_A_FIRE_WITH_NO_TRANSITION_IS_A_STOP_AND_IS_REFUSED(self):
        """§0.5: *a guardrail's output must be a PLAN STATE TRANSITION, not a stop.* Today's six
        breakers are **65.7% of everything the model sees as an error** — the archetypal ceiling."""
        with pytest.raises(NotObservable, match="TRANSITION"):
            Guardrail(fired=True, evidence="budget spent", transition="")

    def test_A_GUARDRAIL_THAT_DID_NOT_FIRE_NEEDS_NEITHER(self):
        """The bounds apply to a FIRE. Requiring evidence for a non-event would force every quiet
        turn to invent one, which is the fabrication these checks exist to prevent."""
        assert observe([], source="tool", outcome="done").guardrail.fired is False


# ── 2.4 · withheld is reachable, and DISTINGUISHABLE from never-existed ─────────────────────────

class TestTheModelCanTellWithheldFromNeverExisted:
    """REJECTS: an empty-looking surface the model reads as an empty world.

    🔴 **THE ROW WAS HONEST AND THE SCREEN WAS NOT.** V-LIVE watched the model state that
    `book_list` *"does not exist at all"* while the same turn's row recorded it as withheld with a
    stage and a reason. Correct telemetry does not prevent that: the record is read by us,
    afterwards.

    Reachability alone does not prevent it either, which is why this is a separate item from 2.1.
    A model that has already concluded a tool does not exist **has no reason to search for it.**
    """

    def test_A_WITHHELD_DECLARATION_AND_A_NEVER_ADMITTED_ONE_END_DIFFERENTLY(self):
        """🔴 **THE MEASUREMENT, AND IT IS A PAIR.** One name is admitted and withheld; the other
        was never admitted at all. The model searches for each. If the two searches came back the
        same, *"withheld"* and *"never existed"* would be one state as far as the model is
        concerned, and every guard in this class would be about our bookkeeping rather than about
        what the model can know."""
        doc = _doc("book_list", "glossary_search")
        surface = _split(doc, ("glossary_search",))
        toolset = toolset_for(doc, surface, executor=_executor)

        found: dict[str, list[str]] = {}

        def drive(query: str) -> list[str]:
            turns: list[list[str]] = []

            def model_fn(messages, info: AgentInfo):
                turns.append(sorted(t.name for t in info.function_tools))
                if len(turns) == 1:
                    return ModelResponse(
                        parts=[ToolCallPart("search_tools", {"queries": [query]})])
                return ModelResponse(parts=[TextPart("done")])

            agent = Agent(FunctionModel(model_fn), toolsets=[toolset],
                          capabilities=[ToolSearch()])
            asyncio.run(agent.run(f"find {query}"))
            return turns[-1]

        found["withheld"] = drive("glossary")
        found["never"] = drive("wormhole")

        assert "glossary_search" in found["withheld"], (
            "the withheld declaration was not revealed by a search that names it"
        )
        assert "glossary_search" not in found["never"], "the search harness reveals unconditionally"
        assert found["withheld"] != found["never"], (
            "a withheld declaration and one that never existed produced the SAME observable "
            "outcome - then the model cannot tell them apart and §0.14.3's failure is live"
        )

    def test_THE_MODEL_IS_TOLD_UNPROMPTED_THAT_SOMETHING_WAS_WITHHELD(self):
        """Reachable is not enough: the notice is what stops the model concluding *"no tool
        provides this"* before it ever searches."""
        doc = _doc("a", "b", "c")
        notice = withholding_notice(_split(doc, ("b", "c")))
        assert notice is not None and "2 declarations" in notice
        assert "reachable" in notice and "search" in notice

    def test_THE_NOTICE_COUNTS_AND_DOES_NOT_NAME(self):
        """🔴 **NAMING THEM PUTS BACK ON THE WIRE EXACTLY WHAT THE NARROWING REMOVED**, so a budget
        stage that cut five declarations would pay most of its own saving back and the withholding
        would be theatre. The names are in the record, which is where a person reads them."""
        doc = _doc("glossary_search", "kg_build", "book_list")
        notice = withholding_notice(_split(doc, ("glossary_search", "kg_build")))
        assert notice is not None
        for name in ("glossary_search", "kg_build"):
            assert name not in notice, f"the notice leaked {name} back onto the wire"

    def test_NOTHING_WITHHELD_MEANS_NO_NOTICE_AT_ALL__not_a_notice_saying_zero(self):
        """A notice on every turn is noise the model learns to skip, and **absent and zero are
        different facts** — the same distinction §0.14.3 draws for `count`."""
        doc = _doc("a", "b")
        assert withholding_notice(_split(doc, ())) is None

    def test_THE_NOTICE_SAYS_THEY_EXIST__it_is_the_sentence_the_model_got_wrong(self):
        """The observed fabrication was *"does not exist at all"*. A notice that hedges — *"some
        tools may not be available"* — is compatible with that reading and would not close it."""
        doc = _doc("a", "b")
        notice = withholding_notice(_split(doc, ("b",)))
        assert "exist" in notice and "not deleted" in notice
        assert "1 declaration " in notice, "the singular case reads as a plural"


# ── 2.3 · deterministic tool ordering ───────────────────────────────────────────────────────────

_ORDER_PROBE = """
import sys
sys.path.insert(0, {cs!r})
from app.agentruntime import SurfaceAssembler, NarrowingLog, OrderBy
def row(i, svc):
    return {{"id": i, "kind": "tool", "owning_service": svc, "lifecycle": "admitted",
             "contract_version": "1.0.0", "admitted_against": "1.0.0", "members": []}}
doc = {{"manifest_version": 1, "contract_version": "1.0.0",
        "declarations": [row("a", "z"), row("b", "y"), row("c", "x")]}}
s = SurfaceAssembler(doc, log=NarrowingLog()).assemble(
    pass_number=1, pipeline={pipeline})
print(",".join(s.names))
"""

#: 🔴 THE CONTROL FOR THE GUARD BELOW. It is the legacy shape in miniature — `active_tool_names` is
#: a `set[str]` iterated unsorted (`stream_service.py:1383`), and `PYTHONHASHSEED` is exactly what
#: makes that vary between restarts. If this does NOT disagree across seeds then the harness cannot
#: detect non-determinism at all, and the guard beside it is measuring nothing.
_SET_PROBE = """
print(",".join({"glossary_search", "book_list", "kg_build", "entity_triage", "plan_compile"}))
"""


def _across_hash_seeds(source: str, seeds=("0", "1", "12345", "99991")) -> set[str]:
    import os
    outs = set()
    for seed in seeds:
        env = {**os.environ, "PYTHONHASHSEED": seed}
        r = subprocess.run([sys.executable, "-c", source], capture_output=True, text=True, env=env)
        assert r.returncode == 0, f"probe failed under PYTHONHASHSEED={seed}:\n{r.stderr}"
        outs.add(r.stdout.strip())
    return outs


class TestTheOrderIsTheRanksAndItIsDeterministic:
    """REJECTS: an advertised order that changes between restarts, or that discards the rank.

    The legacy defect is one line — `active_tool_names` is a `set[str]` iterated unsorted, so the
    advertised order changes on every restart, **and `tools` is the first prompt-cache block.** The
    new runtime had the mirror-image defect: it was deterministic and threw the rank away.
    """

    _CS = str(_REPO / "services" / "chat-service")

    def test_THE_SURFACE_IS_IN_THE_PIPELINES_ORDER_NOT_ALPHABETICAL(self):
        """🔴 Measured before the fix: rows ranked `c, b, a` were reported `a, b, c`. `order_by`
        decided which declarations survive and had no say in what the model sees first."""
        doc = {
            "manifest_version": 1, "contract_version": "1.0.0",
            "declarations": [
                {**_row("a"), "owning_service": "z-svc"},
                {**_row("b"), "owning_service": "y-svc"},
                {**_row("c"), "owning_service": "x-svc"},
            ],
        }
        surface = SurfaceAssembler(doc, log=NarrowingLog()).assemble(
            pass_number=1, pipeline=[OrderBy(keys=(("owning_service", "asc"),))])
        assert surface.names == ("c", "b", "a"), (
            "the surface re-sorted alphabetically and discarded the rank the pipeline computed"
        )

    def test_A_RANK_DEPENDENT_CUT_PRESENTS_ITS_SURVIVORS_IN_RANK_ORDER(self):
        """Selection was already correct; presentation was not. Both are checked, because a guard
        on the survivor SET is green over a surface that presents them backwards."""
        doc = {
            "manifest_version": 1, "contract_version": "1.0.0",
            "declarations": [
                {**_row("a"), "owning_service": "z-svc"},
                {**_row("b"), "owning_service": "y-svc"},
                {**_row("c"), "owning_service": "x-svc"},
            ],
        }
        surface = SurfaceAssembler(doc, log=NarrowingLog()).assemble(
            pass_number=1,
            pipeline=[OrderBy(keys=(("owning_service", "asc"),)),
                      TopK(k=2, stage="top_k", reason="over rank")])
        assert set(surface.names) == {"c", "b"}, "the wrong two survived"
        assert surface.names == ("c", "b"), "the right two survived, in the wrong order"

    def test_WITH_NO_ORDER_BY_THE_ORDER_IS_THE_MANIFESTS_OWN(self):
        """The no-ranking case must stay stable, and it does so because the DOCUMENT is ordered —
        not because this function sorts. That is the whole difference from the previous code."""
        doc = _doc("c", "a", "b")
        surface = SurfaceAssembler(doc, log=NarrowingLog()).assemble(pass_number=1)
        assert surface.names == ("c", "a", "b")

    def test_THE_MANIFEST_IS_WRITTEN_IN_A_CANONICAL_ORDER__which_is_what_makes_that_stable(self):
        """🔴 The guard above is only worth something if the document's order is itself stable
        across regenerations. `build()` writes `sorted(rows, key=id)`; without that clause the
        previous test would be asserting that a churning order is preserved faithfully."""
        rows = [_row(n) for n in ("c", "a", "b")]
        doc = build(tuple(admit(Declaration(
            id=r["id"], kind="tool", source_path="services/book-service/x.py",
            lifecycle="admitted")) for r in rows))
        assert [r["id"] for r in doc["declarations"]] == ["a", "b", "c"]

    def test_THE_ORDER_IS_IDENTICAL_IN_A_FRESH_INTERPRETER_UNDER_FOUR_HASH_SEEDS(self):
        """🔴 **THE DEFECT THIS ITEM IS NAMED FOR, MEASURED THE ONLY WAY IT CAN BE.**

        *"The order changes on every restart"* is not observable inside one process — the legacy
        `set[str]` iterates consistently for the life of an interpreter and differently in the next
        one, because `PYTHONHASHSEED` is randomised per process. So this runs the real assembly in
        four fresh interpreters under four seeds and requires one answer.
        """
        src = _ORDER_PROBE.format(
            cs=self._CS, pipeline='[OrderBy(keys=(("owning_service", "asc"),))]')
        assert _across_hash_seeds(src) == {"c,b,a"}

    def test_THE_HASH_SEED_HARNESS_CAN_ACTUALLY_DETECT_NON_DETERMINISM(self):
        """🔴 **A CHECK WHOSE CONTROL AGREES WITH ITS SEED IS THEATRE**, and this run has shipped
        two of those. The guard above passes trivially if the subprocesses never differ for any
        reason — a fixed seed leaking in, an env var ignored, output buffered away. So the legacy
        shape is run through the same harness and is required to **DISAGREE**."""
        assert len(_across_hash_seeds(_SET_PROBE)) > 1, (
            "a bare `set` of strings produced one order across four hash seeds - the harness "
            "cannot see non-determinism, so the guard above is measuring nothing"
        )

    def test_THE_TOOLSET_PRESENTS_THE_SURFACE_IN_THAT_ORDER(self):
        """End to end: rank has to survive the trip through CP-2.1's assembly, or it holds in a
        tuple and not on the wire."""
        doc = {
            "manifest_version": 1, "contract_version": "1.0.0",
            "declarations": [
                {**_row("a"), "owning_service": "z-svc"},
                {**_row("b"), "owning_service": "y-svc"},
                {**_row("c"), "owning_service": "x-svc"},
            ],
        }
        surface = SurfaceAssembler(doc, log=NarrowingLog()).assemble(
            pass_number=1, pipeline=[OrderBy(keys=(("owning_service", "asc"),))])
        defs = _defs(toolset_for(doc, surface, executor=_executor))
        assert advertised_names(defs) == ("c", "b", "a")


# ── the gate, and the coupling it now admits ────────────────────────────────────────────────────

def _gate():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "membrane_gate", _REPO / "scripts" / "agentruntime-membrane-gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                # type: ignore[union-attr]
    return mod


class TestTheCeilingApiIsUnreachableInThePackage:
    """REJECTS: a ceiling API arriving in the package later, when the item is no longer in view.

    A behavioural test cannot establish this - it shows the path was not taken on the inputs it
    tried. The same argument as M2, one layer up, and the same instrument.
    """

    def test_NO_CEILING_CALL_EXISTS_IN_THE_PACKAGE(self):
        offenders = []
        for path in sorted(_PACKAGE.rglob("*.py")):
            tree = ast.parse(path.read_text("utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in _gate().CEILING_METHODS:
                        offenders.append(f"{path.name}:{node.lineno} .{node.func.attr}()")
        assert offenders == [], f"a ceiling api is live in the membrane: {offenders}"

    @pytest.mark.parametrize("src", [
        "def f(t, g):\n    return t.filtered(g)\n",
        "def f(t, g):\n    return t.prepared(g)\n",
    ])
    def test_THE_GATE_FIRES_ON_A_CEILING_CALL(self, tmp_path, src):
        p = tmp_path / "assembly.py"
        p.write_text(src, encoding="utf-8")
        assert _gate()._violations_in(p), f"the gate did not fire on:\n{src}"

    def test_THE_GATE_IS_SILENT_ON_THE_DEFERRING_CALL(self, tmp_path):
        p = tmp_path / "assembly.py"
        p.write_text("def f(t, n):\n    return t.defer_loading(n)\n", encoding="utf-8")
        assert not _gate()._violations_in(p)


class TestTheBoughtDependencyIsDeclaredAndScoped:
    """REJECTS: the undeclared-direct-import class this repo's own requirements file records, and
    a scoped allowance that has quietly become package-wide."""

    def test_THE_DEPENDENCY_IS_DECLARED_BY_THE_SERVICE_THAT_IMPORTS_IT(self):
        req = (_REPO / "services" / "chat-service" / "requirements.txt").read_text("utf-8")
        assert "pydantic-ai-slim" in req, (
            "assembly.py does a top-level `from pydantic_ai...` - resolving transitively is the "
            "exact class that once crashed every service on startup"
        )

    def test_THE_ALLOWANCE_IS_SCOPED_TO_THE_ONE_FILE_THAT_NEEDS_IT(self, tmp_path):
        g = _gate()
        assert g.ALLOWED_EXTERNAL_SCOPE["pydantic_ai"] == frozenset({"assembly.py"})
        p = tmp_path / "surface.py"
        p.write_text("from pydantic_ai.tools import ToolDefinition\n", encoding="utf-8")
        assert g._violations_in(p), "the scoped allowance leaked to a second package file"

    def test_ASSEMBLY_IS_THE_ONLY_FILE_IN_THE_PACKAGE_THAT_IMPORTS_IT(self):
        importers = []
        for path in sorted(_PACKAGE.rglob("*.py")):
            tree = ast.parse(path.read_text("utf-8"))
            for node in ast.walk(tree):
                mods = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                        else [a.name for a in node.names] if isinstance(node, ast.Import) else [])
                if any(m.split(".", 1)[0] == "pydantic_ai" for m in mods):
                    importers.append(path.name)
        assert sorted(set(importers)) == ["assembly.py"]

    def test_THE_PACKAGE_STILL_IMPORTS_AT_THE_CONTAINERS_DEPTH(self, tmp_path):
        """🔴 The deployed-layout regression, re-run because CP-2.1 changed what the package pulls.

        `import app.agentruntime` once raised `IndexError` in the running container and no test
        could see it. The property that made it testable was that everything resolved from the
        interpreter rather than the tree - adding a third-party import is exactly the change that
        could quietly end that, so it is re-measured here rather than assumed to carry over.
        """
        import shutil
        pkg = tmp_path / "app" / "agentruntime"
        pkg.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(_PACKAGE, pkg)
        (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, "-c", "import app.agentruntime as m; print(m.TOOLSET_ID)"],
            cwd=tmp_path, capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr


class TestTheModuleDeclaresItsOwnLimits:
    """REJECTS: a residual that stopped being written down once it stopped being new.

    Three things are true and unflattering about this module, and each is named in its docstring.
    A docstring is not a mechanism - but a *missing* one is how a named residual becomes a
    forgotten one, and this run has watched a claim survive four rounds in three files.
    """

    @pytest.mark.parametrize("phrase", [
        "discoverable **by name tokens only**",      # no description field exists yet
        "It does not make the package pure",         # transitive imports are not gated
        "It does not route a turn",                  # CP-2.7 owns the route
    ])
    def test_THE_NAMED_RESIDUAL_IS_STILL_NAMED(self, phrase):
        assert phrase in (_assembly.__doc__ or "")
