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
    {"id": "arc-plan", "tool": "plan_propose_spec", "done_when": "plan > 0"},
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
        for expr in ("cast", "cast > ", "cast < 5", "len(cast) > 0", "__import__('os')", ""):
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
