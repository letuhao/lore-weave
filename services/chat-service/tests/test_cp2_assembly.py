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
    DeclarationToolset,
    DenyList,
    admit,
    build,
    NarrowingLog,
    OrderBy,
    RequirementNotAdmitted,
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
