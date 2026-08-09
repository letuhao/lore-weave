"""CP-3 — the plan. **The architecture's central claim**, and the checkpoint most likely to fail.

Every guard here is about the same sentence: *the conversation is a lossy carrier and the runtime was
relying on it to hold identifiers.* 61.8% of failures are on a declaration that already succeeded.
"""
from __future__ import annotations

from types import MappingProxyType as M

import pytest

from app.agentruntime.plan import (
    RECOVERY_SCOPES,
    Binding,
    BindingError,
    Event,
    PlanError,
    Spec,
    State,
    Step,
    Termination,
    preflight_gates,
    re_runnable,
    resolve_arguments,
    terminate,
)
from app.agentruntime.planparse import PlanParseError, parse
from app.agentruntime.planproject import project

UUID = "019fafa2-dead-beef-0000-000000000001"


def _pair(gated: bool = False) -> Spec:
    """The two-step shape brick 4 names: step 2 consumes step 1's `emits` (C-6)."""
    return Spec(goal="read a book", steps=(
        Step(declaration="book_list", contract_version="1.0.0", emits=("book_id",)),
        Step(declaration="book_read", contract_version="1.0.0",
             accepts=M({"book_id": Binding(from_step=0, from_emit="book_id")}), gated=gated),
    ))


class TestTheCarryForwardIsBoundNotRetyped:
    """3.4 — the one part of this design with no prior art in any surveyed system."""

    def test_THE_EXECUTOR_SUPPLIES_THE_IDENTIFIER_THE_MODEL_ALREADY_SAW(self):
        spec = _pair()
        st = State(spec.hashed())
        st.append(Event(kind="step_emitted", step_index=0, values=M({"book_id": UUID})))
        assert resolve_arguments(spec, st, 1) == {"book_id": UUID}

    def test_A_MISSING_VALUE_IS_A_REFUSAL_NOT_A_FALLBACK_TO_ASKING_THE_MODEL(self):
        """🔴 The whole mechanism, stated as the thing it must NOT do.

        Degrading to *"let the model supply it"* would reintroduce the exact failure — silently, and
        only under the conditions where the carrier had already failed. `"0"` instead of
        `entity_id:019fafa2-…` is what that looks like in production.
        """
        spec = _pair()
        st = State(spec.hashed())
        with pytest.raises(BindingError) as exc:
            resolve_arguments(spec, st, 1)
        assert exc.value.step_index == 1 and exc.value.param == "book_id"
        assert "not requested from the model" in str(exc.value).lower()

    def test_A_BINDING_NOBODY_EMITS_IS_A_GENERATION_ERROR_NOT_A_RUNTIME_ONE(self):
        """§6.2 — checked when the plan is BUILT, so the failure is unreachable at execution. The
        same inversion M5 makes for manifest members: a reference checked when it is used has a
        failure mode of *allow*."""
        with pytest.raises(BindingError) as exc:
            Spec(goal="g", steps=(
                Step(declaration="a", contract_version="1.0.0", emits=("x",)),
                Step(declaration="b", contract_version="1.0.0",
                     accepts=M({"p": Binding(from_step=0, from_emit="nope")})),
            ))
        assert "does not declare it" in str(exc.value)
        assert "['x']" in str(exc.value), "the rejection must name what WOULD be accepted (C-12)"

    def test_A_BINDING_TO_A_LATER_STEP_IS_A_CYCLE_AND_IS_REFUSED(self):
        with pytest.raises(BindingError, match="does not run before"):
            Spec(goal="g", steps=(
                Step(declaration="a", contract_version="1.0.0",
                     accepts=M({"p": Binding(from_step=1, from_emit="x")})),
                Step(declaration="b", contract_version="1.0.0", emits=("x",)),
            ))

    def test_A_BINDING_IS_A_REFERENCE_OR_A_LITERAL_AND_NEVER_BOTH(self):
        """The shape says which, so the executor never guesses. A `{{step2.entity_id}}` in a value
        field is indistinguishable from text a user typed."""
        with pytest.raises(PlanError, match="two sources"):
            Binding(from_step=0, from_emit="x", literal="also this")
        with pytest.raises(PlanError, match="neither one thing nor the other"):
            Binding(from_step=None, from_emit="x")


class TestTheApprovalBindsToTheGatedStepsOnly:
    """3.7 · §0.8's permission-laundering fix, which works only because SPEC and STATE are split."""

    def test_AN_UNGATED_EDIT_DOES_NOT_INVALIDATE_AN_APPROVAL(self):
        """🔴 The half that is easy to get wrong in the SAFE-LOOKING direction.

        Hashing the whole spec would invalidate an approval whenever any step changed, including a
        prose edit to an ungated one. That sounds conservative and is the actual failure: it trains
        a user to re-approve reflexively, which is how assent stops meaning anything.
        """
        before = _pair(gated=True)
        after = Spec(goal="read a book", steps=(
            Step(declaration="book_list", contract_version="1.0.0", emits=("book_id",),
                 done_when="a book id came back"),          # ungated step edited
            before.steps[1],
        ))
        assert after.gated_hash() == before.gated_hash()
        assert after.hashed() != before.hashed(), (
            "the whole-spec hash must still move, or the two hashes are one thing wearing two names"
        )

    def test_A_GATED_EDIT_DOES_INVALIDATE_IT(self):
        before = _pair(gated=True)
        after = Spec(goal="read a book", steps=(
            before.steps[0],
            Step(declaration="book_purge", contract_version="1.0.0",
                 accepts=M({"book_id": Binding(from_step=0, from_emit="book_id")}), gated=True),
        ))
        assert after.gated_hash() != before.gated_hash()

    def test_REORDERING_GATED_STEPS_INVALIDATES_IT_BECAUSE_POSITION_IS_MEANING(self):
        """*"Approve step 3"* is about which call runs third. A hash over the gated steps as a SET
        would let two approved operations swap places under an unchanged approval."""
        a = Spec(goal="g", steps=(
            Step(declaration="x_one", contract_version="1.0.0", gated=True),
            Step(declaration="x_two", contract_version="1.0.0", gated=True),
        ))
        b = Spec(goal="g", steps=(
            Step(declaration="x_two", contract_version="1.0.0", gated=True),
            Step(declaration="x_one", contract_version="1.0.0", gated=True),
        ))
        assert a.gated_hash() != b.gated_hash()

    def test_INSERTING_AN_UNGATED_STEP_BEFORE_A_GATED_ONE_INVALIDATES_IT(self):
        """The index is in the payload, so a gated step that moves from position 1 to position 2 is
        a different thing to approve even though its own fields are untouched."""
        before = _pair(gated=True)
        after = Spec(goal="read a book", steps=(
            before.steps[0],
            Step(declaration="book_search", contract_version="1.0.0"),
            Step(declaration="book_read", contract_version="1.0.0",
                 accepts=M({"book_id": Binding(from_step=0, from_emit="book_id")}), gated=True),
        ))
        assert after.gated_hash() != before.gated_hash()

    def test_THE_PREFLIGHT_NAMES_EVERY_GATED_STEP_AT_PLAN_TIME(self):
        assert preflight_gates(_pair(gated=True)) == (1,)
        assert preflight_gates(_pair(gated=False)) == ()


class TestStateIsEventSourcedAndAppendOnly:
    """3.1 — replay reconstructs; nothing is mutated."""

    def test_A_HISTORY_CANNOT_BE_SUPPLIED_AT_CONSTRUCTION(self):
        """🔴 What keeps *"one writer during execution"* true. A manufactured past could include an
        `effect_committed` for something that never ran — which is precisely what §0.5 feeds to a
        replan."""
        import inspect

        assert set(inspect.signature(State.__init__).parameters) == {"self", "spec_hash"}, (
            "State takes something other than a spec hash; a caller that can hand in events can "
            "manufacture a past, and the replan reads that past as fact"
        )

    def test_REPLAY_RECONSTRUCTS_THE_SAME_STATE(self):
        spec = _pair()
        st = State(spec.hashed())
        st.append(Event(kind="step_started", step_index=0))
        st.append(Event(kind="step_emitted", step_index=0, values=M({"book_id": UUID})))
        again = State.replay(spec.hashed(), st.events)
        assert again.emitted() == st.emitted()
        assert again.status_of(0) == "done"

    def test_A_RETRIED_STEPS_SECOND_EMISSION_IS_THE_CURRENT_TRUTH(self):
        """§0.5's `retry_step` depends on this rather than on the first write sticking."""
        spec = _pair()
        st = State(spec.hashed())
        st.append(Event(kind="step_emitted", step_index=0, values=M({"book_id": "old"})))
        st.append(Event(kind="step_emitted", step_index=0, values=M({"book_id": UUID})))
        assert resolve_arguments(spec, st, 1) == {"book_id": UUID}

    def test_A_STEP_EMITTED_EVENT_CARRYING_NOTHING_IS_REFUSED(self):
        """It would say a step completed while destroying the only thing a later step can bind to."""
        with pytest.raises(PlanError, match="no values"):
            Event(kind="step_emitted", step_index=0)

    def test_A_FAILURE_NOBODY_CLASSIFIED_IS_REFUSED(self):
        """C-7 classifies where the failure is raised; recovery cannot act on an absent class."""
        with pytest.raises(PlanError, match="no error_class"):
            Event(kind="step_failed", step_index=0)

    def test_THE_EVENT_LIST_CANNOT_BE_MUTATED_THROUGH_THE_ACCESSOR(self):
        st = State("h")
        st.events  # noqa: B018 - the accessor is the subject
        assert isinstance(st.events, tuple)
        with pytest.raises(PlanError, match="not an Event"):
            st.append({"kind": "step_started", "step_index": 0})


class TestTheFourSilentExitsCloseAsOneMechanism:
    """3.6 — *a plan that ends anywhere but `done_when` names what is live and hands it to a human.*"""

    def test_AN_END_THAT_IS_NOT_DONE_WHEN_MUST_NAME_SOMEONE(self):
        """Exits #2 and #4 became silent precisely because a STATUS was recorded and no action was
        named. `sweep_expired_runs` has zero callers; a cancel was badged `interrupted`."""
        st = State("h")
        with pytest.raises(PlanError, match="names nobody"):
            terminate(st, "escalate_to_human", 1)

    def test_LIVE_EFFECTS_IS_REQUIRED_AND_EMPTY_IS_A_REAL_ANSWER(self):
        """🔴 Exit #1 is *nobody looked* being mistaken for *nothing is outstanding*."""
        with pytest.raises(PlanError, match="tuple"):
            Termination(scope="done_when", step_index=0, live_effects=None, hand_to_human="")
        ok = Termination(scope="done_when", step_index=0, live_effects=(), hand_to_human="")
        assert ok.live_effects == ()

    def test_THE_LEDGER_IS_READ_OUT_OF_STATE_NOT_TAKEN_ON_TRUST(self):
        """This is why STATE is event-sourced: a snapshot would have to be kept correct by whoever
        wrote it, which is silent exit #1 with an extra step."""
        spec = _pair()
        st = State(spec.hashed())
        st.append(Event(kind="effect_committed", step_index=0,
                        undo_hint="book_delete(book_id)", committed=True))
        st.append(Event(kind="effect_committed", step_index=1, undo_hint="n/a", committed=False))
        t = terminate(st, "escalate_to_human", 1, hand_to_human="a book was created; confirm or undo")
        assert [e.step_index for e in t.live_effects] == [0], (
            "an effect that did not commit is not live, and one that did must not be dropped"
        )

    def test_ABANDONED_BY_USER_IS_A_SCOPE_OF_ITS_OWN(self):
        """§0.5 called badging a cancel `interrupted` a defect, and said so because it makes the
        section's own baseline metric uninterpretable."""
        assert "abandoned_by_user" in RECOVERY_SCOPES
        t = terminate(State("h"), "abandoned_by_user", 0, hand_to_human="user stopped the plan")
        assert t.error_class is None, "a cancellation is not a failure and carries no error class"


class TestRecoveryAsksBeforeItReRuns:
    """3.5 · C-13 — `re_runnable` BEFORE any automatic re-run, never after."""

    def test_A_STEP_THAT_COMMITTED_AN_EFFECT_IS_NOT_AUTO_RE_RUNNABLE(self):
        spec = _pair()
        st = State(spec.hashed())
        assert re_runnable(spec, st, 0) is True
        st.append(Event(kind="effect_committed", step_index=0,
                        undo_hint="book_delete(book_id)", committed=True))
        assert re_runnable(spec, st, 0) is False, (
            "the second run would duplicate whatever the first did, and the ledger is the only "
            "record it happened at all"
        )

    def test_A_STEP_INDEX_OUTSIDE_THE_PLAN_IS_REFUSED(self):
        """`re_runnable` answers *may the runtime re-run this?*, and a `False` for an index that is
        not in the plan would be a *no* to a question nobody asked — which reads as a considered
        refusal. An out-of-range index is a caller defect and says so."""
        spec = _pair()
        st = State(spec.hashed())
        with pytest.raises(PlanError, match="not in a plan"):
            re_runnable(spec, st, 5)
        with pytest.raises(PlanError, match="not in a plan"):
            re_runnable(spec, st, -1)

    def test_AN_UNCOMMITTED_EFFECT_DOES_NOT_BLOCK_A_RETRY(self):
        spec = _pair()
        st = State(spec.hashed())
        st.append(Event(kind="effect_committed", step_index=0, undo_hint="x", committed=False))
        assert re_runnable(spec, st, 0) is True


class TestEveryRefusalInThePlanModuleIsChecked:
    """🔴 **THE CENSUS FOUND 22 UNGUARDED REFUSAL SITES IN THIS CHANGE AND I FIRST READ ONLY 5.**

    I ran the gate through `| tail -6`, so its own output was truncated and I reasoned from the
    remainder — the exact failure class this instrument exists to catch, committed against the
    instrument. The full list came from the verdict JSON.

    Every constructor below rejects a shape that a plan author, a template or a model can produce,
    and each one is the last thing standing between that shape and a SPEC hash somebody approves.
    """

    def test_A_BINDING_WITH_A_NEGATIVE_OR_NON_INT_STEP_IS_REFUSED(self):
        with pytest.raises(PlanError, match="non-negative step index"):
            Binding(from_step=-1, from_emit="x")
        with pytest.raises(PlanError, match="non-negative step index"):
            Binding(from_step="0", from_emit="x")

    def test_A_REFERENCE_WITHOUT_A_NAME_IS_REFUSED(self):
        """Binding to a STEP rather than to a value is how a carry-forward silently picks whichever
        field happened to be first."""
        with pytest.raises(PlanError, match="needs the NAME"):
            Binding(from_step=0, from_emit="")

    def test_AN_UNKNOWN_EVENT_KIND_IS_REFUSED(self):
        with pytest.raises(PlanError, match="unknown event kind"):
            Event(kind="step_finished", step_index=0)

    def test_AN_EVENT_WITH_A_BAD_STEP_INDEX_IS_REFUSED(self):
        with pytest.raises(PlanError, match="non-negative index"):
            Event(kind="step_started", step_index=-1)

    def test_A_SPEC_VERSION_MUST_BE_A_POSITIVE_INTEGER(self):
        """A revision is a NEW version; version 0 or a string would make *which spec is current* a
        comparison nobody defined."""
        with pytest.raises(PlanError, match="positive integer"):
            Spec(goal="g", steps=(Step(declaration="a", contract_version="1.0.0"),), version=0)

    def test_A_NEGATIVE_REPLAN_BUDGET_IS_REFUSED(self):
        with pytest.raises(PlanError, match="non-negative int"):
            Spec(goal="g", steps=(Step(declaration="a", contract_version="1.0.0"),),
                 replan_budget=-1)

    def test_STATE_WITHOUT_A_SPEC_HASH_DESCRIBES_NO_PLAN(self):
        with pytest.raises(PlanError, match="bound to a SPEC hash"):
            State("")

    def test_A_STEP_WITHOUT_A_DECLARATION_IS_REFUSED(self):
        with pytest.raises(PlanError, match="expected a manifest id"):
            Step(declaration="", contract_version="1.0.0")

    def test_A_STEP_EMITTING_AN_EMPTY_NAME_IS_REFUSED(self):
        with pytest.raises(PlanError, match="non-empty names"):
            Step(declaration="a", contract_version="1.0.0", emits=("",))

    def test_A_STEP_EMITTING_A_DUPLICATE_NAME_IS_REFUSED(self):
        """A later step binding to it could not say which one it meant."""
        with pytest.raises(PlanError, match="duplicate name"):
            Step(declaration="a", contract_version="1.0.0", emits=("x", "x"))

    def test_AN_UNKNOWN_TERMINATION_SCOPE_IS_REFUSED(self):
        with pytest.raises(PlanError, match="unknown termination scope"):
            Termination(scope="gave_up", step_index=0, live_effects=(), hand_to_human="x")

    def test_A_PLAIN_VALUE_IN_ACCEPTS_IS_NOT_A_BINDING(self):
        """A bare value would be a literal nobody declared — and `check_bindings` is the only place
        that can tell the difference before the SPEC is hashed."""
        with pytest.raises(BindingError, match="a Binding"):
            Spec(goal="g", steps=(
                Step(declaration="a", contract_version="1.0.0", accepts=M({"p": "just a string"})),
            ))


class TestTheMarkdownSurfaceRejectsWithALocus:
    """3.2 · C-12 — a rejection names line, field, and what would have been accepted."""

    GOOD = (
        "# goal: read the user's newest book\n"
        "# done_when: the prose is on screen\n"
        "\n"
        "## step: book_list\n"
        "- contract_version: 1.0.0\n"
        "- emits: book_id\n"
        "\n"
        "## step: book_read\n"
        "- contract_version: 1.0.0\n"
        "- gated: true\n"
        "- accepts:\n"
        "  - book_id from step 0.book_id\n"
        "  - limit = 20\n"
    )

    def test_A_PLAN_ROUND_TRIPS_INTO_A_SPEC(self):
        spec = parse(self.GOOD)
        assert spec.goal == "read the user's newest book"
        assert [s.declaration for s in spec.steps] == ["book_list", "book_read"]
        assert spec.steps[1].gated is True
        b = spec.steps[1].accepts["book_id"]
        assert (b.from_step, b.from_emit) == (0, "book_id")
        assert spec.steps[1].accepts["limit"].literal == 20
        assert preflight_gates(spec) == (1,)

    def test_A_PARSE_FAILURE_CARRIES_THE_LINE_NUMBER_AND_WHAT_WOULD_BE_ACCEPTED(self):
        bad = self.GOOD.replace("  - book_id from step 0.book_id\n",
                                "  - book_id <- step 0.book_id\n")
        with pytest.raises(PlanParseError) as exc:
            parse(bad)
        assert exc.value.line_no == 12, f"reported line {exc.value.line_no}"
        assert "from step" in exc.value.accepted and "=" in exc.value.accepted
        assert "invalid" not in str(exc.value).lower(), (
            "C-12: a rejection names the locus and the accepted form, never just `invalid`"
        )

    def test_A_PLAN_WITH_NO_GOAL_IS_REFUSED(self):
        with pytest.raises(PlanParseError, match="goal"):
            parse("## step: book_list\n- emits: book_id\n")

    def test_A_PLAN_WITH_NO_STEPS_IS_REFUSED(self):
        """An empty plan cannot reach a `done_when`, so it would be a silent exit by construction."""
        with pytest.raises(PlanParseError, match="no steps"):
            parse("# goal: do a thing\n")

    def test_A_SECOND_GOAL_HEADING_IS_REFUSED(self):
        """Two goals is two plans. A revision is a new SPEC version, not a second heading — and
        silently keeping the first (or the last) would make which one wins a property of the parser
        rather than a decision anybody took."""
        with pytest.raises(PlanParseError) as exc:
            parse("# goal: one\n# goal: two\n## step: book_list\n- emits: x\n")
        assert exc.value.line_no == 2

    def test_ACCEPTS_WITH_A_VALUE_ON_THE_SAME_LINE_IS_REFUSED(self):
        """`- accepts: book_id from step 0.book_id` looks right and is not: bindings are nested
        data, so each needs its own line. Accepting the one-liner would mean a second grammar for
        the same thing, and the two would drift."""
        with pytest.raises(PlanParseError, match="own"):
            parse("# goal: g\n## step: a\n- accepts: book_id from step 0.book_id\n")

    def test_CONTENT_BEFORE_THE_GOAL_HEADING_IS_REFUSED(self):
        """Without a goal there is nothing for the plan-level `done_when` to be about, and §0.11
        keeps plan-level and step-level completion separate precisely so a plan cannot complete
        every step while not having done the thing that was asked."""
        with pytest.raises(PlanParseError, match="before any"):
            parse("some prose\n# goal: g\n## step: a\n- emits: x\n")

    def test_AN_UNRECOGNISED_LINE_IS_REFUSED_AND_LISTS_THE_KEYS(self):
        """The catch-all still names what would have been accepted (C-12). A parser that ignored
        what it did not understand would drop a `gated: true` to a typo — silently downgrading a
        step that needs approval into one that does not."""
        with pytest.raises(PlanParseError) as exc:
            parse("# goal: g\n## step: a\n- emits: x\n- gatd: true\n")
        assert exc.value.line_no == 4
        assert "gated" in exc.value.accepted, "the rejection must list the keys that ARE accepted"

    def test_THE_PARSER_HAS_NO_TEMPLATE_INTERPOLATION_ARM(self):
        """A reference written inside a value cannot be told from text the user typed."""
        bad = self.GOOD.replace("  - book_id from step 0.book_id\n",
                                "  - book_id = {{step0.book_id}}\n")
        spec = parse(bad)
        b = spec.steps[1].accepts["book_id"]
        assert b.from_step is None and b.literal == "{{step0.book_id}}", (
            "the braces were interpreted as a reference — the parser grew an interpolation arm, "
            "and a literal that can compute is a literal that can read what it was not handed"
        )


class TestTheProjectionIsHonestAndLossless_WhereItMatters:
    """3.3 — generated with a gate, declares its lossiness, stable, never compresses an identifier."""

    def _with_value(self):
        spec = _pair()
        st = State(spec.hashed())
        st.append(Event(kind="step_emitted", step_index=0, values=M({"book_id": UUID})))
        return spec, st

    def test_AN_IDENTIFIER_IS_NEVER_COMPRESSED(self):
        spec, st = self._with_value()
        assert UUID in project(spec, st), (
            "the projection dropped or truncated an emitted identifier — that is the 61.8% failure "
            "with an extra step in front of it"
        )

    def test_THE_PROJECTION_TAKES_NO_BUDGET_PARAMETER(self):
        """🔴 Obligation 4 is not *try not to truncate*. A projection that can be asked to fit a
        size is one that will silently drop the value the next step binds to."""
        import inspect

        params = set(inspect.signature(project).parameters)
        assert params == {"spec", "state"}, (
            f"project() takes {sorted(params)}; a budget, max_length or limit here would make "
            f"dropping an identifier expressible"
        )

    def test_IT_IS_STABLE_BETWEEN_PLAN_EVENTS(self):
        """Obligation 3 — deterministic in (spec, state) and nothing else, so an unchanged plan
        cannot churn the prompt prefix and every cached block below it."""
        spec, st = self._with_value()
        assert project(spec, st) == project(spec, st)

    def test_IT_DECLARES_WHETHER_IT_IS_ABRIDGED_AND_NAMES_WHAT_IS_NOT(self):
        spec, st = self._with_value()
        assert "complete plan" in project(spec, st)
        long_goal = Spec(goal="g" * 900, steps=spec.steps)
        out = project(long_goal, st)
        assert "abridged" in out and "every step, position, emitted value" in out, (
            "a summary that does not say it is one gets read as complete"
        )
        assert UUID in out, "abridging the GOAL must never reach an identifier"

    def test_THE_COMMITTED_LEDGER_IS_PROJECTED_IN_FULL(self):
        spec, st = self._with_value()
        st.append(Event(kind="effect_committed", step_index=0,
                        undo_hint="book_delete(019fafa2)", committed=True))
        assert "book_delete(019fafa2)" in project(spec, st)
