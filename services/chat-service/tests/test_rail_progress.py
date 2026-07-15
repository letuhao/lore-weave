"""Track C Phase 2 — the RAIL DRIVER.

The flagship's failure was never a missing tool. Discovery was dead, the assent landed on
the rail, the step tools were advertised, the errors were honest — and the cast still landed
**0/0/0/0 across four identical runs**, because the model was asked to hold a 12-step recipe
across a 17-turn conversation and simply lost its place.

So these tests are about one question: *does the server know where the user actually is?*
And the sharpest of them is `test_a_tool_that_ran_but_wrote_nothing_is_not_done` — the whole
reason the book outranks the call log.
"""

from __future__ import annotations

import pytest

from app.services.rail_progress import (
    BookState,
    compute_rail_progress,
    parse_done_when,
    render_book_state,
    render_progress_block,
)

# The flagship rail, in the shape the registry actually serves it.
VISION_STEPS = [
    {"id": "see-standards", "tool": "glossary_list_system_standards"},
    {"id": "adopt-categories", "tool": "glossary_adopt_standards"},
    {"id": "apply-categories", "tool": "glossary_confirm_action", "gate": "confirm",
     "inputs_map": {"confirm_token": "adopt-categories.confirm_token"}, "done_when": "categories > 0"},
    {"id": "read-back", "tool": "glossary_book_ontology_read"},
    {"id": "capture-cast", "tool": "glossary_extract_entities_from_doc"},
    {"id": "save-cast", "tool": "glossary_propose_entities", "done_when": "cast > 0"},
    {"id": "apply-cast", "tool": "glossary_confirm_action", "gate": "confirm",
     "inputs_map": {"confirm_token": "save-cast.confirm_token"}},
    {"id": "connect-project", "tool": "kg_project_create"},
    {"id": "connect-people", "tool": "kg_project_entities_to_nodes", "done_when": "connections > 0"},
    {"id": "arc-plan", "tool": "plan_propose_spec", "async_job": True, "done_when": "plan > 0"},
    {"id": "draft-opening", "tool": "book_chapter_create", "done_when": "chapters > 0"},
    {"id": "write-opening", "tool": "book_chapter_save_draft", "done_when": "prose > 0"},
]


# ── the grammar ──────────────────────────────────────────────────────────────

class TestDoneWhenGrammar:
    def test_parses_the_closed_set(self):
        assert parse_done_when("cast > 0") == ("cast", ">", 0)
        assert parse_done_when("categories >= 3") == ("categories", ">=", 3)
        assert parse_done_when("  plan>1  ") == ("plan", ">", 1)

    def test_rejects_an_unknown_key(self):
        """`entities` is not a book-state key (it is `cast`). A predicate naming a key the
        probe never fills could never be satisfied — better to fall back to the call log
        loudly than to strand the agent on a step forever."""
        assert parse_done_when("entities > 0") is None

    def test_rejects_junk_and_never_evaluates_it(self):
        # NB `cast < 5` is now VALID (the drain operator) — see TestDrainPredicate. Junk here is
        # only what is outside the closed grammar entirely.
        for expr in ("cast", "cast > ", "cast != 5", "len(cast) > 0", "__import__('os')", ""):
            assert parse_done_when(expr) is None


# ── the core question: where is the user? ────────────────────────────────────

class TestProgress:
    def test_an_empty_book_starts_at_step_one(self):
        state = BookState(categories=0, cast=0, connections=0, plan=0, chapters=0, prose=0)
        p = compute_rail_progress("vision-to-book", VISION_STEPS, state, succeeded_tools=set())
        assert p.next_index == 1
        assert p.next_step.tool == "glossary_list_system_standards"
        assert not p.all_done

    def test_the_artifact_marks_a_step_done_even_with_no_memory_of_it(self):
        """The categories exist in the book. It does not matter whether the model recalls
        creating them, and it does not matter that the call log is empty (a fresh turn after
        a compaction, say) — they are THERE."""
        state = BookState(categories=12, cast=0, connections=0, plan=0, chapters=0, prose=0)
        p = compute_rail_progress("vision-to-book", VISION_STEPS, state, succeeded_tools=set())

        apply_cats = next(s for s in p.steps if s.step_id == "apply-categories")
        assert apply_cats.done is True
        assert "categories=12" in apply_cats.reason

    def test_a_tool_that_ran_but_wrote_nothing_is_NOT_done(self):
        """THE test. This is the flagship's signature failure, and the entire reason the
        book outranks the call log.

        `glossary_propose_entities` was CALLED and returned success — it is in the call log.
        But 0 entities exist. Trusting the call log would mark save-cast done and march the
        agent on to `apply-cast`, confirming a cast that was never created. The book says
        otherwise, and the book wins."""
        state = BookState(categories=12, cast=0, connections=0, plan=0, chapters=0, prose=0)
        ran = {
            "glossary_list_system_standards", "glossary_adopt_standards",
            "glossary_confirm_action", "glossary_book_ontology_read",
            "glossary_extract_entities_from_doc",
            "glossary_propose_entities",      # ← it RAN, and it wrote nothing
        }
        p = compute_rail_progress("vision-to-book", VISION_STEPS, state, ran)

        save_cast = next(s for s in p.steps if s.step_id == "save-cast")
        assert save_cast.done is False
        assert "never landed" in save_cast.reason
        # …and that is exactly where the agent is sent back to
        assert p.next_step.step_id == "save-cast"
        assert p.next_step.tool == "glossary_propose_entities"

    def test_the_call_log_carries_steps_with_no_artifact(self):
        """A read (`see-standards`) or a confirm leaves nothing in the book to point at, so
        the server's own record of what ran is the only truth available."""
        state = BookState(categories=12, cast=4, connections=0, plan=0, chapters=0, prose=0)
        ran = {
            "glossary_list_system_standards", "glossary_adopt_standards",
            "glossary_confirm_action", "glossary_book_ontology_read",
            "glossary_extract_entities_from_doc", "glossary_propose_entities",
        }
        p = compute_rail_progress("vision-to-book", VISION_STEPS, state, ran)
        assert next(s for s in p.steps if s.step_id == "see-standards").done is True
        assert next(s for s in p.steps if s.step_id == "apply-cast").done is True
        # first genuinely-outstanding step
        assert p.next_step.step_id == "connect-project"

    def test_unknown_state_falls_back_to_the_call_log_never_to_a_guess(self):
        """The glossary probe failed this turn (cast is None = UNKNOWN, NOT 0). Guessing
        "done" would skip the step; guessing "not done" would redo it. Fall back to the one
        thing we do know: whether the tool ran."""
        state = BookState(categories=12, cast=None)
        p = compute_rail_progress(
            "vision-to-book", VISION_STEPS, state, {"glossary_propose_entities"},
        )
        save_cast = next(s for s in p.steps if s.step_id == "save-cast")
        assert save_cast.done is True
        assert "unknown" in save_cast.reason

    def test_a_finished_rail_reports_all_done_and_says_so(self):
        state = BookState(categories=12, cast=8, connections=8, plan=1, chapters=1, prose=1)
        ran = {s["tool"] for s in VISION_STEPS}
        p = compute_rail_progress("vision-to-book", VISION_STEPS, state, ran)
        assert p.all_done
        assert p.next_step is None
        assert "EVERY step" in render_progress_block(p)


# ── what the model actually reads ────────────────────────────────────────────

class TestRender:
    def test_the_block_names_ONE_next_action_with_its_tool(self):
        state = BookState(categories=12, cast=0, connections=0, plan=0, chapters=0, prose=0)
        ran = {
            "glossary_list_system_standards", "glossary_adopt_standards",
            "glossary_confirm_action", "glossary_book_ontology_read",
            "glossary_extract_entities_from_doc",
        }
        text = render_progress_block(
            compute_rail_progress("vision-to-book", VISION_STEPS, state, ran)
        )
        assert "YOUR PLACE IN THE RECIPE" in text
        assert "glossary_propose_entities" in text
        assert "save-cast" in text
        # it must also tell the model NOT to redo what is already done
        assert "do NOT repeat these" in text
        assert "apply-categories" in text

    def test_an_unknown_source_is_never_reported_as_zero(self):
        """A failed glossary probe must not render "characters saved: 0" — that would tell
        the agent the user's world is empty and invite it to rebuild one they already have.
        An unknown source is simply not mentioned."""
        line = render_book_state(BookState(categories=12, cast=None))
        assert "world categories: 12" in line
        assert "characters" not in line

    def test_no_known_state_renders_no_snapshot(self):
        assert render_book_state(BookState()) is None


# ── the wiring: the progress block must actually REACH the prompt ────────────

class TestPinnedRailCarriesTheProgress:
    """A perfect progress computation that never reaches the model is worth nothing. This
    is the seam where a 'built but unwired' bug would hide."""

    def _wf(self):
        return [{
            "slug": "vision-to-book",
            "title": "Turn a story idea into a book",
            "description": "d",
            "steps": VISION_STEPS,
            "notes_md": "notes",
        }]

    def test_the_rendered_progress_lands_in_the_pinned_block(self):
        from app.services.workflow_runner import pinned_rail_block

        state = BookState(categories=12, cast=0, connections=0, plan=0, chapters=0, prose=0)
        ran = {"glossary_list_system_standards", "glossary_adopt_standards",
               "glossary_confirm_action", "glossary_book_ontology_read",
               "glossary_extract_entities_from_doc"}
        prog = render_progress_block(
            compute_rail_progress("vision-to-book", VISION_STEPS, state, ran)
        )

        text, tools = pinned_rail_block(
            self._wf(), ["vision-to-book"], frozenset(),
            progress_by_slug={"vision-to-book": prog},
        )
        assert text is not None
        # Strings ONLY render_progress_block emits — never the header. (The header's memory
        # clause used to quote "YOUR NEXT ACTION", so asserting that let the test pass even
        # when the block itself never rendered — review finding #10.)
        assert "YOUR PLACE IN THE RECIPE: step" in text
        assert "do NOT repeat these" in text
        assert "glossary_propose_entities" in text
        # the step tools are still activated (the pin's other job)
        assert "glossary_propose_entities" in tools

    def test_without_progress_the_rail_still_renders_exactly_as_before(self):
        """Degrade contract: a failed probe must leave the rail working, not break the turn."""
        from app.services.workflow_runner import pinned_rail_block

        text, tools = pinned_rail_block(self._wf(), ["vision-to-book"], frozenset())
        assert text is not None
        assert "YOUR NEXT ACTION" not in text
        assert "YOU HAVE A READY-MADE RECIPE" in text
        assert "glossary_propose_entities" in tools


# ── the two rules the LIVE run forced (a naive "first not-done" was wrong) ────

class TestPipelineSemantics:
    def test_a_fresh_session_on_an_EXISTING_book_does_not_restart_at_step_one(self):
        """The bug the live run exposed, verbatim.

        A user opens a NEW chat on a book that already has 31 categories and 3187 cast
        members. The call log is empty (it is a new session), so every read/confirm step
        looks "not done" and the naive rule told the agent:

            "YOUR NEXT ACTION - step 1 of 12: call glossary_list_system_standards"

        …on a half-built book. A rail is a PIPELINE: a later artifact is proof the earlier
        plumbing ran. You cannot be holding 3187 cast members without the categories they
        are filed under."""
        state = BookState(categories=31, cast=3187, connections=0, plan=0, chapters=0, prose=0)
        p = compute_rail_progress("vision-to-book", VISION_STEPS, state, succeeded_tools=set())

        assert next(s for s in p.steps if s.step_id == "see-standards").done is True
        assert next(s for s in p.steps if s.step_id == "capture-cast").done is True
        # the cast is real, so the confirm that would apply it is moot too
        assert next(s for s in p.steps if s.step_id == "apply-cast").done is True
        # …and the genuinely-next thing is to connect what exists
        assert p.next_step.step_id == "connect-project"

    def test_a_confirm_is_done_exactly_when_the_step_it_confirms_is_done(self):
        """A confirm gate has no artifact of its own and is not independently actionable —
        it needs a token from a call that already happened. It names its source in
        inputs_map, so derive it rather than stranding the agent on a confirm it cannot make."""
        # cast landed ⇒ the confirm that applies it is done
        p = compute_rail_progress(
            "vision-to-book", VISION_STEPS,
            BookState(categories=12, cast=5, connections=0, plan=0, chapters=0, prose=0), set(),
        )
        assert next(s for s in p.steps if s.step_id == "apply-cast").done is True

        # cast did NOT land ⇒ the confirm is not done either, and the agent is sent back to
        # the step that actually creates the cast. The call log carries the real run's
        # earlier steps: `capture-cast` MUST have produced candidates before `save-cast`
        # could propose them, so the driver must never leapfrog it to "fix" the cast.
        p2 = compute_rail_progress(
            "vision-to-book", VISION_STEPS,
            BookState(categories=12, cast=0, connections=0, plan=0, chapters=0, prose=0),
            {
                "glossary_list_system_standards", "glossary_adopt_standards",
                "glossary_confirm_action", "glossary_book_ontology_read",
                "glossary_extract_entities_from_doc",
                "glossary_propose_entities",   # it ran, and wrote nothing
            },
        )
        assert next(s for s in p2.steps if s.step_id == "apply-cast").done is False
        assert p2.next_step.step_id == "save-cast"

    def test_a_missing_artifact_is_never_backfilled_over_by_a_later_one(self):
        """A chapter exists but the cast does not. The pipeline rule must NOT conclude
        "we got as far as chapters, so the cast must be fine" — the user still has no cast,
        and an absent artifact is a hard NOT-DONE in both directions."""
        state = BookState(categories=12, cast=0, connections=0, plan=0, chapters=1, prose=1)
        p = compute_rail_progress("vision-to-book", VISION_STEPS, state, set())

        # the cast step is NOT done (cast=0), even though a later artifact (chapters) exists
        assert next(s for s in p.steps if s.step_id == "save-cast").done is False
        # …and the resume point is the first outstanding step, which the CONTIGUOUS backfill
        # correctly puts BEFORE the gap (read-back → capture-cast → save-cast), not by leaping
        # straight to save-cast over the capture step that feeds it.
        assert p.next_step.index < next(s.index for s in p.steps if s.step_id == "save-cast")
        assert not p.next_step.done


# ── the driver answers WHERE, never WHEN (the live-run regression) ───────────

class TestTheDriverStatesWhereNeverWhen:
    """Two live S06 runs taught this contract, both of them 0/5.

    Cut 1 issued an unconditional imperative ("call it NOW — the user already said yes").
    On turn 1 the user has said nothing of the sort; the agent fired the opening step while
    they were still describing their story, and burned the rail before the real assent.

    Cut 2 over-corrected: hold the imperative until "in flight" = an artifact exists. But the
    rail's first three steps CREATE no artifact, so in-flight could never become true, the
    block said "don't start building on your own" forever, and the agent re-ran step 1 every
    turn. A deadlock that actively told the model not to work.

    A driver that owns WHEN will either interrupt the user or stall the rail. It owns WHERE.
    """

    def test_the_block_never_commands_timing(self):
        """No "NOW", no "keep listening" — those are the model's call, and the pinned rail's
        header already governs them."""
        for state in (
            BookState(categories=0, cast=0, connections=0, plan=0, chapters=0, prose=0),
            BookState(categories=12, cast=0, connections=0, plan=0, chapters=0, prose=0),
            BookState(categories=12, cast=9, connections=9, plan=1, chapters=1, prose=1),
        ):
            text = render_progress_block(
                compute_rail_progress("vision-to-book", VISION_STEPS, state, set())
            )
            assert "NOW, in this turn" not in text
            assert "Keep listening" not in text
            assert "already said yes" not in text

    def test_an_empty_book_still_names_step_one_as_the_place(self):
        """The rail has to be startable. Cut 2's deadlock was refusing to name a startable
        step until an artifact existed — which the first three steps could never create."""
        state = BookState(categories=0, cast=0, connections=0, plan=0, chapters=0, prose=0)
        text = render_progress_block(
            compute_rail_progress("vision-to-book", VISION_STEPS, state, set())
        )
        assert "YOUR PLACE IN THE RECIPE: step 1 of 12" in text
        assert "glossary_list_system_standards" in text

    def test_a_part_built_book_names_the_OUTSTANDING_step_not_step_one(self):
        """The whole point: the model stops relitigating step 1."""
        state = BookState(categories=12, cast=0, connections=0, plan=0, chapters=0, prose=0)
        text = render_progress_block(
            compute_rail_progress(
                "vision-to-book", VISION_STEPS, state,
                {"glossary_list_system_standards", "glossary_adopt_standards",
                 "glossary_confirm_action", "glossary_book_ontology_read"},
            )
        )
        assert "step 5 of 12" in text
        assert "glossary_extract_entities_from_doc" in text     # capture-cast
        assert "do NOT repeat these" in text
        assert "apply-categories" in text                        # named as done
        assert "not at step 1" in text

    def test_the_block_never_contradicts_itself_on_an_empty_book(self):
        """Shipped in run 3 and it cost a whole S06 run: on an empty book the block said
        'YOUR PLACE: step 1 ... This is the step to run - NOT step 1'. A contradiction in a
        system prompt is worse than silence: the model has to resolve it, and it resolves it
        by doing nothing. The caveat is only meaningful when work is actually behind us."""
        text = render_progress_block(
            compute_rail_progress(
                "vision-to-book", VISION_STEPS,
                BookState(categories=0, cast=0, connections=0, plan=0, chapters=0, prose=0),
                set(),
            )
        )
        assert "step 1 of 12" in text
        assert "not at step 1" not in text.lower()

    def test_the_resume_caveat_appears_once_there_IS_work_behind_us(self):
        text = render_progress_block(
            compute_rail_progress(
                "vision-to-book", VISION_STEPS,
                BookState(categories=12, cast=0, connections=0, plan=0, chapters=0, prose=0),
                {"glossary_list_system_standards", "glossary_adopt_standards",
                 "glossary_confirm_action", "glossary_book_ontology_read"},
            )
        )
        assert "resume HERE" in text
        assert "not at step 1" in text


# ── same-tool-twice: the call log must be CONSUMED, not just membership-tested ─

class TestCallLogConsumesOccurrences:
    """A review finding: a rail that uses the same tool in two steps was marking BOTH done
    the moment the FIRST succeeded, because doneness was `tool in succeeded_tools` (set
    membership). It must consume one success per step."""

    STEPS = [
        {"id": "confirm-a", "tool": "confirm_action"},
        {"id": "confirm-b", "tool": "confirm_action"},
    ]

    def test_one_success_marks_only_the_first_of_two_same_tool_steps(self):
        from collections import Counter
        state = BookState()  # no artifacts — pure call-log path
        p = compute_rail_progress("x", self.STEPS, state, Counter({"confirm_action": 1}))
        assert p.steps[0].done is True
        assert p.steps[1].done is False
        assert p.next_step.step_id == "confirm-b"

    def test_two_successes_mark_both(self):
        from collections import Counter
        p = compute_rail_progress("x", self.STEPS, BookState(), Counter({"confirm_action": 2}))
        assert all(s.done for s in p.steps)
        assert p.all_done

    def test_a_plain_set_still_works_each_tool_once(self):
        # backward-compat: a set input treats each tool as one success (Counter(set) → 1 each)
        p = compute_rail_progress("x", self.STEPS, BookState(), {"confirm_action"})
        assert p.steps[0].done is True
        assert p.steps[1].done is False


# ── the step-runner's decision helper (P-1) ──────────────────────────────────

class TestNextActionableStep:
    """The pure decision the server-side step-runner makes each hop. The design panel chose a
    pure helper precisely so THIS logic is unit-testable — the loop that calls it is invisible
    to every other test."""

    from app.services.rail_progress import (  # noqa: E402
        DRIVE, STOP_ASYNC, STOP_DONE, STOP_UNKNOWN, STOP_USER,
        next_actionable_step,
    )

    ASYNC = frozenset()  # async is authored on the step (async_job:true), so no catalog set needed

    def _prog(self, state, ran):
        from collections import Counter
        return compute_rail_progress("vision-to-book", VISION_STEPS, state, Counter(ran))

    def test_empty_book_drives_step_one(self):
        from app.services.rail_progress import next_actionable_step, DRIVE
        p = self._prog(BookState(categories=0, cast=0, connections=0, plan=0, chapters=0, prose=0), set())
        action, step = next_actionable_step(p, VISION_STEPS, set(), self.ASYNC)
        assert action == DRIVE
        assert step.tool == "glossary_list_system_standards"

    def test_after_categories_land_it_drives_toward_the_cast(self):
        from app.services.rail_progress import next_actionable_step, DRIVE
        # categories landed; the read/confirm steps are pipeline-backfilled done
        p = self._prog(
            BookState(categories=12, cast=0, connections=0, plan=0, chapters=0, prose=0),
            {"glossary_list_system_standards", "glossary_adopt_standards",
             "glossary_confirm_action", "glossary_book_ontology_read",
             "glossary_extract_entities_from_doc"},
        )
        action, step = next_actionable_step(p, VISION_STEPS, set(), self.ASYNC)
        assert action == DRIVE
        assert step.step_id == "save-cast"      # the thing S06 never reached

    def test_a_confirm_gate_is_DRIVEN_because_calling_the_tool_raises_the_card(self):
        """Corrected against live evidence (drift DR14). glossary_adopt_standards does NOT
        auto-apply — it returns a confirm_token, and the categories land only when the model
        calls glossary_confirm_action, which SUSPENDS for the user. So the driver DRIVES the
        confirm step (nudges the model to call the tool → the card is raised → the user gates
        at the suspend). The first cut STOPPED here and the rail dead-ended at step 3 forever
        (measured: categories 0/5)."""
        from app.services.rail_progress import next_actionable_step, DRIVE
        steps = [
            {"id": "adopt", "tool": "glossary_adopt_standards"},
            {"id": "apply", "tool": "glossary_confirm_action", "gate": "confirm", "done_when": "categories > 0"},
            {"id": "read", "tool": "glossary_book_ontology_read"},
        ]
        from collections import Counter
        p = compute_rail_progress("x", steps, BookState(categories=0), Counter({"glossary_adopt_standards": 1}))
        action, step = next_actionable_step(p, steps, {"glossary_adopt_standards"}, self.ASYNC)
        assert action == DRIVE
        assert step.tool == "glossary_confirm_action"

    def test_an_already_started_async_step_stops_the_driver(self):
        from app.services.rail_progress import next_actionable_step, STOP_ASYNC
        # everything up to arc-plan done; plan not landed yet; plan_propose_spec already ran
        state = BookState(categories=12, cast=8, connections=8, plan=0, chapters=0, prose=0)
        ran = {"glossary_list_system_standards", "glossary_adopt_standards", "glossary_confirm_action",
               "glossary_book_ontology_read", "glossary_extract_entities_from_doc",
               "glossary_propose_entities", "kg_project_create", "kg_project_entities_to_nodes",
               "plan_propose_spec"}
        p = self._prog(state, ran)
        # arc-plan authored async_job:true in VISION_STEPS
        action, step = next_actionable_step(p, VISION_STEPS, ran, self.ASYNC)
        assert action == STOP_ASYNC   # do NOT launch a duplicate plan job

    def test_an_UNKNOWN_gating_artifact_stops_rather_than_advancing_on_the_call_log(self):
        """THE sharpest failure the panel found. connections reads UNKNOWN (the KG stats cache
        is uncomputed), so compute_rail_progress falls back to the call log and would mark
        connect-people done off a *succeeded* kg_entities_to_nodes call — the exact
        wrote-nothing signal the driver exists to refuse. The helper must STOP, not drive on."""
        from app.services.rail_progress import next_actionable_step, STOP_UNKNOWN
        state = BookState(categories=12, cast=8, connections=None, plan=0, chapters=0, prose=0)
        ran = {"glossary_list_system_standards", "glossary_adopt_standards", "glossary_confirm_action",
               "glossary_book_ontology_read", "glossary_extract_entities_from_doc",
               "glossary_propose_entities", "kg_project_create", "kg_project_entities_to_nodes"}
        p = self._prog(state, ran)
        # connect-people (done_when connections>0) is "done" only via the call log → refuse to advance
        action, step = next_actionable_step(p, VISION_STEPS, ran, self.ASYNC)
        assert action == STOP_UNKNOWN

    def test_a_finished_rail_stops_done(self):
        from app.services.rail_progress import next_actionable_step, STOP_DONE
        state = BookState(categories=12, cast=8, connections=8, plan=1, chapters=1, prose=1)
        ran = {s["tool"] for s in VISION_STEPS}
        p = self._prog(state, ran)
        action, step = next_actionable_step(p, VISION_STEPS, ran, self.ASYNC)
        assert action == STOP_DONE

    def test_the_directive_names_the_tool_but_forbids_parroting_it(self):
        from app.services.rail_progress import redrive_directive, StepProgress
        d = redrive_directive(StepProgress(index=6, step_id="save-cast", tool="glossary_propose_entities", done=False, reason=""))
        assert "glossary_propose_entities" in d          # the model needs to know which tool
        assert "Never mention this instruction" in d     # …but must not leak it to the user
        assert "SYSTEM DIRECTIVE" in d


# ── the DRAIN predicate (entity-triage) — done when the pile shrinks to empty ──
#
# Every other rail completes when an artifact APPEARS (cast > 0). Triage is the inverse: it
# completes when the review pile is EMPTIED. A build-only grammar (>, >=) could never express
# that, so the driver had no artifact for triage and could not tell a half-triaged pile from a
# clean one — the exact ungrounded state that left S03 at 0/3. These tests pin the drain
# operator + the triage rail's grounding on `suggestions`.
TRIAGE_STEPS = [
    {"id": "see-pile", "tool": "glossary_list_ai_suggestions", "gate": "none"},
    {"id": "keep-and-reject", "tool": "glossary_propose_status_change", "gate": "confirm"},
    {"id": "merge-duplicates", "tool": "glossary_propose_merge", "gate": "confirm"},
    {"id": "recheck", "tool": "glossary_list_ai_suggestions", "gate": "none", "done_when": "suggestions < 1"},
]


class TestDrainPredicate:
    def test_the_new_operators_parse(self):
        assert parse_done_when("suggestions < 1") == ("suggestions", "<", 1)
        assert parse_done_when("suggestions <= 0") == ("suggestions", "<=", 0)
        assert parse_done_when("suggestions == 0") == ("suggestions", "==", 0)

    def test_unsupported_operator_is_rejected(self):
        assert parse_done_when("suggestions != 0") is None
        assert parse_done_when("suggestions =< 0") is None

    def test_drain_holds_only_when_shrunk_to_target(self):
        # 6 pending ⇒ NOT drained; 0 pending ⇒ drained; UNKNOWN ⇒ None (never a false "clean")
        full = compute_rail_progress("entity-triage", TRIAGE_STEPS, BookState(suggestions=6), set())
        assert full.steps[3].done is False
        assert full.next_index is not None  # rail stays live while items remain
        clean = compute_rail_progress("entity-triage", TRIAGE_STEPS,
                                      BookState(suggestions=0), {"glossary_list_ai_suggestions",
                                                                 "glossary_propose_status_change"})
        assert clean.steps[3].done is True

    def test_a_half_triaged_pile_keeps_the_recheck_step_open(self):
        # listed + made some decisions, but 3 items still pending ⇒ recheck is NOT done, so the
        # driver keeps pointing at the rail instead of declaring it finished (the S03 fix).
        from collections import Counter
        p = compute_rail_progress(
            "entity-triage", TRIAGE_STEPS, BookState(suggestions=3),
            Counter({"glossary_list_ai_suggestions": 1, "glossary_propose_status_change": 1,
                     "glossary_propose_merge": 1}),
        )
        assert p.next_step is not None and p.next_step.step_id == "recheck"
        assert not p.all_done

    def test_unknown_suggestions_never_reads_as_clean(self):
        # glossary unreachable ⇒ suggestions None ⇒ fall back to the call log, NOT a false drain.
        p = compute_rail_progress("entity-triage", TRIAGE_STEPS, BookState(suggestions=None),
                                  {"glossary_list_ai_suggestions"})
        # recheck falls back to the call log (its tool ran) — but crucially not via a manufactured 0.
        assert "suggestions" not in (render_book_state(BookState(suggestions=None)) or "")

    def test_snapshot_labels_the_pending_pile(self):
        snap = render_book_state(BookState(suggestions=4))
        assert snap is not None and "suggested items still waiting for review: 4" in snap


# ── the COMPILE effect (Phase G · G0) — a proposal is NOT a compiled plan ─────────────
#
# The S06 flagship failure in one line: the agent proposed a spec (`plan`/has_spec flips true)
# and STOPPED, so `structure_node` stayed 0 — the plan was talked about, never materialised.
# `plan > 0` marks the planning step done after a bare proposal. These two keys gate on the
# REAL compile instead.

# A planning rail whose "compile" step is gated on the durable structure, not the proposal.
COMPILE_STEPS = [
    {"id": "propose", "tool": "plan_propose_spec", "async_job": True, "done_when": "plan > 0"},
    {"id": "compile", "tool": "plan_compile", "done_when": "structure_fresh > 0"},
]


class TestCompileEffectG0:
    def test_grammar_accepts_the_new_keys(self):
        assert parse_done_when("structure > 0") == ("structure", ">", 0)
        assert parse_done_when("structure_fresh > 0") == ("structure_fresh", ">", 0)

    def test_a_proposal_alone_does_NOT_satisfy_the_compile_step_D3(self):
        """The core S06 fix. The proposal landed (`plan`=1) and `plan_compile` even 'ran'
        successfully — but the book has ZERO compiled structure. The compile step is NOT done;
        the driver keeps pointing at it. A bare arc_create (structure via a plain insert) is the
        same case: it never stamps plan_run_id, so `structure_fresh` stays 0."""
        state = BookState(plan=1, structure=0, structure_fresh=0)
        p = compute_rail_progress(
            "planning", COMPILE_STEPS, state, succeeded_tools={"plan_propose_spec", "plan_compile"},
        )
        # propose IS done (its artifact exists); compile is NOT (the effect never landed).
        by_id = {s.step_id: s for s in p.steps}
        assert by_id["propose"].done is True
        assert by_id["compile"].done is False
        assert "never landed" in by_id["compile"].reason
        assert p.next_step is not None and p.next_step.step_id == "compile"

    def test_a_replan_reads_born_fresh_zero_not_done_D2(self):
        """Freshness. run #1 already compiled (book-global `structure`=6), but the author
        re-plans: run #2 is the latest with nothing compiled yet (`structure_fresh`=0). The
        compile step must NOT be born-done off the OLD run's structure."""
        state = BookState(plan=1, structure=6, structure_fresh=0)
        p = compute_rail_progress(
            "planning", COMPILE_STEPS, state, succeeded_tools={"plan_propose_spec"},
        )
        by_id = {s.step_id: s for s in p.steps}
        assert by_id["compile"].done is False
        assert p.next_step is not None and p.next_step.step_id == "compile"

    def test_a_real_compile_marks_the_step_done(self):
        state = BookState(plan=1, structure=2, structure_fresh=2)
        p = compute_rail_progress(
            "planning", COMPILE_STEPS, state, succeeded_tools={"plan_propose_spec", "plan_compile"},
        )
        by_id = {s.step_id: s for s in p.steps}
        assert by_id["compile"].done is True
        assert p.all_done

    def test_unknown_structure_falls_back_to_the_call_log_never_a_guess(self):
        """composition unreachable ⇒ structure_fresh None ⇒ the compile step falls back to the
        call log (was plan_compile called?), NOT a manufactured 0 that would strand the rail."""
        state = BookState(plan=1, structure=None, structure_fresh=None)
        p = compute_rail_progress(
            "planning", COMPILE_STEPS, state, succeeded_tools={"plan_propose_spec"},
        )
        by_id = {s.step_id: s for s in p.steps}
        # compile's tool has NOT run and state is unknown → not done, but via the call-log path.
        assert by_id["compile"].done is False
        assert "unknown" in by_id["compile"].reason
        # and the unknown source never renders a fake 0
        assert "compiled" not in (render_book_state(state) or "")

    def test_the_new_keys_render_their_labels(self):
        snap = render_book_state(BookState(structure=3, structure_fresh=1))
        assert snap is not None
        assert "arcs compiled into real chapter/scene structure: 3" in snap
        assert "arcs the latest plan run just compiled: 1" in snap
