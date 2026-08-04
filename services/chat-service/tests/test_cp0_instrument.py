"""CP-0 — the instrument. Spec: docs/specs/2026-08-03-agent-runtime-unification §5.

**What these tests are for, and what they are not for.** The governing rule of this run is that a
test may REJECT but may never ADMIT: a green test here does not establish that the instrument is
sound in production, and no bound may be claimed from it. Five recorded cases in this repository had
a green test over an artifact no consumer ever received. What these do is fail when a specific,
named defect is reintroduced — each one below corresponds to a measured production failure, not to a
hypothetical.

Every test states the defect it rejects. If you cannot say what would make it red, it is not a test.
"""
from __future__ import annotations

import pytest

from pathlib import Path

from app.services import instrument
from app.services.instrument import AdvertisedToolsRecorder
from app.services.tool_surface import budget_names_by_tokens, budget_names_by_tokens_ex

_APP = Path(__file__).resolve().parents[1] / "app"


def _stream_src() -> str:
    return (_APP / "services" / "stream_service.py").read_text(encoding="utf-8")


def _surface_src() -> str:
    return (_APP / "services" / "tool_surface.py").read_text(encoding="utf-8")


# ── The wiring gates ────────────────────────────────────────────────────────────────────────────
#
# These assert over CALL SITES rather than over behaviour, and that is deliberate. The defect they
# reject is not a wrong value — it is a correct mechanism with no production caller, which every
# behavioural test passes because the mechanism itself works perfectly in isolation. A capability
# claimed in a docstring is not a capability; count the callers.


class TestTheInstrumentIsActuallyWired:
    def test_the_token_budgeter_reports_its_drops_in_production(self):
        """REJECTS: the exact defect this checkpoint shipped and a verifier caught.

        `budget_names_by_tokens_ex` was added, unit-tested, and documented as the fix for arm E —
        and had ZERO production callers. Every real site still called the plain variant and threw
        the dropped names away, so the column existed and stayed empty for the one narrowing it was
        built for. The unit tests all passed, because the function was never the problem.

        The budgeter decides at ACTIVATION time, several call sites away from the advertise
        chokepoint where the other four stages register — which is exactly how it got missed.

        Round 2 note, and it is the more useful lesson: the first version of THIS GATE read only
        `stream_service.py`. Four discarding sites lived in `tool_surface.py`, written in exactly
        the string form the gate forbids — so the gate was green over a live instance of the defect
        it names, purely because of the file it was pointed at. **A gate's scope is part of the
        gate.** It now reads every module that budgets, and the largest of those sites trims a
        315-tool catalog to a 2,000-token hot seed on EVERY turn.
        """
        for name, src in (("stream_service", _stream_src()), ("tool_surface", _surface_src())):
            assert "= budget_names_by_tokens(" not in src, (
                f"{name}: a production site still uses the variant that discards its drops"
            )
        assert "_budget_withheld" in _stream_src(), "the budgeter's drops must be accumulated"
        assert '"stage": "token_budget"' in _stream_src(), "drops must register with a stage"
        surface = _surface_src()
        assert "_budget_and_register(" in surface, (
            "surface-assembly budgeting must register its drops"
        )
        # Count CALLS, excluding the definition. The first version counted both, so the `def` line
        # paid for one missing call site — the same class of arithmetic slack that let the dispatch
        # gate stay green over a real defect. A gate that counts must count only the thing it means.
        calls = surface.count("_budget_and_register(") - surface.count("def _budget_and_register(")
        assert calls >= 4, (
            f"expected every surface-assembly budget call to register; found {calls}"
        )

    def test_a_surface_narrowing_registers_without_anyone_wiring_it(self):
        """REJECTS: the defect that survived THREE rounds by moving one frame inward each time.

        R1: the reporting budgeter had no callers. R2: four `tool_surface` sites still discarded.
        R3: those sites called the registering helper — and its `withheld_sink` argument had no
        callers, so the `is not None` guard never fired. Each round I fixed the layer named and the
        hole reappeared one level down, and a source-reading gate stayed green over all three.

        So this gate stops reading source. It runs the real budgeter with a real over-budget catalog
        and asserts the narrowing ARRIVES — which is false for every one of those three states,
        including the two that passed the string checks above.
        """
        catalog = [
            {"type": "function", "function": {"name": n, "description": "x" * 800,
                                              "parameters": {"type": "object", "properties": {}}}}
            for n in ("book_list", "book_read", "glossary_search", "kg_project_create")
        ]
        from app.services import instrument as _inst
        from app.services.tool_surface import _budget_and_register

        sink: list[dict] = []
        token = _inst.surface_withheld.set(sink)
        try:
            # No explicit sink argument — exactly how both production call sites invoke it.
            kept = _budget_and_register(
                None, "hot_seed", catalog,
                {"book_list", "book_read", "glossary_search", "kg_project_create"},
                token_budget=200,
            )
        finally:
            _inst.surface_withheld.reset(token)

        assert len(kept) < 4, "the budget must actually drop something or this proves nothing"
        assert sink, (
            "a surface narrowing registered NOWHERE when the caller omitted the sink — this is the "
            "arm-E defect, and it is what shipped green past three rounds of source review"
        )
        assert {e["tool"] for e in sink} == {"book_list", "book_read", "glossary_search",
                                            "kg_project_create"} - set(kept)
        assert all(e["stage"] == "hot_seed" and e["reason"] for e in sink)

    def test_every_real_dispatch_is_stamped_as_a_real_dispatch(self):
        """REJECTS: a genuine tool execution filed as our own prose.

        Shipped once already: the approved Tier-A RESUME path dispatches for real, was left
        unstamped, and so was classified `breaker` — inverting the one distinction the field exists
        to make, on the highest-consequence calls in the product (writes a human has just approved).

        **This gate was itself defective in round 1 and the defect is the instructive part.** It
        compared two COUNTS — dispatch sites vs `SOURCE_TOOL` stamps — with no positional
        correspondence. Three dispatches, three stamps, green. But one of the stamps belonged to the
        subagent path (not a dispatch at all) and it offset a genuine dispatch that had no stamp:
        the ext-task provide-input call, which recorded *nothing whatsoever*. A counting gate is
        satisfied by a coincidence; it was green over a live instance of the defect it names.

        Now POSITIONAL: each dispatch must have a stamp within the following window of source. A
        surplus stamp somewhere else in the file can no longer pay for a missing one here.
        """
        src = _stream_src()
        needle = "await knowledge_client.mcp_execute_tool("
        starts, i = [], 0
        while (idx := src.find(needle, i)) != -1:
            starts.append(idx)
            i = idx + len(needle)
        assert len(starts) >= 3, (
            f"expected at least 3 real dispatch sites (in-loop, approval resume, ext-task); "
            f"found {len(starts)}"
        )
        # Each dispatch owns the region from itself to the NEXT dispatch, and that region must
        # contain its stamp. A fixed byte window would be arbitrary — the in-loop dispatch stamps
        # ~220 lines later, at the yield — while region-ownership is the actual invariant: a stamp
        # cannot be claimed by two dispatches, so a surplus elsewhere cannot cover a deficit here.
        bounds = starts[1:] + [len(src)]
        unstamped = [
            src.count("\n", 0, s) + 1
            for s, end in zip(starts, bounds)
            if "source=instrument.SOURCE_TOOL" not in src[s:end]
        ]
        assert not unstamped, (
            f"real dispatch(es) at line(s) {unstamped} have no SOURCE_TOOL stamp nearby — a genuine "
            f"execution is being recorded as our own breaker prose, or not recorded at all"
        )


# ── CP-0.1 · one entry per pass, because the DIFFERENCE between passes is the finding ──────────


class TestAdvertisedIsPerPass:
    def test_a_mid_turn_deletion_is_visible_in_the_record(self):
        """REJECTS: the arm-E defect — a tool offered on pass 1 and gone by pass 2.

        This is the founding measurement of the whole rebuild: the budgeter dropped the one tool the
        model needed, and the failure looked, in every log we had, like the model choosing not to
        call it. A recorder that keeps one state per turn cannot express this, because the deletion
        IS the difference between two states. Goes red if `record_pass` ever overwrites.
        """
        rec = AdvertisedToolsRecorder()
        rec.record_pass(["book_list", "book_read", "glossary_search"])
        rec.record_pass(["book_list", "book_read"])  # glossary_search silently deleted

        recorded = rec.advertised_json()
        assert recorded is not None and len(recorded) == 2, "one entry per pass, appended"
        assert recorded[0]["pass"] == 1 and recorded[1]["pass"] == 2
        # The claim under test: the deletion is RECOVERABLE from the record alone.
        assert "glossary_search" in recorded[0]["names"]
        assert "glossary_search" not in recorded[1]["names"]
        vanished = set(recorded[0]["names"]) - set(recorded[1]["names"])
        assert vanished == {"glossary_search"}

    def test_names_are_sorted_so_two_turns_are_comparable(self):
        """REJECTS: an unstable record. The live surface is built from a `set` iterated unsorted, so
        the same surface serializes differently between restarts — which would make two turns look
        different when nothing changed."""
        rec = AdvertisedToolsRecorder()
        rec.record_pass({"zeta_tool", "alpha_tool", "mid_tool"})
        assert rec.advertised_json()[0]["names"] == ["alpha_tool", "mid_tool", "zeta_tool"]

    def test_a_tool_free_pass_is_recorded_and_is_not_the_same_as_no_record(self):
        """REJECTS: fusing 'offered nothing' with 'never asked'. Only one of those is a defect, and
        a column that cannot tell them apart cannot report either."""
        never_asked = AdvertisedToolsRecorder()
        assert never_asked.advertised_json() is None, "no pass reached the model at all"

        offered_nothing = AdvertisedToolsRecorder()
        offered_nothing.record_pass([])
        recorded = offered_nothing.advertised_json()
        assert recorded is not None and recorded[0]["names"] == [] and recorded[0]["count"] == 0


# ── CP-0.2 · a withholding that does not register is a defect, not a policy ─────────────────────


class TestWithheldRegisters:
    def test_a_withholding_carries_who_decided_and_why(self):
        """REJECTS: a bare name list. 'glossary_search was dropped' is not actionable; the stage is
        what says which mechanism to go fix."""
        rec = AdvertisedToolsRecorder()
        rec.record_pass(["book_list"])
        rec.record_withheld("glossary_search", stage="failure_breaker", reason="gave up after 3")
        assert rec.withheld_json() == [{
            "tool": "glossary_search", "stage": "failure_breaker", "reason": "gave up after 3",
            # WHEN, not only who and why. Without it a verifier found 19 of 303 withheld tools also
            # advertised on every pass and could not tell a contradiction from a sequence — dropped
            # at activation then re-added later is coherent history, but only if it is timestamped.
            "pass": 2,
        }]

    def test_the_same_stage_dropping_a_tool_twice_is_one_withholding(self):
        """REJECTS: a count that measures how many passes the turn took rather than how much was
        narrowed. Five passes each dropping the same tool is one narrowing."""
        rec = AdvertisedToolsRecorder()
        for _ in range(5):
            rec.record_withheld("book_get", stage="rail_gate", reason="step satisfied")
        assert len(rec.withheld_json()) == 1

    def test_two_different_stages_dropping_the_same_tool_are_two_findings(self):
        """REJECTS: over-deduplication. Two mechanisms independently hiding the same tool is a
        different (and worse) fact than one mechanism doing it, and collapsing them hides the
        second mechanism entirely."""
        rec = AdvertisedToolsRecorder()
        rec.record_withheld("book_get", stage="rail_gate", reason="step satisfied")
        rec.record_withheld("book_get", stage="failure_breaker", reason="gave up")
        assert len(rec.withheld_json()) == 2


class TestBudgeterReportsWhatItDropped:
    """CP-0.2 at the source: the budgeter is where arm E's tool actually vanished."""

    CATALOG = [
        {"type": "function", "function": {"name": n, "description": "x" * 400,
                                          "parameters": {"type": "object", "properties": {}}}}
        for n in ("book_list", "book_read", "glossary_search", "kg_project_create")
    ]

    def test_dropped_names_are_returned_not_discarded(self):
        names = {"book_list", "book_read", "glossary_search", "kg_project_create"}
        kept, dropped = budget_names_by_tokens_ex(self.CATALOG, names, token_budget=200)
        assert dropped, "a budget this small MUST drop something, or the test proves nothing"
        assert set(kept) | set(dropped) == names, "every candidate is accounted for"
        assert not (set(kept) & set(dropped)), "a name cannot be both kept and dropped"

    def test_the_reporting_variant_does_not_change_what_is_kept(self):
        """REJECTS: the instrument moving the thing it measures. If adding the report changed the
        surface, every comparison against the frozen baseline would be against a different runtime.
        """
        names = {"book_list", "book_read", "glossary_search", "kg_project_create"}
        for budget in (150, 200, 400, 900, 10_000):
            plain = budget_names_by_tokens(self.CATALOG, names, token_budget=budget)
            kept, _ = budget_names_by_tokens_ex(self.CATALOG, names, token_budget=budget)
            assert kept == plain, f"kept set diverged at budget={budget}"


# ── CP-0.3 · our own prose is not a tool error ──────────────────────────────────────────────────


class TestToolCallSource:
    def test_an_unstamped_record_is_never_silently_called_a_tool(self):
        """REJECTS: the highest-consequence default in this checkpoint.

        A majority of what the model sees as a tool error is our own prose (recomputed 57.7%,
        2,315/4,010; the once-quoted 65.7% had no derivation and is withdrawn). Defaulting an
        unlabelled record to 'tool' would re-merge exactly those two populations and would do it
        invisibly — the split would still render, and it would be a fiction.
        """
        chunk = instrument.ensure_tool_call_instrumented(
            {"id": "1", "tool": "book_chapter_save_draft", "ok": False, "error": "nope"}
        )
        assert chunk["source"] != instrument.SOURCE_TOOL
        assert chunk["source"] == instrument.SOURCE_BREAKER
        assert chunk["source_inferred"] is True, "an inferred row must be distinguishable"

    def test_a_runtime_primitive_is_meta_and_meta_still_counts_as_not_a_tool(self):
        """REJECTS: a redefinition disguised as an improvement.

        `meta` is a reporting sub-class, never a deduction. The same 1,337 `tool_list`/`find_tools`
        failures the old runtime counted as tool errors become `meta` here — moving the class 33pp
        on IDENTICAL rows. Measuring the new runtime on `breaker` alone against a blended baseline
        would show a large win before a single request is served. The measured class is
        `source != 'tool'`, and this test pins `meta` inside it.
        """
        chunk = instrument.ensure_tool_call_instrumented({"id": "1", "tool": "tool_list"})
        assert chunk["source"] == instrument.SOURCE_META
        assert chunk["source"] != instrument.SOURCE_TOOL, (
            "meta must remain inside the 'not a real dispatch' class"
        )

    def test_an_explicit_stamp_is_never_overwritten_by_the_chokepoint(self):
        """REJECTS: the chokepoint second-guessing the dispatch site. Only the dispatch site knows
        that a tool really ran."""
        chunk = instrument.stamp_tool_call(
            {"id": "1", "tool": "tool_list"}, source=instrument.SOURCE_TOOL, latency_ms=42,
        )
        instrument.ensure_tool_call_instrumented(chunk)
        assert chunk["source"] == instrument.SOURCE_TOOL, "a real dispatch stays a real dispatch"
        assert chunk["latency_ms"] == 42
        assert "source_inferred" not in chunk

    def test_an_unknown_source_is_refused_at_the_stamp(self):
        with pytest.raises(ValueError):
            instrument.stamp_tool_call({"tool": "x"}, source="probably_fine")

    def test_declaration_identity_and_variant_ride_on_every_record(self):
        """REJECTS: the failure that makes the entire run unanswerable. Without these two fields the
        per-declaration matched-pair comparison cannot be computed AT ALL, however much traffic
        accumulates — the run would produce data that cannot answer its own question."""
        chunk = instrument.ensure_tool_call_instrumented({"id": "1", "tool": "book_list"})
        assert chunk["declaration"] == "book_list"
        assert chunk["runtime_variant"] == instrument.RUNTIME_LEGACY

    def test_a_consolidating_declaration_keeps_both_identities(self):
        """The migration's primary operation is consolidation — one new declaration superseding
        several legacy names. The join needs both halves or the pair cannot be matched."""
        chunk = instrument.stamp_tool_call(
            {"id": "1", "tool": "book_get"},
            source=instrument.SOURCE_TOOL,
            declaration="book_list",
            runtime_variant=instrument.RUNTIME_AGENTRUNTIME,
        )
        assert chunk["tool"] == "book_get" and chunk["declaration"] == "book_list"
        assert chunk["runtime_variant"] == instrument.RUNTIME_AGENTRUNTIME


# ── CP-0.4 · how the turn ended, on every terminal path ─────────────────────────────────────────


class TestOutcome:
    def test_cancellation_is_not_a_failure_and_has_its_own_state(self):
        """REJECTS: the defect that made this run's own baseline uninterpretable.

        'interrupted' fused 'the user changed their mind' with 'we lost the turn'. A metric holding
        both cannot move in a direction that means anything, so the fourth baseline class could not
        be read until cancel moved out.
        """
        assert instrument.OUTCOME_ABANDONED_BY_USER in instrument.OUTCOMES
        assert instrument.OUTCOME_ABANDONED_BY_USER != instrument.OUTCOME_FAILED
        assert instrument.OUTCOME_ABANDONED_BY_USER != instrument.OUTCOME_INTERRUPTED

    def test_asking_the_user_is_a_success_state(self):
        """REJECTS: scoring the behaviour we want as the defect. A model that stops to ask when it
        does not know is correct; counting that as failure would train the opposite."""
        assert instrument.OUTCOME_AWAITING_INPUT in instrument.OUTCOMES
        assert instrument.OUTCOME_AWAITING_INPUT != instrument.OUTCOME_FAILED

    def test_a_streaming_checkpoint_reads_back_as_crashed(self):
        """REJECTS: the optimistic default. A row still at 'streaming' means the process died before
        any terminal handler ran — nothing will ever come back to correct it. Reading it as anything
        successful produces the one kind of wrongness nobody investigates."""
        assert instrument.outcome_for_finish_reason("streaming") == instrument.OUTCOME_CRASHED

    def test_legacy_interrupted_is_not_retroactively_relabelled(self):
        """REJECTS: inventing a fact about historical rows. The old code wrote 'interrupted' for both
        a cancel and a lost turn, so those rows genuinely do not distinguish them. Mapping them to
        `abandoned_by_user` would manufacture a baseline that reads better than the truth."""
        assert instrument.outcome_for_finish_reason("interrupted") == instrument.OUTCOME_INTERRUPTED

    def test_an_unrecognised_finish_reason_never_reads_as_success(self):
        """REJECTS: an unhandled path scoring as completed — the fail-safe direction."""
        assert instrument.outcome_for_finish_reason("some_future_provider_word") != \
            instrument.OUTCOME_COMPLETED
        assert instrument.outcome_for_finish_reason(None) != instrument.OUTCOME_COMPLETED

    def test_an_error_is_failed_whatever_the_provider_said(self):
        assert instrument.outcome_for_finish_reason("stop", is_error=True) == \
            instrument.OUTCOME_FAILED

    def test_outcome_never_moves_without_finish_reason_moving_with_it(self):
        """REJECTS: a column that disagrees with its neighbour.

        Shipped once already: a statement set `finish_reason='interrupted'` on an abandoned suspend
        and left `outcome='awaiting_input'` — a SUCCESS state — on the same row, so an abandoned run
        counted as a turn that correctly stopped to ask. A missing value is a hole; a contradictory
        one answers confidently and wrongly, and nobody re-checks a column that has an answer.
        """
        src = _stream_src()
        # A window, not a quote-delimited match: these statements are built from adjacent Python
        # string literals, so a pattern that stops at the first quote reads only the fragment before
        # `'interrupted'` and reports every statement as broken. The window spans the whole clause.
        needle = "UPDATE chat_messages SET"
        start = 0
        checked = 0
        while (idx := src.find(needle, start)) != -1:
            stmt = src[idx: idx + 260]
            clause = stmt.split("WHERE")[0]
            if "finish_reason" in clause:
                checked += 1
                assert "outcome" in clause, (
                    f"this statement moves finish_reason without moving outcome: {clause!r}"
                )
            start = idx + len(needle)
        assert checked, "found no finish_reason UPDATE at all — the gate would pass vacuously"

    def test_the_vocabulary_matches_the_database_constraint(self):
        """REJECTS: the two halves drifting. The column has a CHECK constraint; a value this module
        can produce that the constraint rejects would fail the INSERT on a terminal path — i.e. lose
        the turn — and it would only ever show up in production."""
        import re
        from pathlib import Path
        ddl = Path(__file__).resolve().parents[1].joinpath("app/db/migrate.py").read_text(
            encoding="utf-8"
        )
        block = re.search(
            r"ADD COLUMN IF NOT EXISTS outcome TEXT\s*CHECK \(outcome IS NULL OR outcome IN\s*\((.*?)\)\)",
            ddl, re.S,
        )
        assert block, "the outcome CHECK constraint was not found — it must not be silently dropped"
        in_db = {v.strip().strip("'") for v in block.group(1).split(",")}
        assert in_db == set(instrument.OUTCOMES), (
            f"vocabulary drift: python={set(instrument.OUTCOMES) - in_db} db={in_db - set(instrument.OUTCOMES)}"
        )
