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

from app.services import instrument
from app.services.instrument import AdvertisedToolsRecorder
from app.services.tool_surface import budget_names_by_tokens, budget_names_by_tokens_ex


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
        rec.record_withheld("glossary_search", stage="failure_breaker", reason="gave up after 3")
        assert rec.withheld_json() == [
            {"tool": "glossary_search", "stage": "failure_breaker", "reason": "gave up after 3"}
        ]

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

        65.7% of what the model sees as a tool error is our own prose. Defaulting an unlabelled
        record to 'tool' would re-merge exactly those two populations and would do it invisibly —
        the split would still render, and it would be a fiction.
        """
        chunk = instrument.ensure_tool_call_instrumented(
            {"id": "1", "tool": "book_chapter_save_draft", "ok": False, "error": "nope"}
        )
        assert chunk["source"] != instrument.SOURCE_TOOL
        assert chunk["source"] == instrument.SOURCE_BREAKER
        assert chunk["source_inferred"] is True, "an inferred row must be distinguishable"

    def test_a_runtime_primitive_is_meta_not_a_tool_failure(self):
        """REJECTS: counting discovery calls as tool traffic. `tool_list` alone is 1,744 calls whose
        'failures' are our own breaker cap — folding those into a tool failure rate would swamp it.
        """
        chunk = instrument.ensure_tool_call_instrumented({"id": "1", "tool": "tool_list"})
        assert chunk["source"] == instrument.SOURCE_META

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
