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

import ast

import pytest

from pathlib import Path

from app.services import instrument
from app.services.instrument import AdvertisedToolsRecorder
from app.services.tool_surface import budget_names_by_tokens, budget_names_by_tokens_ex

#: The two gates in this file sweep a directory tree, and this names it. Both were moved here from
#: beside the arm-order gate so that everything which writes into the swept tree can derive its path
#: from the same constant the sweep uses.
#:
#: 🔴 **ROUTE SEVENTEEN, AND IT IS ABOUT THE FUTURE RATHER THAN THE PAST.** The sweep was a
#: **non-recursive** glob over two named directories, so a byte-identical entry point is discovered
#: under `app/services/` and **not discovered at all** under `app/agentruntime/` — the package CP-2
#: will put the new runtime's turn entry point in. The gate would have been green on the first turn
#: served by the thing this whole effort exists to build.
#:
#: `app/` recursively, with the directories that cannot host a turn named as exclusions, so a new
#: package is IN scope by default and leaving it out is a decision someone writes down.
_TURN_SCOPE_ROOT = "app"
_TURN_SCOPE_EXCLUDE = ("__pycache__",)

_APP = Path(__file__).resolve().parents[1] / _TURN_SCOPE_ROOT


def _swept_root() -> Path:
    """The directory **both gates actually sweep** — the one place a probe module may be written.

    🔴 **SIX ROUNDS: SIX PROBE WRITERS TYPED `"app"` WHILE BOTH GATES READ `_TURN_SCOPE_ROOT`.**
    Every one of the probe tests below is an experiment whose independent variable is *"a module
    appears inside the swept tree"* — and each of them named the tree by hand. Rename or re-root the
    scope and the gates follow it while every probe lands outside, so each of those tests goes green
    while asserting nothing at all. That is the failure mode this file convicts other people's gates
    of by name: **a file set that is TYPED OUT cannot notice the tree moving.**

    `test_EVERY_PROBE_IS_WRITTEN_INTO_THE_TREE_THE_GATES_ACTUALLY_SWEEP` holds it as a property, so
    the seventh writer cannot arrive typed.
    """
    return Path(__file__).resolve().parents[1] / _TURN_SCOPE_ROOT


def _probe_offender(where: str, stem: str) -> str:
    """A `pytest.raises(match=…)` pattern that only THIS probe's offender line can satisfy.

    🔴 **THE THREE WEAK ORACLES, EIGHT ROUNDS.** All three terminal-write probe tests asserted
    `match="withheld_tools"`, and the terminal-write gate carries that word in **three of its four
    assertions** — the named-writer subset check, the `>= 4` anchor check and the offender list. So
    each of those tests passed when its probe was caught, and passed identically when the gate broke
    for a reason having nothing to do with the probe: *"a red happened"* is not *"my experiment
    fired"*. The gate's own anchor assertion exists precisely because it can stop matching, and the
    tests over it could not have noticed.

    🔴 **AND THE FIRST VERSION OF THIS HELPER WAS STILL NOT AN ORACLE.** Matching the probe's module
    path alone narrowed three assertions to two, not to one: `binds_checked` is a list of the same
    `mod::fn:line` strings, so the ANCHOR assertion (*"only N bind(s) were found"*) renders the
    probe's path as well. Driven: with the anchor's threshold raised so it fails for a reason having
    nothing to do with any probe, all three tests stayed **green** — the same result the old oracle
    gave, which is the whole defect one step smaller. So the pattern carries the offender sentence
    too, and that sentence exists in exactly one assertion.
    """
    import re as _re
    return (_re.escape(f"{where}/{stem}.py::")
            + r"\S+ writes .withheld_tools. and NO argument")


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
        # Any CALL FORM, not just the `=` assignment. The prior version forbade
        # "= budget_names_by_tokens(" only, so `return budget_names_by_tokens(...)` slipped through
        # — the boundary was drawn around one syntax rather than around the function.
        import re as _re
        for name, src in (("stream_service", _stream_src()), ("tool_surface", _surface_src())):
            # Any call form — but not the definition itself, and not the `_ex` sibling.
            calls = [
                m for m in _re.finditer(r"(?<![_\w])budget_names_by_tokens\(", src)
                if not src[max(0, m.start() - 4): m.start()].endswith("def ")
            ]
            assert not calls, (
                f"{name}: {len(calls)} production call(s) to the variant that discards its drops"
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

        # DO NOT ARM THE SINK HERE. The previous version of this test called
        # `surface_withheld.set(...)` itself — supplying the exact precondition production was
        # failing to supply — so it passed while the real path recorded nothing. A behavioural gate
        # that stages its own precondition is a source gate wearing a costume.
        #
        # The ordering half of this gate — "armed by production code that runs BEFORE the
        # narrowing" — used to live here as a 900-character substring window around one call site.
        # It is now `TestTheTurnSinkIsArmedBeforeAnythingNarrows`, which compares line numbers in the
        # parse tree instead. The window was what let the seventh recurrence ship: it was satisfied
        # by an arming 380 lines below the catalogue fetch, because the fetch was not the call the
        # window was drawn around.

        sink: list[dict] = []
        token = _inst.surface_withheld.set(sink)
        try:
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

    def test_every_assistant_row_insert_anywhere_writes_an_outcome(self):
        """REJECTS: a whole pipeline invisible to the column whose premise is 'every terminal path'.

        Two terminal paths wrote assistant rows with no outcome and went unnoticed for three rounds:
        the VOICE pipeline (`voice_stream_service.py`) and the PROACTIVE check-in
        (`routers/internal.py`). Neither is exotic and neither is deferred anywhere — they were
        simply in files the instrument was not built in, and every gate I wrote read only the file
        it was built in.

        So this one scans the WHOLE app package. The unit is "an INSERT that creates an assistant
        row", wherever it lives, because that is the actual population the claim is about.
        """
        offenders = []
        for path in sorted(_APP.rglob("*.py")):
            src = path.read_text(encoding="utf-8")
            start = 0
            while (idx := src.find("INSERT INTO chat_messages", start)) != -1:
                stmt = src[idx: idx + 1400]
                # Match the COLUMN LIST ONLY — the parenthesised names before VALUES — not the
                # surrounding text. The first version of this gate scanned a 1400-char window and
                # was satisfied by a COMMENT containing the word "outcome", so removing the column
                # left it green. That is the third time a gate of mine has matched prose instead of
                # code, and it is why the window is now bounded by the statement's own syntax.
                head = stmt.split("VALUES", 1)[0]
                cols = head[head.find("(") + 1: head.rfind(")")] if "(" in head else ""
                cols = " ".join(line.split("--")[0] for line in cols.splitlines())
                # Only statements that create an ASSISTANT row; a user-message INSERT has no outcome
                # to carry, and demanding one would be a gate that cannot be satisfied.
                if "'assistant'" in stmt and "outcome" not in cols:
                    offenders.append(f"{path.name}:{src.count(chr(10), 0, idx) + 1}")
                start = idx + 1
        assert not offenders, (
            f"assistant-row INSERT(s) with no outcome column: {offenders}. Every terminal path that "
            f"writes a row must record how the turn ended, in whatever file it happens to live."
        )

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
            # F-48 — WHO WROTE IT. Not decoration either: the persistence merge replaces a
            # segment's own contribution and leaves every other segment alone, so an entry that
            # does not name its writer falls back to append-only and is duplicated by the next
            # checkpoint. Asserted against `rec.segment` rather than a literal, so the value stays
            # opaque while the binding stays exact.
            "segment": rec.segment,
            # WHICH QUESTION this row answers. §0.14.3 specifies a `declaration` row and the column
            # never carried one — `scope` was on the sink's rows and not on the persisted ones, so a
            # reader could not tell a per-declaration narrowing from a scope-less legacy row.
            "scope": instrument.SCOPE_DECLARATION,
            "tool": "glossary_search", "stage": "failure_breaker", "reason": "gave up after 3",
            # WHEN, not only who and why. Without it a verifier found 19 of 303 withheld tools also
            # advertised on every pass and could not tell a contradiction from a sequence — dropped
            # at activation then re-added later is coherent history, but only if it is timestamped.
            # The pass it APPLIES TO — the one just recorded. `len + 1` was measured off by one
            # against five live removals (dropped at 6, stamped 7), which made a withholding look
            # simultaneous with an advertisement it had actually preceded.
            "pass": 1,
        }]

    def test_a_withholding_belongs_to_the_pass_it_shaped_not_the_next_one(self):
        """REJECTS: the off-by-one that made the `pass` field decorative.

        Measured live: a tool removed from pass 6 was stamped 7, consistently across five removals.
        An entry stamped one pass late reads as simultaneous with an advertisement it preceded —
        which is exactly the contradiction the field exists to resolve, so the stamp was worse than
        no stamp: it looked like an answer.
        """
        rec = AdvertisedToolsRecorder()
        rec.record_pass(["a", "b"])                      # pass 1
        rec.record_pass(["a"])                           # pass 2 — 'b' removed here
        rec.record_withheld("b", stage="failure_breaker", reason="gave up")
        assert rec.withheld_json()[0]["pass"] == 2, "belongs to the pass it shaped"

        # A narrowing recorded when NO pass has happened yet is stamped None, not 1 — fabricating a
        # pass that never existed is strictly worse than admitting none.
        #
        # ATTRIBUTION CORRECTED: an earlier version of this comment blamed `max(len,1)` for 145 live
        # records. Those are pass 3 on 2-pass turns (the earlier `len+1` era), not pass 1 on turns
        # that never advertised. This assertion is a correctness floor, not a fix for those rows —
        # and the branch is unreachable in production, since both call sites run after `record_pass`.
        pre = AdvertisedToolsRecorder()
        pre.record_withheld("c", stage="hot_seed", reason="budget")
        assert pre.withheld_json()[0]["pass"] is None, (
            "a narrowing with no pass recorded must say so, not claim pass 1"
        )

    def test_the_same_stage_dropping_a_tool_twice_is_one_withholding(self):
        """REJECTS: a count that measures how many passes the turn took rather than how much was
        narrowed. Five passes each dropping the same tool is one narrowing."""
        rec = AdvertisedToolsRecorder()
        for _ in range(5):
            rec.record_withheld("book_get", stage="rail_gate", reason="step satisfied")
        assert len(rec.withheld_json()) == 1

    def test_a_tool_the_model_could_see_is_not_reported_as_withheld(self):
        """REJECTS: the contradiction three live rounds found and no timestamp could fix.

        The same eleven tools were recorded as withheld while advertised on EVERY pass — 6.3%,
        6.2%, 6.2% across rounds 2-4, the same names each time. It is not a sequencing error: an
        intermediate stage really did drop the tool and a later stage really did put it back (the
        always-hot write allowlist does exactly this). The stage's decision was real; the CLAIM was
        false, because the model could see the tool.

        A consumer asking "what was hidden from the model?" must be able to trust the answer without
        re-deriving it against advertised_tools — otherwise the column is a log line with a schema.
        """
        rec = AdvertisedToolsRecorder()
        rec.record_pass(["book_list", "glossary_search"])
        # A stage drops it; a later stage restores it — the model ends up holding it.
        rec.record_withheld("glossary_search", stage="hot_seed", reason="did not fit the budget")
        rec.record_withheld("kg_project_create", stage="hot_seed", reason="did not fit the budget")

        withheld = rec.withheld_json() or []
        names = {w["tool"] for w in withheld}
        assert "glossary_search" not in names, (
            "a tool present in the pass's advertised set was still reported as withheld"
        )
        assert "kg_project_create" in names, (
            "a genuinely absent tool must still be reported — the reconciliation must not swallow "
            "real withholdings"
        )

    def test_a_real_withholding_survives_the_reconciliation(self):
        """REJECTS: two defensible mechanisms that are silently destructive together.

        The advertised-set reconciliation drops an entry whose tool was in fact advertised. The
        (tool, stage) dedupe was first-wins across the whole turn. Together they DELETED A TRUE
        WITHHOLDING: dropped on pass 1 but restored (so reconciled away), then genuinely gone on
        pass 2 — and the pass-2 entry was suppressed as a duplicate of the one already deleted, so
        the column recorded nothing at all.
        """
        rec = AdvertisedToolsRecorder()
        rec.record_pass(["book_list", "glossary_search"])          # pass 1 — restored, so visible
        rec.record_withheld("glossary_search", stage="hot_seed", reason="budget")
        rec.record_pass(["book_list"])                             # pass 2 — genuinely gone
        rec.record_withheld("glossary_search", stage="hot_seed", reason="budget")

        withheld = rec.withheld_json() or []
        assert any(w["tool"] == "glossary_search" and w["pass"] == 2 for w in withheld), (
            "a tool genuinely absent on pass 2 was not recorded — the pass-1 reconciliation and the "
            "turn-wide dedupe destroyed it between them"
        )

    def test_dedupe_never_collapses_two_different_calls(self):
        """REJECTS: an under-count shipped while fixing an over-count.

        The first key omitted `args`, so `book_read(chapter=1)` and `book_read(chapter=2)` — two
        real, different calls in one iteration — collapsed to one. An under-count moves a failure
        RATE in the flattering direction, exactly like the over-count it replaced, and is harder to
        notice because the row simply is not there.
        """
        calls = [
            {"iteration": 3, "tool": "book_read", "args": {"chapter": 1}, "ok": True,
             "source": "tool", "error": None},
            {"iteration": 3, "tool": "book_read", "args": {"chapter": 2}, "ok": True,
             "source": "tool", "error": None},
        ]
        assert len(instrument.dedupe_recorded_calls(calls)) == 2, (
            "two genuinely different calls were collapsed into one"
        )
        # A true duplicate — same everything — still collapses.
        dup = [dict(calls[0]), dict(calls[0])]
        assert len(instrument.dedupe_recorded_calls(dup)) == 1

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
        # Three of the four CP-0 columns had NO existence assertion anywhere: deleting their
        # ADD COLUMN lines left every gate green. A vocabulary check over one column is not a
        # schema check.
        for _col in ("advertised_tools", "withheld_tools", "runtime_variant", "outcome"):
            assert f"ADD COLUMN IF NOT EXISTS {_col}" in ddl, (
                f"chat_messages.{_col} has no DDL — the instrument cannot record into a column "
                f"that is never created"
            )
        in_db = {v.strip().strip("'") for v in block.group(1).split(",")}
        assert in_db == set(instrument.OUTCOMES), (
            f"vocabulary drift: python={set(instrument.OUTCOMES) - in_db} db={in_db - set(instrument.OUTCOMES)}"
        )


class TestF19NormalTerminationsAreNotInterrupted:
    """REJECTS: a fail-safe applied where the path is already classified.

    My fix for one constant shipped a regression in a live population. The `case _` default sends
    unrecognised provider words to `interrupted` — correct for an UNCLASSIFIED path, wrong on the
    clean-finish path where the turn demonstrably ended normally. Anthropic always receives
    `max_tokens`, so `length` is a routine truncation; mapping it to the deprecated bucket INFLATED
    the one metric CP-0 exists to drive to zero, from inside a fix for something else.
    """

    def test_a_truncated_turn_completed(self):
        assert instrument.outcome_for_finish_reason("length") == instrument.OUTCOME_COMPLETED

    def test_a_turn_that_stopped_to_call_tools_completed(self):
        assert instrument.outcome_for_finish_reason("tool_calls") == instrument.OUTCOME_COMPLETED

    def test_a_refusal_is_failed_not_interrupted(self):
        """`content_filter` means the request was NOT carried out — a failure, not a lost turn.
        Three provider words with three meanings; the fail-safe collapsed them into a fourth."""
        assert instrument.outcome_for_finish_reason("content_filter") == instrument.OUTCOME_FAILED

    def test_a_genuinely_unknown_word_still_fails_safe(self):
        """The fail-safe must survive the fix — an unrecognised word is still not a success."""
        assert instrument.outcome_for_finish_reason("some_future_word") == \
            instrument.OUTCOME_INTERRUPTED
        assert instrument.outcome_for_finish_reason(None) != instrument.OUTCOME_COMPLETED


class TestF45TheVocabularyCannotFORKAgain:
    """F-45 — a value one site writes and no reader knows.

    `resolve_expired_suspends` began writing `finish_reason='abandoned_expired'` in the SAME COMMIT
    that taught the class-4 baseline metric to read `finish_reason='awaiting_input'`. Each half was
    a correct fix; together they cancelled, because the sweep eliminated the exact state the metric
    had just learned to recognise. Every swept row then counted as `unrecorded` — the number CP-0
    exists to drive to zero — and the frozen 0.0% held only because its rows had been swept by the
    PREVIOUS build. The figure would have drifted upward with no code change at all.

    Three readers gave three answers for one row. These gates make the fork impossible rather than
    unlikely: the vocabulary is declared once, and both the writers and the readers are checked
    against the declaration.
    """

    def test_the_swept_row_reads_the_same_way_through_the_shim(self):
        """REJECTS the third verdict. Before this, `abandoned_expired` fell to `case _` and read
        `interrupted` — so the shim and the sweep disagreed about a row the sweep had just written.
        """
        assert instrument.outcome_for_finish_reason("abandoned_expired") == \
            instrument.OUTCOME_ABANDONED_BY_USER

    def test_every_finish_reason_this_codebase_WRITES_is_declared(self):
        """The gate that would have caught F-45 the day it shipped.

        A literal assigned under `app/` and absent from `KNOWN_FINISH_REASONS` is a word invented by
        a write path that no reader has been taught. Provider words are exempt by construction —
        they arrive from outside and the fallback exists for them — which is why the declaration is
        split into `_PROVIDER` and `_OURS` rather than being one bag.
        """
        import re as _re
        written: set[str] = set()
        for path in sorted(_APP.rglob("*.py")):
            src = path.read_text(encoding="utf-8")
            for m in _re.finditer(r"""finish_reason\s*=\s*['"]([a-z_]+)['"]""", src):
                written.add(m.group(1))
        undeclared = written - instrument.KNOWN_FINISH_REASONS
        assert not undeclared, (
            f"finish_reason value(s) written but declared nowhere: {sorted(undeclared)}. "
            f"Add them to instrument.FINISH_REASONS_OURS and teach every reader — a value one site "
            f"writes and no reader knows is F-45."
        )

    def test_every_declared_value_maps_to_a_real_outcome(self):
        """A declared word must resolve through the shim to something in the CP-0 vocabulary. The
        declaration is not a comment: if adding a value here does not force a decision about what it
        MEANS, it is bookkeeping."""
        for fr in sorted(instrument.KNOWN_FINISH_REASONS):
            assert instrument.outcome_for_finish_reason(fr) in set(
                instrument.__dict__[k] for k in dir(instrument) if k.startswith("OUTCOME_")
            ), f"{fr!r} does not map to a CP-0 outcome"

    def test_ours_and_provider_do_not_overlap(self):
        """An overlap would let a value be treated as externally-supplied (exempt from the write
        gate) while this codebase is the thing writing it — the exemption swallowing the rule."""
        assert not (instrument.FINISH_REASONS_OURS & instrument.FINISH_REASONS_PROVIDER)

    def test_the_class_4_metric_no_longer_pins_outcome_to_one_finish_reason(self):
        """REJECTS the defective half directly, in the artifact where it lived.

        `WHEN m.outcome IS NOT NULL AND m.finish_reason = 'awaiting_input'` made a class named
        *"turns with no recorded outcome"* depend on a vocabulary it does not own. A row that HAS an
        outcome cannot belong to that class, whatever word sits beside it.
        """
        sql = (Path(__file__).resolve().parents[3] / "contracts" / "agent-runtime-baseline"
               / "baseline-metrics.sql").read_text(encoding="utf-8")
        assert "WHEN m.outcome IS NOT NULL THEN m.outcome" in sql, (
            "class 4 must read `outcome` unconditionally, not for one finish_reason"
        )
        assert "m.outcome IS NOT NULL AND m.finish_reason" not in sql, (
            "class 4 still pins the outcome branch to a finish_reason literal — F-45's mechanism"
        )

    def test_the_clean_finish_writes_both_fields_from_one_signal(self):
        """REJECTS: a row that contradicts itself. Pinning finish_reason='stop' while outcome
        varied left a reader unable to tell which half to believe — worse than either being wrong.
        """
        src = _stream_src()
        assert "finish_reason = EXCLUDED.finish_reason" in src
        assert "$15, 'stop'," not in src, "the clean-finish INSERT still pins a literal 'stop'"


class TestP3EveryTerminalPathRecordsAnOutcome:
    """P3 — the property claim's third invariant, falsified by ONE unrecorded terminal path.

    Two paths recorded nothing at all: a cancel before the first token, and a process death before
    any checkpoint. I deferred both on the assumption that an outcome needs an ASSISTANT row, and
    that writing one means a blank bubble. The assumption was wrong — `outcome` is a column on
    `chat_messages`, not a property of a role, and the USER's row already exists for exactly these
    turns. That is what makes them orphaned rather than absent.
    """

    def test_the_empty_turn_path_stamps_the_user_row_rather_than_recording_nothing(self):
        src = _stream_src()
        skip = src.index("if not content and not reasoning and not tool_calls_history:")
        window = src[skip: skip + 4200]
        assert "UPDATE chat_messages SET outcome" in window, (
            "an empty terminal turn still records nothing — P3 is falsified by this path alone"
        )
        assert "outcome IS NULL" in window, (
            "the stamp must not overwrite an outcome a later path already recorded"
        )
        # It must anchor on the SESSION, not on parent_message_id. Measured live: that id is a
        # UUIDv4 present in no row on this path, so the UPDATE matched nothing — 0 of 3,154 user
        # rows carried an outcome — while the log reported "no parent to stamp". The guard reported
        # the absence of a row it had failed to look for.
        assert "role = 'user'" in window and "session_id = $1" in window, (
            "the orphan stamp must find the user row by session; parent_message_id does not "
            "resolve on this path"
        )
        assert "RETURNING message_id" in window, (
            "the stamp must report whether it actually matched a row, or a silent no-op reads as "
            "a success — which is exactly how this shipped broken the first time"
        )

    def test_the_orphan_stamp_derives_its_value_and_never_asserts_one(self):
        """The same discipline as every other outcome site: derived from the signal, never a
        literal. Four defects in this checkpoint were confident values for unobserved things."""
        src = _stream_src()
        skip = src.index("if not content and not reasoning and not tool_calls_history:")
        window = src[skip: skip + 4200]
        assert "instrument.outcome_for_finish_reason(" in window
        assert "_orphan_outcome = outcome or" in window, (
            "an explicitly-passed outcome must win over the derived fallback"
        )


class TestP1TheCandidateSelectionRegisters:
    """P1 — falsified live at 237 of 315 tools in neither bucket, and this is why.

    Every narrowing previously instrumented sits BELOW domain selection. The stage that decides
    which domains are candidates at all sat above them and registered nothing — and it is
    query-dependent, so the surface silently differs between two messages by 17 tool names.

    The decisive live case: `world_map_create` absent from both records at passes 1-2, then
    carrying a `token_budget` withheld record at pass 3 — the runtime's own record proving it had
    been a candidate all along.
    """

    def test_tools_outside_the_hot_domains_register_as_withheld(self):
        from app.services import instrument as _inst
        from app.services.tool_surface import SessionToolPins, discovery_seed_for_surface

        catalog = [
            {"type": "function", "function": {"name": n, "description": "d",
                                              "parameters": {"type": "object", "properties": {}}}}
            for n in ("book_read", "book_list", "world_map_create", "translation_job_status")
        ]
        # DO NOT PASS withheld_sink. Neither production call site does — both rely on the
        # ContextVar fallback — so a gate that passes it explicitly stages the exact precondition
        # production fails to supply, and deleting the fallback leaves it GREEN. That is the fifth
        # recurrence of this one defect, and it is written as a warning in the sibling gate's
        # docstring nine lines above. Exercise the path production actually takes.
        sink: list[dict] = []
        token = _inst.surface_withheld.set(sink)
        try:
            discovery_seed_for_surface(
                catalog,
                pins=SessionToolPins(effective_enabled=[], effective_skills=[],
                                     curated_mode=False,
                                     activation_state={"activated_tools": [], "dirty": False}),
                editor=False, book_scoped=True,
            )
        finally:
            _inst.surface_withheld.reset(token)
        stages = {e["stage"] for e in sink}
        assert "domain_not_selected" in stages, (
            "the largest narrowing in the system still registers nothing — it does not look like "
            "a filter, it looks like a set being built, which is why it was the last one found"
        )
        for e in sink:
            if e["stage"] == "domain_not_selected":
                assert e["tool"] and e["reason"], "a withholding needs its tool and its reason"

    def test_it_names_the_hot_set_that_excluded_them(self):
        """The reason must say WHICH hot set excluded the tool. 'not selected' alone cannot be
        acted on; the domain list is what makes the narrowing reviewable."""
        src = _surface_src()
        assert "domain not in this turn's hot set" in src
        assert "', '.join(sorted(hot_domains))" in src, (
            "the reason must carry the domains, or the record cannot be reconciled against a "
            "query-dependent surface"
        )


class TestP2SourceIsAssignedStructurally:
    """P2 — a call's `source` is assigned structurally, never inferred.

    RED, and this gate exists to keep it measurable rather than asserted. Live: 110 of 201 recorded
    calls carry `source_inferred`, meaning the chokepoint classified them by name rather than the
    mint site declaring what it was.

    The distinction that matters, and why the residual is not simply a bug: `source='tool'` IS
    structural today — assigned at the two sites where a dispatch really runs, so it can never be
    inferred onto something that did not dispatch. What remains inferred is the meta/breaker SPLIT,
    decided by a lookup over a closed set of primitive names this service defines. That is not a
    guess about prose, but it is not the mint site declaring itself either.

    Closing it means classifying ~29 mint sites individually. That is a mechanical change to the
    tool loop, and this checkpoint has twice produced regressions from large edits made at the end
    of a long pass — the voice initialiser that broke nine tests, and F-19, which inflated the very
    metric CP-0 exists to drive down. So it is scoped, gated, and left for a pass with room to
    verify it.
    """

    def test_the_tool_half_of_the_split_is_structural_and_cannot_be_inferred(self):
        """The load-bearing half holds: nothing can acquire `tool` except by passing a dispatch."""
        chunk = instrument.ensure_tool_call_instrumented(
            {"id": "1", "tool": "book_read", "ok": False, "error": "x"}
        )
        assert chunk["source"] != instrument.SOURCE_TOOL
        assert chunk["source_inferred"] is True

    def test_an_inferred_row_is_always_marked_as_inferred(self):
        """P2's residual must stay COUNTABLE. An inferred row that does not say so is
        indistinguishable from a declared one, and the gap stops being measurable."""
        for name, expected in (("tool_list", instrument.SOURCE_META),
                               ("glossary_propose_entities", instrument.SOURCE_BREAKER)):
            c = instrument.ensure_tool_call_instrumented({"id": "1", "tool": name})
            assert c["source"] == expected
            assert c.get("source_inferred") is True, (
                f"{name} was classified without marking itself inferred — P2's residual becomes "
                f"invisible the moment an inferred row looks declared"
            )

    def test_a_declared_source_never_acquires_the_inferred_mark(self):
        c = instrument.stamp_tool_call({"id": "1", "tool": "tool_list"},
                                       source=instrument.SOURCE_META)
        instrument.ensure_tool_call_instrumented(c)
        assert "source_inferred" not in c


class TestP1TheLastTwoUnregisteredNarrowings:
    """P1's deterministic residual — 4 of 315, the same four in both live runs.

    They cleared domain selection (their domain WAS in the hot set) and vanished between there and
    the wire. Two narrowings lived in four lines of the advertise loop, both downstream of every
    stage previously instrumented:

      * a name in the ACTIVE SET with no catalog entry — `_add(None)` returns at its first line,
        so the tool leaves the wire without a word. Deterministic, because a catalog miss is a
        property of the CATALOG rather than of the query, which is exactly why the residual was the
        same four tools both times.
      * ask/plan mode dropping every non-tier-R tool. The permission-mode registration at the
        advertise chokepoint covers the other branch only, so on a discovery surface this
        registered nowhere.
    """

    def test_both_narrowings_register(self):
        src = _stream_src()
        for stage in ("catalog_miss", "permission_tier"):
            assert f'stage="{stage}"' in src, f"{stage} narrowing still silent"

    def test_the_catalog_miss_registers_before_the_early_return_swallows_it(self):
        """REJECTS: registering AFTER the `continue`. `_add(None)` returns at its first line, so a
        record placed downstream of it never runs — the failure mode that made this invisible."""
        src = _stream_src()
        i = src.index("        td = catalog_index.get(name)")
        window = src[i: i + 1800]
        miss = window.index('stage="catalog_miss"')
        cont = window.index("continue", miss)
        assert miss < cont, "the record must be written before control leaves the branch"

    def test_a_registered_narrowing_names_what_excluded_it(self):
        """`reason` must be actionable. 'dropped' cannot be acted on; 'absent from the catalog
        index' and the tier name both point at where to look."""
        src = _stream_src()
        assert "absent from this turn's catalog index" in src
        assert "not offered in restricted mode" in src


class TestP3TheKillPathReconciler:
    """P3's kill path. These gates CALL the function — the previous four were
    `inspect.getsource` substring counts, and none of them ran it.

    The measured consequence: deleting `await reconcile_crashed_turns(pool)` from main.py left the
    caller test GREEN, because `from ... import reconcile_crashed_turns` supplied both the substring
    AND the ordering. The gate named `sweep_expired_runs` as the state it rejects — zero callers,
    docstring claiming otherwise — while sitting in exactly that state. Substring gates cannot tell
    an import from a call.
    """

    def test_main_awaits_it_rather_than_merely_importing_it(self):
        """REJECTS an import satisfying a caller check. Matches the AWAIT, not the name."""
        import re as _re
        main = (_APP / "main.py").read_text(encoding="utf-8")
        assert _re.search(r"await\s+reconcile_crashed_turns\s*\(", main), (
            "no awaited call — an import is not a caller, which is the exact state this gate was "
            "written to reject and was itself in"
        )

    async def _run(self, pool):
        return await instrument.reconcile_crashed_turns(pool)

    def test_it_executes_and_reports_what_it_stamped(self):
        """RUNS it against a stub connection, asserting the SQL it issues and the counts it
        returns. A short-circuited body, an inverted predicate and a flipped outcome all go red
        here; none of them moved the substring gates."""
        import asyncio

        issued: list[tuple] = []

        class _Conn:
            async def fetchval(self, sql, *args):
                issued.append((sql, args))
                return 3

        class _Acquire:
            async def __aenter__(self): return _Conn()
            async def __aexit__(self, *a): return False

        class _Pool:
            def acquire(self): return _Acquire()

        out = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            self._run(_Pool())
        )
        assert out["assistant"] == 3, "it must report what it stamped, not a hardcoded zero"
        assert issued, "the function issued no SQL — a short-circuited body passes every substring gate"
        sql, args = issued[0]
        assert instrument.OUTCOME_CRASHED in args, "the outcome must be bound, not spelled inline"
        assert "outcome IS NULL" in sql, "it must never overwrite a recorded outcome"
        assert "outcome_source = 'reconciler'" in sql, "a swept row must be distinguishable"
        assert "now() - interval" in sql, (
            "the age bound must SUBTRACT — inverting it to now() + interval claims live turns"
        )
        assert "finish_reason = 'streaming'" in sql, (
            "it must act only on the evidence-bearing shape"
        )

    def test_it_no_longer_guesses_at_user_rows(self):
        """REJECTS the branch that fired without evidence: a user deleting an assistant reply had
        their own row stamped `crashed` at next boot, irreversibly, no race required."""
        import inspect
        src = inspect.getsource(instrument.reconcile_crashed_turns)
        assert "role = 'user'" not in src, (
            "the evidence-free user-row branch is back — it cannot tell a crash from a deletion"
        )


class TestTheReconcilerCannotImpersonateATerminalPath:
    """P3's provenance — the finding that a repair which cannot be told from the thing it repairs
    makes the property it 'satisfies' unfalsifiable.

    Measured: the sweep stamped 223 rows back to 2026-04-03, and with ONE `outcome` column a
    reader could not distinguish "the terminal path recorded this" from "a startup sweep guessed
    it three days later". P3 then read as satisfied because the record was repaired instead of the
    path. A sweep is not a terminal path.
    """

    def test_a_swept_row_is_distinguishable_from_a_path_recorded_one(self):
        import inspect
        src = inspect.getsource(instrument.reconcile_crashed_turns)
        assert src.count("outcome_source = 'reconciler'") >= 1, (
            "the sweep must mark its own writes, or P3 becomes unfalsifiable"
        )
        ddl = (_APP / "db" / "migrate.py").read_text(encoding="utf-8")
        assert "ADD COLUMN IF NOT EXISTS outcome_source" in ddl
        assert "'path', 'reconciler'" in ddl, "the vocabulary must be closed"

    def test_it_acts_only_where_evidence_exists(self):
        """The session-continued guard is gone because the branch needing it is gone.

        86 of 223 swept rows sat in sessions with LATER activity, and a delete of an assistant
        reply produced the same shape as a crash. Rather than add a third guard to a branch that
        could not tell them apart, the branch was removed. What remains acts on
        `finish_reason='streaming'` — written by exactly ONE site — and is currently VACUOUS,
        which is the honest state: the dying process now records its own outcome, so the sweep
        drains the pre-CP-0 backlog once and then stamps nothing."""
        import inspect
        src = inspect.getsource(instrument.reconcile_crashed_turns)
        assert "finish_reason = 'streaming'" in src, "the evidence-bearing shape must remain"
        assert "role = 'user'" not in src, "the evidence-free branch must stay removed"

    def test_the_fingerprint_does_not_hash_a_column_no_class_reads(self):
        """REJECTS: a pin breakable WITHOUT TRAFFIC. Hashing `outcome` meant a startup sweep
        invalidated the freeze while every published number stayed identical — round 3's
        'fingerprint was theatre' defect inverted: covering more than the numbers depend on turns
        an unrelated write into a false drift signal."""
        from pathlib import Path as _P
        sql = (_P(__file__).resolve().parents[3] / "contracts" / "agent-runtime-baseline"
               / "baseline-metrics.sql").read_text(encoding="utf-8")
        pin = sql[sql.index("corpus_md5"):sql.index("== 0 ·")] if "== 0 ·" in sql else sql
        assert "coalesce(outcome,'')" not in pin, (
            "the fingerprint still hashes `outcome`, which no class reads"
        )


class TestP1TheIntentGateRegisters:
    """P1's seventh and most upstream frame — a drop at CATALOG ASSEMBLY.

    A verifier's accounting landed on this exact set twice: the four tools in neither bucket are
    `INTENT_GATED_SETUP_TOOLS` minus the one a rail exempted. `catalog_miss` could never see them,
    because they ARE in the catalog index — they are removed from the catalog handed to it.

    A narrowing this early is the easiest to mistake for "not a candidate". It IS a candidate: the
    gate exists because these tools would otherwise be offered, and one injected skill makes them
    appear. That distinction — "the runtime chose not to offer this, and here is why" versus "this
    tool does not exist" — is the whole of P1.
    """

    def test_the_gate_registers_what_it_drops(self):
        from app.services import instrument as _inst
        from app.services.tool_discovery import (
            INTENT_GATED_SETUP_TOOLS, filter_intent_gated_setup_tools,
        )
        catalog = [
            {"type": "function", "function": {"name": n, "description": "d",
                                              "parameters": {"type": "object", "properties": {}}}}
            for n in sorted(INTENT_GATED_SETUP_TOOLS) + ["book_read"]
        ]
        sink: list[dict] = []
        token = _inst.surface_withheld.set(sink)
        try:
            kept = filter_intent_gated_setup_tools(catalog, injected_skill_codes=[])
        finally:
            _inst.surface_withheld.reset(token)

        assert len(kept) < len(catalog), "the gate must actually drop something here"
        names = {e["tool"] for e in sink if e["stage"] == "intent_gate"}
        assert names == set(INTENT_GATED_SETUP_TOOLS), (
            f"registered {names}, expected every gated tool it removed"
        )
        assert all(e["reason"] for e in sink), "a withholding without a reason cannot be acted on"

    def test_a_rail_exempted_tool_is_neither_dropped_nor_registered(self):
        """REJECTS over-registration: a tool the rail exempts is still OFFERED, so recording it as
        withheld would be the advertised-and-withheld contradiction in a new place."""
        from app.services import instrument as _inst
        from app.services.tool_discovery import filter_intent_gated_setup_tools
        catalog = [
            {"type": "function", "function": {"name": "glossary_plan", "description": "d",
                                              "parameters": {"type": "object", "properties": {}}}}
        ]
        sink: list[dict] = []
        token = _inst.surface_withheld.set(sink)
        try:
            kept = filter_intent_gated_setup_tools(
                catalog, injected_skill_codes=[], rail_step_tools={"glossary_plan"},
            )
        finally:
            _inst.surface_withheld.reset(token)
        assert len(kept) == 1, "a rail-exempted tool stays in the catalog"
        assert not sink, "and must NOT be recorded as withheld — it was offered"


class TestExpiredSuspendsAreResolved:
    """CP-0.4 — `awaiting_input` on a turn whose run has expired is a SUCCESS LABEL ON A DEAD TURN.

    Measured: 5 of 8 such rows can never receive input. `load_suspended_run` filters on
    `expires_at > now()`, so once the run expires the card is unreachable — while the message still
    advertises `awaiting_input`, which this module classifies as a success state.

    These gates CALL the function. Four earlier reconciler gates were substring counts and none ran
    it; deleting its caller left them green.
    """

    def test_it_is_wired_with_an_await_not_merely_imported(self):
        import re as _re
        main = (_APP / "main.py").read_text(encoding="utf-8")
        assert _re.search(r"await\s+resolve_expired_suspends\s*\(", main), (
            "an import is not a caller — `sweep_expired_runs` has sat in this repo with zero "
            "callers and a docstring claiming otherwise, which is the state this rejects"
        )

    def test_it_acts_only_on_evidence_the_row_carries_about_itself(self):
        import asyncio
        issued: list[tuple] = []

        class _Conn:
            async def fetchval(self, sql, *args):
                issued.append((sql, args)); return 5

        class _Acquire:
            async def __aenter__(self): return _Conn()
            async def __aexit__(self, *a): return False

        class _Pool:
            def acquire(self): return _Acquire()

        n = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            instrument.resolve_expired_suspends(_Pool())
        )
        assert n == 5, "it must report what it resolved, not a hardcoded zero"
        sql, args = issued[0]
        assert "expires_at <= now()" in sql, (
            "the only admissible evidence — a fact the row carries about itself, not an inference. "
            "The reconciler branch removed this checkpoint was removed for lacking exactly this"
        )
        assert "finish_reason = 'awaiting_input'" in sql
        assert instrument.OUTCOME_ABANDONED_BY_USER in args
        # F-38 — the two columns must move together. A row saying `abandoned` in one and
        # `awaiting_input` in the other cannot be read at all, and the published figure read the
        # wrong half for 84.6% of that bucket.
        assert "finish_reason = 'abandoned_expired'" in sql, (
            "outcome moved without finish_reason — the self-contradiction the lockstep gate rejects"
        )
        # EXISTS must not be invertible to NOT EXISTS, which would stamp exactly the LIVE cards.
        assert "AND EXISTS (SELECT 1 FROM chat_suspended_runs" in sql, (
            "inverting this predicate targets the runs that have NOT expired"
        )
        assert "outcome_source = 'reconciler'" in sql, (
            "a swept row must never be mistakable for one a terminal path recorded"
        )

    def test_it_does_not_delete_the_evidence(self):
        """REJECTS deleting the suspended run. `sweep_expired_runs` does that and has zero callers;
        deleting the row before anything reads it is how these turns became unexplainable."""
        import ast, inspect
        # Read the CODE, not the prose. The docstring explains what it declines to do, so a naive
        # substring scan matches its own explanation — the same class of error as the gate that was
        # satisfied by a comment containing the word "outcome".
        fn = ast.parse(inspect.getsource(instrument.resolve_expired_suspends)).body[0]
        body = ast.get_source_segment(
            inspect.getsource(instrument.resolve_expired_suspends),
            fn,
        ) or ""
        literals = [
            n.value for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
        sql_literals = [v for v in literals if "chat_messages" in v or "chat_suspended_runs" in v]
        assert sql_literals, "no SQL found to inspect"
        assert not any("DELETE" in v.upper() for v in sql_literals), (
            "resolving an outcome must not destroy the record that justifies it"
        )


class TestOutcomeSourceIsTwoDirectional:
    """`outcome_source` only bites if BOTH sides declare themselves.

    Measured: nothing wrote 'path'. Both writers emitted 'reconciler', so a NULL meant either "a
    terminal path wrote this" or "a sweep wrote it before the column existed" — and 64.8% of
    outcomed rows read as path-written when they were not. A one-directional marker can REFUTE a
    claim of path-coverage; it cannot support one, which is the same limit as `source_inferred`.
    """

    def test_the_terminal_paths_declare_themselves(self):
        src = _stream_src()
        assert src.count("outcome_source = 'path'") >= 2, (
            "the upsert branches must claim authorship, or a swept row is indistinguishable from a "
            "path-written one on re-read"
        )
        assert src.count("'path')") >= 2, "and the INSERT branches too"

    def test_the_two_writers_never_claim_the_same_authorship(self):
        import inspect
        sweep = inspect.getsource(instrument.reconcile_crashed_turns)
        resolver = inspect.getsource(instrument.resolve_expired_suspends)
        for name, s in (("reconciler", sweep), ("resolver", resolver)):
            assert "'path'" not in s, f"{name} must never claim a terminal path wrote its row"
            assert "outcome_source = 'reconciler'" in s


class TestAResumeNeverErasesTheTurnItResumes:
    """The most serious defect found in this checkpoint, and nobody asked for it.

    Measured live: declining a confirm card took a row from 2 passes to 1 and ERASED the
    pass-1→pass-2 deletion — the exact founding-defect artefact `advertised_tools` exists to
    preserve. An executed tool call (`source='tool'`, `ok=true`) was replaced by a breaker entry.
    One UI click; same `message_id`; minutes apart.

    The row afterwards told a COHERENT, PLAUSIBLE, WRONG story — which is worse than a gap, because
    nothing about it invites a second look. And it means any `advertised_tools` reading taken after
    a resume measures the RESUME, not the turn.

    Cause: a resume builds a fresh recorder, so the upsert's COALESCE took the new, shorter array.
    `AdvertisedToolsRecorder` promises "appended, never replaced" — the persistence layer was
    replacing what the recorder had appended.
    """

    def test_both_upsert_sites_use_the_ONE_merge_expression(self):
        """🔴 REWRITTEN. The previous two gates here counted substrings of the merge SQL, and they
        were green over F-48 — an array storing `[1,1,2,1,2,3,1]` contains every substring they
        looked for. `||` in the source says nothing about what the column ends up holding.

        What is checkable without a database is the property that made F-45 possible: **the same
        rule maintained in two hand-written copies**. The class-4 predicate and the expired-suspend
        sweep drifted apart inside a single commit for exactly that reason. So this asserts there is
        ONE generator and both sites use it — the behaviour itself is proven against real Postgres
        in `test_cp0_merge_db.py`, which is where a jsonb expression can actually be executed.
        """
        src = _stream_src()
        for col in ("advertised_tools", "withheld_tools"):
            generated = instrument.segment_merge_sql(col)
            assert src.count(f'instrument.segment_merge_sql("{col}")') >= 2, (
                f"{col}: both upsert sites must interpolate the shared merge expression"
            )
            # And no hand-written copy may survive beside it: a second implementation is how the
            # two halves of one fix came to cancel each other.
            assert f"chat_messages.{col} || EXCLUDED.{col}" not in src, (
                f"{col}: a hand-written merge still exists alongside the generated one"
            )
            assert "jsonb_array_elements" in generated

    def test_the_merge_preserves_a_row_when_the_incoming_side_is_null(self):
        """A checkpoint that carries no recorder must leave what is stored intact — the one thing
        the original COALESCE got right, and the thing both later rewrites could have dropped.
        Asserted on the generated expression, so there is one place for it to be true."""
        for col in ("advertised_tools", "withheld_tools"):
            sql = instrument.segment_merge_sql(col)
            i = sql.index(f"WHEN EXCLUDED.{col} IS NULL THEN chat_messages.{col}")
            j = sql.index(f"WHEN chat_messages.{col} IS NULL THEN EXCLUDED.{col}", i)
            assert j > i, f"{col}: both NULL branches must precede the merge"

    def test_the_merge_generator_refuses_a_non_identifier(self):
        """It interpolates into SQL. The guard is not theatre: this is the only string in the
        instrument that is not a bound parameter."""
        with pytest.raises(ValueError):
            instrument.segment_merge_sql("advertised_tools; DROP TABLE chat_messages --")


class TestP1RegistrationIsUnconditional:
    """P1's EIGHTH frame — my own registration hiding inside a branch.

    A control turn (world-setup intent, where the intent filter provably does not fire) left the
    residual unchanged at 4, disproving the intent-gate diagnosis. This is what it was pointing at:
    the `domain_not_selected` block sat under `if binding_categories:`, so on every turn WITHOUT
    binding categories it never ran — and the tools it was written to record went unregistered
    exactly as before the fix.

    Eight frames, and the last two were both my fix placed where it could not run: once after the
    stage it instruments, once inside a branch that stage does not take.
    """

    def test_it_registers_on_a_turn_with_no_binding_categories(self):
        """The condition under which it silently did nothing. No binding_categories, no sticky
        domains — the ordinary turn."""
        from app.services import instrument as _inst
        from app.services.tool_surface import SessionToolPins, discovery_seed_for_surface

        catalog = [
            {"type": "function", "function": {"name": n, "description": "d",
                                              "parameters": {"type": "object", "properties": {}}}}
            for n in ("book_read", "glossary_search", "world_map_create", "kg_project_create")
        ]
        sink: list[dict] = []
        token = _inst.surface_withheld.set(sink)
        try:
            discovery_seed_for_surface(
                catalog,
                pins=SessionToolPins(effective_enabled=[], effective_skills=[],
                                     curated_mode=False,
                                     activation_state={"activated_tools": [], "dirty": False}),
                editor=False, book_scoped=True,
                binding_categories=None,   # <- the branch that used to gate the whole block
            )
        finally:
            _inst.surface_withheld.reset(token)
        assert any(e["stage"] == "domain_not_selected" for e in sink), (
            "no registration on a turn without binding categories — the eighth frame, and the "
            "condition under which every prior measurement was taken"
        )

    def test_the_block_is_not_nested_under_a_conditional(self):
        """Structural, because the behavioural test above can only prove ONE branch. Asserts the
        registration sits at function level — the property that makes it unconditional."""
        import ast, inspect
        from app.services import tool_surface
        src = inspect.getsource(tool_surface.discovery_seed_for_surface)
        tree = ast.parse(src.lstrip())
        fn = tree.body[0]

        def _mentions(node) -> bool:
            return any(
                isinstance(n, ast.Constant) and n.value == "domain_not_selected"
                for n in ast.walk(node)
            )

        top = [st for st in fn.body if _mentions(st)]
        assert top, (
            "the registration is not at function level — it is nested inside a branch, which is "
            "exactly how it came to never run"
        )


class TestU2ACatalogueOutageIsRegistered:
    """U-2 — REJECTS the counter-example that REFUTED P1.

    `get_tool_definitions` returned `[]` on any exception with only a `logger.warning`, so a gateway
    hiccup withheld **the entire catalogue** and registered nothing — the largest narrowing this
    system can perform, treated as a feature. P1 is falsifiable at n=1 and this was the n.
    """

    def test_the_record_carries_a_scope_and_no_tool(self):
        """Neither escape was acceptable: one row per absent declaration turns an outage into
        hundreds of identical rows, and `tool: "*"` makes every consumer that counts tools return a
        wrong answer while looking correct."""
        sink: list = []
        token = instrument.surface_withheld.set(sink)
        try:
            instrument.record_catalogue_unavailable(
                stage="catalogue_unavailable", reason="list-tools failed: TimeoutError",
            )
        finally:
            instrument.surface_withheld.reset(token)
        assert len(sink) == 1
        assert sink[0]["scope"] == instrument.SCOPE_CATALOGUE
        assert "tool" not in sink[0], "a catalogue outage has no single tool; a sentinel would lie"

    def test_count_is_ABSENT_on_a_cold_failure_not_zero(self):
        """`count: 0` claims *we know nothing was there*. On a cold failure nothing is known, not
        even the size — emitting 0 is a fabrication reached by a default, which is the thing this
        record exists to stop."""
        sink: list = []
        token = instrument.surface_withheld.set(sink)
        try:
            instrument.record_catalogue_unavailable(stage="s", reason="r")
            instrument.record_catalogue_unavailable(stage="s", reason="r", count=41)
        finally:
            instrument.surface_withheld.reset(token)
        assert "count" not in sink[0]
        assert sink[1]["count"] == 41

    def test_a_per_declaration_record_still_carries_its_scope(self):
        """The other half of the extension — an existing record must say which question it answers,
        or a consumer cannot tell the two shapes apart."""
        sink: list = []
        token = instrument.surface_withheld.set(sink)
        try:
            instrument.record_surface_withheld("book_list", stage="token_budget", reason="over")
        finally:
            instrument.surface_withheld.reset(token)
        assert sink[0]["scope"] == instrument.SCOPE_DECLARATION and sink[0]["tool"] == "book_list"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,args,break_it", [
        # 🔴 EVERY branch that returns `[]`, not just the transport one. A verifier deleted the
        # registration from BOTH `mcp not installed` branches and the suite stayed **green** — round
        # 8 named that coverage gap, round 9 fixed the code it was hiding and left the gap itself.
        # And `no admin token` survived both rounds untouched, because each fix went to the branch
        # the previous verdict had pointed at.
        ("get_tool_definitions", {"user_id": "u-1"}, "transport"),
        ("get_admin_tool_definitions", {"admin_token": "tok"}, "transport"),
        ("get_tool_definitions", {"user_id": "u-1"}, "no_mcp"),
        ("get_admin_tool_definitions", {"admin_token": "tok"}, "no_mcp"),
        ("get_admin_tool_definitions", {"admin_token": None}, "no_token"),
    ])
    async def test_EVERY_catalogue_path_registers_on_a_real_failure(self, method, args, break_it):
        """🔴 The previous version asserted `src.count("self._register_catalogue_outage(") >= 2` —
        a substring count, which is how the ADMIN path came to be the one member of the set that was
        never fixed. Both methods return `[]` on a transport failure, and returning `[]` with only a
        log line IS the counter-example that refuted P1.

        Driven, not counted: a transport that raises, a context this test does not pre-arm with a
        hand-made sink, and the assertion that the record arrived.
        """
        import contextvars
        from unittest.mock import patch

        from app.services import instrument as _inst
        from app.client.knowledge_client import KnowledgeClient
        client = KnowledgeClient(
            base_url="http://knowledge-service:8092", internal_token="t", timeout_s=0.1, retries=1,
        )

        async def run():
            sink = _inst.arm_turn_surface()
            if break_it == "transport":
                with patch("app.client.knowledge_client.streamablehttp_client",
                           side_effect=RuntimeError("gateway down")):
                    out = await getattr(client, method)(**args)
            elif break_it == "no_mcp":
                # The dependency-missing branch. Deleting its registration left the suite green in
                # BOTH doors — a coverage gap round 8 named and round 9 walked past.
                with patch("app.client.knowledge_client.streamablehttp_client", None), \
                        patch("app.client.knowledge_client.ClientSession", None):
                    out = await getattr(client, method)(**args)
            else:                                              # no_token
                out = await getattr(client, method)(**args)
            return out, sink, _inst.catalogue_outage_registered()

        ctx = contextvars.copy_context()
        out, sink, outage = await ctx.run(run)

        assert out == [], "the failure path did not degrade to an empty catalogue"
        assert outage is True, f"{method} returned [] and registered nothing — P1's counter-example"
        rows = [e for e in sink if e.get("scope") == _inst.SCOPE_CATALOGUE]
        assert len(rows) == 1 and "tool" not in rows[0]
        assert rows[0]["stage"] == "catalogue_unavailable" and rows[0]["reason"]
        assert "count" not in rows[0], "a cold failure knows nothing, not even the size"

    def test_A_CATALOGUE_ROW_REACHING_THE_RECORDER_DOES_NOT_KILL_THE_TURN(self):
        """🔴 THE FIX FOR ARM-AFTER-USE IS WHAT ARMED THIS LANDMINE.

        The catalogue record deliberately omits `tool` — a sentinel would make every consumer that
        counts tools return a wrong answer while looking correct. That was decided in isolation from
        the drain, which read `_sw["tool"]` unconditionally. While the sink was armed 382 lines after
        the fetch the row never arrived, so the mismatch was **latent**. Arming the sink first
        delivered it: a verifier measured a real editor-surface turn and a real resume both ending in
        `RUN_ERROR "'tool'"` **with the model never called** — a degraded catalogue converted from a
        silent narrowing into a dead turn.

        A record shape and its consumer are ONE change.
        """
        rec = instrument.AdvertisedToolsRecorder()
        rec.record_pass(["book_list"], tool_choice="auto")
        sink = [
            {"scope": instrument.SCOPE_CATALOGUE, "stage": "catalogue_unavailable",
             "reason": "list-tools failed: TimeoutError"},
            {"scope": instrument.SCOPE_DECLARATION, "tool": "glossary_search",
             "stage": "token_budget", "reason": "over budget"},
        ]
        # The production drain, verbatim in shape: dispatch on scope, never index `tool` blind.
        for _sw in sink:
            if _sw.get("scope") == instrument.SCOPE_CATALOGUE:
                rec.record_catalogue_withheld(
                    stage=_sw["stage"], reason=_sw["reason"], count=_sw.get("count"))
            else:
                rec.record_withheld(_sw["tool"], stage=_sw["stage"], reason=_sw["reason"])

        rows = rec.withheld_json()
        assert rows is not None
        outage = [r for r in rows if r.get("scope") == instrument.SCOPE_CATALOGUE]
        assert len(outage) == 1, "the outage row was dropped by reconciliation"
        assert "tool" not in outage[0], "a sentinel name leaked back in"
        assert outage[0]["pass"] == 1 and outage[0]["stage"] == "catalogue_unavailable"
        assert {r["tool"] for r in rows if "tool" in r} == {"glossary_search"}

    def test_THE_ROW_REACHES_THE_COLUMN_ON_A_TURN_THAT_NEVER_ADVERTISED(self):
        """🔴 **THE RECORD PATH WAS DISABLED BY THE EVENT IT EXISTS TO RECORD.**

        The drain lived inside `if _adv_ev is not None` — a chunk only `_stream_with_tools` emits.
        A **tool-free** turn never reached it, and *a catalogue outage is precisely what makes a turn
        tool-free.* Measured across the four live turn shapes: agui+editor wrote the row; plain chat,
        admin and voice persisted `NULL` while the sink held it.

        So the drain belongs to the recorder, and `withheld_json()` runs it — because every terminal
        path reads that, and no path can forget to.
        """
        sink = [{"scope": instrument.SCOPE_CATALOGUE, "stage": "catalogue_unavailable",
                 "reason": "list-tools failed: TimeoutError"}]
        rec = instrument.AdvertisedToolsRecorder()
        rec.bind_sink(sink)
        # No `record_pass` at all — this turn never advertised, which is the whole point.
        rows = rec.withheld_json()
        assert rows, "the sink held a narrowing and the column got nothing"
        assert rows[0]["scope"] == instrument.SCOPE_CATALOGUE
        assert rows[0]["pass"] is None, "no pass ran; fabricating 1 would claim one did"
        assert not sink, "drained, not copied — a second read must not duplicate it"

    def test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE__not_a_literal_None(self):
        """🔴 *"Round 10 made the row arrive, and nothing in the tree would notice if it stopped."*

        A verifier deleted `bind_sink` from `stream_response` — **green**. From
        `voice_stream_response` — **green**. Bound `None` at the suspend, cancel, error and **clean
        finish** write sites — **all four green, 261 tests passing.** The mechanism worked and was
        held up by nothing.

        So this reads the parse tree at every site that persists the column and asserts the bound
        expression is the RECORDER'S, never a literal. A behaviour test cannot reach all four
        terminal paths from a unit suite; what it can do is make "someone quietly binds `None`
        again" impossible to do silently.

        🔴 **AND THE FIRST VERSION OF THIS GATE WAS WORSE THAN NO GATE.** It matched
        `ast.keyword`, and **every bind that actually persists the column is POSITIONAL** — an
        asyncpg parameter. So it saw 4 of 8 sites, **none of them an SQL bind**, stayed green on the
        clean finish, on voice, on the main INSERT, and **on the orphan `UPDATE` that was the
        previous round's own headline fix** — while reddening on a correct helper. A guard with a
        false positive is one that gets deleted the first time it is inconvenient, and this one was
        also blind where it mattered.

        🔴 **AND THE SECOND VERSION WAS STILL A PROPERTY ABOUT ONE SYNTACTIC FORM OF ONE LOCAL, SO
        THE ORIGINAL FINDING SURVIVED SEVEN ROUNDS.** `_emit_chat_turn` — **the path every
        successful turn takes** — has no `withheld*` local at all: it binds the value as a positional
        argument. So `bad_bindings` was vacuous over it, the only obligation left was that the string
        `withheld_json` appear *somewhere* in its 1,200 lines, and binding `None` at the clean finish
        stayed green through two consecutive rewrites of this gate. An ordinary two-line extraction
        (`_wj_tmp = None; _withheld_json = _wj_tmp`) walked past it too.

        Each round said the honest version was "the harder one". A verifier finally **built** it and
        measured it: forty lines, **seven of seven defeats red, zero false positives on the pristine
        tree**. It was not harder; it was deferred. So the anchor moves from the ASSIGNMENT to the
        **BIND**:

        > For every `execute`/`fetchval`/`fetchrow` call whose SQL names `withheld_tools`, at least
        > one argument **of that call** must be recorder-derived — a `withheld_json()`/`absorb()`
        > call, a local transitively assigned from one (through `Assign` *and* `AnnAssign`), or the
        > conduit parameter.

        Keying on the SQL text of the *individual call* rather than on a column name matched anywhere
        in the function is also what stops R12's G5 false positive coming back.
        """
        import ast
        from pathlib import Path

        _RECORDER_CALLS = ("withheld_json", "absorb")
        _EXECUTORS = ("execute", "fetchval", "fetchrow", "fetch", "executemany")
        _COL = "withheld_tools"

        # 🔴 **T11d — SIX ROUNDS, AND IT IS ABOUT THE LIVE WRITE, NOT A PROBE.** Every production
        # site that persists this column is an **f-string**, and the only thing making any of them
        # visible to this gate is that the column name appears as a *literal* inside it —
        # `instrument.segment_merge_sql("withheld_tools")`, or the bare word in the INSERT's column
        # list. Hoist that name to a constant, which is the most ordinary refactor there is and one
        # this file has already recorded happening to the SQL itself (T9e), and the gate goes silent
        # on **the real writers**, not on a synthetic probe. Measured BLIND with the control CAUGHT.
        #
        # So a name bound to the column's own spelling resolves like a name bound to the SQL does,
        # and for the same reason: this gate has no import graph, so it over-approximates across
        # modules. Over-approximating costs a few extra binds to check; under-approximating is T11d.
        # 🔴 **AND THE FIRST REPAIR WAS WRONG IN BOTH DIRECTIONS AT ONCE.** It kept ONE
        # global alias set for all of `app/` with no import graph, and it flattened with `ast.walk`.
        # A verifier measured what each cost:
        #
        #   * **RED ON CORRECT CODE, twice, cross-module** - the delete-the-gate criterion I quoted
        #     at the verifiers. Module A hoists `_COL = "withheld_tools"`, which is exactly the
        #     refactor T11d exists to survive; module B, which never touches the column, takes an
        #     unrelated parameter named `_COL` - and is convicted. The same fires through
        #     `global_sql_names` with a generic `_SQL` executor helper. **The over-approximation
        #     does not cost "a few extra binds to check"; it costs the identifier namespace of the
        #     whole tree**, and `_COL`/`col`/`_SQL`/`sql`/`q` are normal things to write.
        #   * **BLIND on the table-name hoist** - the same refactor one level out, which is T9e
        #     exactly, cited as the precedent and then left unfixed. `ast.walk` is BREADTH-first, so
        #     an alias's spelling is always appended AFTER every literal in the expression:
        #     `withheld_tools =` is never contiguous, and the fix survived only because
        #     `UPDATE chat_messages` was still a literal.
        #
        # Both come from the same two choices. Aliases are scoped to the module that binds them plus
        # the modules that IMPORT them, and the text is assembled in SOURCE order with any name
        # bound to a string literal substituted - not just the column's, so a hoisted TABLE name
        # resolves by the same rule that resolves a hoisted column name.
        _col_aliases: dict[str, str] = {}

        def _flat_sql(node) -> str:
            """The expression's strings, in **source order**, with string-bound names substituted.

            `ast.iter_child_nodes` yields fields in declaration order, and for a `JoinedStr` that is
            the order the pieces appear in the f-string. `ast.walk` is breadth-first and was the
            whole of A4.
            """
            parts: list[str] = []

            def go(n):
                if isinstance(n, ast.Constant) and isinstance(n.value, str):
                    parts.append(n.value)
                    return
                if isinstance(n, ast.Name) and n.id in _col_aliases:
                    parts.append(_col_aliases[n.id])
                    return
                for c in ast.iter_child_nodes(n):
                    go(c)

            go(node)
            return " ".join(" ".join(parts).split())

        def _names_the_column(node) -> bool:
            """Does this expression carry SQL that **writes a value into** the column?

            🔴 The per-bind rebuild dropped the qualification the previous version had and matched
            the bare column name. Widening the sweep to all of `app/` then reddened
            `db/migrate.py` - the **DDL that creates the column**, which binds nothing. That is a
            false positive on correct code, the failure this file has convicted itself of three
            times, and it is recorded here rather than fixed by narrowing the sweep back: the
            subject is a row WRITE, and `CREATE TABLE` / `ALTER TABLE` are not writes.
            """
            # 🔴 **AND QUALIFYING IT COST FIVE DETECTIONS THAT ALREADY WORKED.** A verifier
            # attributed them per probe against a control: concatenation, `.format`, `%`,
            # `" ".join` and **two spaces** (`"UPDATE  chat_messages"`) were all CAUGHT before this
            # qualification and blinded by it. Damping a false positive by narrowing a matcher is
            # how a gate loses the cases it was built for. So the SQL is ASSEMBLED from every string
            # in the expression and whitespace-normalised before matching - which still keeps
            # `db/migrate.py` out, because DDL contains none of these verbs, and discards no
            # spelling of a write.
            _flat = _flat_sql(node)
            if _COL in _flat and (
                    "INSERT INTO chat_messages" in _flat
                    or "UPDATE chat_messages" in _flat
                    or f"{_COL} =" in _flat
                    or f"{_COL}=" in _flat):
                return True
            for n in ast.walk(node):
                # `_called_name`, not `func.attr`: a bare-name `segment_merge_sql(...)` - the same
                # unqualified-executor shape T9 already recorded for `execute` - had no `attr` at
                # all, so this branch returned `None` and read as "not the column".
                if isinstance(n, ast.Call) and _called_name(n) == "segment_merge_sql" \
                        and any((isinstance(a, ast.Constant) and a.value == _COL)
                                or (isinstance(a, ast.Name)
                                    and _col_aliases.get(a.id) == _COL)
                                for a in n.args):
                    return True
            return False

        def _has_recorder_call(node) -> bool:
            return any(isinstance(n, ast.Call)
                       and getattr(n.func, "attr", None) in _RECORDER_CALLS
                       for n in ast.walk(node))

        def _bindings(fn):
            """`(target_name, value_expr)` for every assignment form that can bind a local."""
            out = []
            for n in ast.walk(fn):
                if isinstance(n, ast.Assign):
                    targets, value = n.targets, n.value
                elif isinstance(n, ast.AnnAssign) and n.value is not None:
                    targets, value = [n.target], n.value
                elif isinstance(n, ast.NamedExpr):          # the walrus
                    targets, value = [n.target], n.value
                else:
                    continue
                for t in targets:
                    if isinstance(t, ast.Name):
                        out.append((t.id, value))
                    elif isinstance(t, (ast.Tuple, ast.List)):   # a tuple target
                        for e in t.elts:
                            if isinstance(e, ast.Name):
                                out.append((e.id, value))
            return out

        def _recorder_locals(fn) -> set[str]:
            """Names transitively derived from a recorder call, plus the conduit parameter.

            A fixed point, **depth-bounded** — `a = b; b = a` is a cycle and a gate that hangs is a
            gate someone deletes.
            """
            derived = {a.arg for a in fn.args.args + fn.args.kwonlyargs
                       if "withheld" in a.arg}
            binds = _bindings(fn)
            for _ in range(12):
                grew = False
                for name, value in binds:
                    if name in derived:
                        continue
                    if _has_recorder_call(value) or any(
                            isinstance(n, ast.Name) and n.id in derived for n in ast.walk(value)):
                        derived.add(name)
                        grew = True
                if not grew:
                    break
            return derived

        # 🔴 **T8 — AND IT WAS THE MODULE LIST.** Ten in-module defeats red (alias, `*args`,
        # `**kwargs`, a returning helper, `executemany`, a rename, SQL split across one and two
        # locals, a lost writer, a gained writer) — and a writer in **any other module** binding
        # `None` was `1 passed`, three ways. A gate whose file set is TYPED OUT cannot notice a
        # writer arriving somewhere else, and the arm-order gate sixty lines below already derives
        # its file set with `rglob` for exactly that reason: two gates in one file, one discovering
        # and one listing.
        #
        # The reachability is not hypothetical: **`app/agentruntime/` is where CP-2's runtime
        # lands**, and a terminal write there would have been invisible to this gate by construction.
        # 🔴 **T9 — NINE MORE DEFEATS, AND THE HEADLINE ONE WAS A MODULE-LEVEL CONSTANT.** Hoisting
        # the SQL out of the function (`_SQL = "UPDATE chat_messages SET withheld_tools = $1 …"`)
        # made the whole gate blind, because `sql_locals` was computed from the FUNCTION's bindings
        # only. So were: SQL assembled in another module, a write at module scope, in a `lambda`, in
        # a comprehension, in a class body, and through a bare-name executor (`execute(...)` rather
        # than `conn.execute(...)`). And `except SyntaxError: continue` was **fail-open** — an
        # unparseable module silently left the sweep.
        #
        # Every one of those is an ordinary way to write the same statement. The anchor is now: any
        # executor call anywhere under `app/`, with the SQL resolved through module-level constants
        # and cross-module constants as well as function locals.
        offenders, binds_checked, unparseable = [], [], []
        _base = _swept_root()
        _paths = [p for p in sorted(_base.rglob("*.py"))
                  if not any(part in _TURN_SCOPE_EXCLUDE for part in p.parts)]
        _mods, trees_all = [], []
        for p in _paths:
            try:
                trees_all.append(ast.parse(p.read_text(encoding="utf-8")))
            except SyntaxError:
                # FAIL CLOSED. A file this gate cannot read is a file it cannot clear, and
                # `continue` meant an unparseable module left the sweep with no record at all.
                unparseable.append(p.relative_to(_base).as_posix())
                continue
            _mods.append(p.relative_to(_base).as_posix())

        # 🔴 **THE ALIAS MAPS ARE PER-MODULE PLUS IMPORTS, WHICH IS THE WHOLE OF A3.** One
        # global set meant a name bound anywhere convicted every OTHER module that reused the
        # identifier - two executed false positives on correct code, which is the criterion this
        # file uses to predict that a gate gets deleted. A constant crosses a module boundary
        # exactly one way, and it is an `import`; the arm-order gate sixty lines below already
        # follows those edges for the same reason.
        #
        # Every name bound to a string literal is recorded, not only the column's: a hoisted TABLE
        # name is the same refactor one level out (A4 / T9e's twin) and resolves by the same rule.
        _strs_by_mod: dict[str, dict[str, str]] = {}
        for mod, tree in zip(_mods, trees_all):
            own: dict[str, str] = {}
            for _ in range(12):                       # a fixed point: `_A = "x"; _B = _A`
                grew = False
                for name, value in _bindings(tree):
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        if own.get(name) != value.value:
                            own[name] = value.value
                            grew = True
                    elif isinstance(value, ast.Name) and value.id in own:
                        if own.get(name) != own[value.id]:
                            own[name] = own[value.id]
                            grew = True
                if not grew:
                    break
            _strs_by_mod[mod] = own

        def _visible_strs(mod: str, tree) -> dict[str, str]:
            """This module's string constants, plus the ones it actually IMPORTS."""
            out = dict(_strs_by_mod.get(mod, {}))
            for n in ast.walk(tree):
                if not (isinstance(n, ast.ImportFrom) and (n.module or "").startswith("app.")):
                    continue
                src = (n.module or "").removeprefix("app.").replace(".", "/") + ".py"
                for a in n.names:
                    val = _strs_by_mod.get(src, {}).get(a.name)
                    if val is not None:
                        out[a.asname or a.name] = val
            return out

        # `global_sql_names` was global for the same wrong reason and produced the same class of
        # false positive on a generic `async def run_any(conn, _SQL, arg)`. Per module, plus imports.
        _sql_by_mod: dict[str, set[str]] = {}
        for mod, tree in zip(_mods, trees_all):
            _col_aliases.clear()
            _col_aliases.update(_visible_strs(mod, tree))
            _sql_by_mod[mod] = {name for name, value in _bindings(tree)
                                if _names_the_column(value)}

        def _visible_sql(mod: str, tree) -> set[str]:
            out = set(_sql_by_mod.get(mod, set()))
            for n in ast.walk(tree):
                if not (isinstance(n, ast.ImportFrom) and (n.module or "").startswith("app.")):
                    continue
                src = (n.module or "").removeprefix("app.").replace(".", "/") + ".py"
                for a in n.names:
                    if a.name in _sql_by_mod.get(src, set()):
                        out.add(a.asname or a.name)
            return out

        for mod, tree in zip(_mods, trees_all):
            # The alias map is re-scoped per module before every use of `_names_the_column`.
            _col_aliases.clear()
            _col_aliases.update(_visible_strs(mod, tree))
            global_sql_names = _visible_sql(mod, tree)
            for call in ast.walk(tree):
                if not (isinstance(call, ast.Call) and _called_name(call) in _EXECUTORS):
                    continue
                # The enclosing function, if any — a write at module scope, in a lambda or in a
                # comprehension has none, and used to be skipped for exactly that reason.
                fn = next((f for f in ast.walk(tree)
                           if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                           and f.lineno <= call.lineno <= (f.end_lineno or f.lineno)), None)
                derived = _recorder_locals(fn) if fn is not None else set()
                sql_locals = set(global_sql_names)
                sql_locals |= {n for n, v in _bindings(fn if fn is not None else tree)
                               if _names_the_column(v)}
                args = list(call.args) + [k.value for k in call.keywords]
                if not any(_names_the_column(a) or (isinstance(a, ast.Name) and a.id in sql_locals)
                           for a in args):
                    continue
                where = f"{mod}::{fn.name if fn is not None else '<module>'}:{call.lineno}"
                binds_checked.append(where)
                ok = any(
                    _has_recorder_call(a) or any(isinstance(n, ast.Name) and n.id in derived
                                                 for n in ast.walk(a))
                    for a in args
                )
                if not ok:
                    offenders.append(
                        f"{where} writes `withheld_tools` and NO argument of that call carries the "
                        f"recorder's value")

        assert not unparseable, (
            f"{unparseable} could not be parsed, so this gate cleared them without looking. A gate "
            f"that skips what it cannot read is green over exactly the files most likely to be wrong."
        )

        # 🔴 The NV: if the anchor stops matching, every assertion below is vacuous and green.
        #
        # The threshold is the MEASURED set, not a guess. I first wrote `>= 5` from an expectation
        # and it red on correct code — a gate whose bound comes from what the author assumed rather
        # than from what is there is the same defect as a metric with a self-derived denominator,
        # and it is the shape this file exists to catch. The four binds are two in
        # `_persist_terminal_assistant` (the INSERT and the orphan UPDATE), one in `_emit_chat_turn`
        # (the clean finish — R10's I13, the site this rebuild is for) and one in voice.
        #
        # Named rather than counted, so losing a *specific* writer is caught by name: a count alone
        # is satisfied by any four.
        _binding_fns = {b.split("::")[1].split(":")[0] for b in binds_checked}
        assert _binding_fns >= {"_persist_terminal_assistant", "_emit_chat_turn",
                                "voice_stream_response"}, (
            f"a terminal writer stopped binding `withheld_tools`: found {sorted(_binding_fns)}. "
            f"Three of four turn shapes once persisted NULL under a fully green suite."
        )
        assert len(binds_checked) >= 4, (
            f"only {len(binds_checked)} bind(s) of `withheld_tools` were found: {binds_checked}. "
            f"The gate's anchor stopped matching, so it is green over nothing."
        )
        assert not offenders, (
            f"{offenders} — a statement persists the column with no recorder-derived argument. A "
            f"verifier bound `None` at the clean finish and at four other sites, and the previous "
            f"two versions of this gate stayed green on all of them."
        )

    @pytest.mark.asyncio
    async def test_AN_EMPTY_CATALOGUE_IS_NOT_AN_OUTAGE__AT_THE_CALLER_TOO(self):
        """🔴 I re-created U-2's founding confusion **in the fix for something else**, and the test
        against it stayed green because that test drives the *recorder* while the defect was at the
        *caller*.

        A successful fetch returning zero tools is a legitimately empty catalogue — an admin with no
        system-tier tools — not an unavailable one. Registering it told the model its tools were
        unreachable when nothing had failed: the exact inversion, one layer out from where anyone
        was looking.
        """
        import contextvars
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.services import instrument as _inst
        from app.client.knowledge_client import KnowledgeClient

        listed = MagicMock()
        listed.tools, listed.meta = [], {}                      # SUCCESS, and empty
        session = AsyncMock()
        session.list_tools = AsyncMock(return_value=listed)
        session.initialize = AsyncMock()

        client = KnowledgeClient(
            base_url="http://knowledge-service:8092", internal_token="t", timeout_s=0.5, retries=1)

        async def run():
            _inst.arm_turn_surface()
            with patch("app.client.knowledge_client.streamablehttp_client") as transport, \
                    patch("app.client.knowledge_client.ClientSession") as cs:
                transport.return_value.__aenter__ = AsyncMock(return_value=(None, None, None))
                transport.return_value.__aexit__ = AsyncMock(return_value=False)
                cs.return_value.__aenter__ = AsyncMock(return_value=session)
                cs.return_value.__aexit__ = AsyncMock(return_value=False)
                out = await client.get_admin_tool_definitions("adm")
            return out, _inst.catalogue_outage_registered()

        out, outage = await contextvars.copy_context().run(run)
        assert out == []
        assert outage is False, (
            "an empty catalogue was registered as an OUTAGE, so the model is told its tools are "
            "unreachable when nothing failed — the confusion U-2 exists to end"
        )

    @pytest.mark.asyncio
    async def test_AN_EMPTY_ADMIN_CATALOGUE_IS_NOT_CACHED(self):
        """The `[]`-not-cached fix shipped with **no test**, and it is the half of that change that
        actually mattered: the cache had no TTL, so one zero-tool answer pinned every admin turn for
        the life of the process and the transport was never re-dialled after recovery. The emptiness
        was never the outage — **the permanence was.**"""
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.client.knowledge_client import KnowledgeClient

        calls = {"n": 0}

        def _listed(n):
            t = MagicMock()
            t.name, t.description, t.inputSchema = f"admin_{n}", "d", {"type": "object"}
            out = MagicMock()
            out.tools, out.meta = ([] if n == 0 else [t]), {}
            return out

        session = AsyncMock()

        async def list_tools():
            calls["n"] += 1
            return _listed(0 if calls["n"] == 1 else 1)      # empty first, then recovered

        session.list_tools = list_tools
        session.initialize = AsyncMock()
        client = KnowledgeClient(
            base_url="http://knowledge-service:8092", internal_token="t", timeout_s=0.5, retries=1)

        with patch("app.client.knowledge_client.streamablehttp_client") as transport, \
                patch("app.client.knowledge_client.ClientSession") as cs:
            transport.return_value.__aenter__ = AsyncMock(return_value=(None, None, None))
            transport.return_value.__aexit__ = AsyncMock(return_value=False)
            cs.return_value.__aenter__ = AsyncMock(return_value=session)
            cs.return_value.__aexit__ = AsyncMock(return_value=False)
            first = await client.get_admin_tool_definitions("adm")
            second = await client.get_admin_tool_definitions("adm")

        assert first == []
        assert calls["n"] == 2, "the empty answer was cached; the gateway was never re-dialled"
        assert second, "a recovered catalogue was still served as empty, permanently"

    def test_A_NARROWING_BEFORE_ANY_ARMING_IS_STILL_RECORDED(self):
        """🔴 **EIGHT MEASURED ROUTES PAST THE ORDERING GATE IN THREE ROUNDS** — a helper one module
        over, two levels of helper, a `_`-prefixed entry point, a class method, `getattr`, a lambda,
        `functools.partial`, a module-level alias, a name collision. Each fix was a better
        *syntactic* check for a *semantic* property, and a parse tree cannot decide what a program
        does. After the eighth route it is the approach that is wrong, not the pattern list.

        So ordering stops being load-bearing: a narrowing with no sink **opens one**. Every route
        above ends in "the narrowing ran before the arming", and every one of them is now harmless.
        The ordering gate remains as a second line, not as the only one.
        """
        import contextvars

        def narrow_first_arm_never():
            # No `arm_turn_surface` anywhere — this is every bypass, distilled.
            instrument.record_catalogue_unavailable(stage="catalogue_unavailable", reason="boom")
            instrument.record_surface_withheld("book_list", stage="token_budget", reason="over")
            rec = instrument.AdvertisedToolsRecorder()
            return instrument.catalogue_outage_registered(), rec.withheld_json()

        outage, rows = contextvars.copy_context().run(narrow_first_arm_never)
        assert outage is True, "the outage was lost because nobody had armed first"
        assert rows and len(rows) == 2, f"narrowings lost to ordering: {rows}"

    def test_NARROW_THEN_ARM_KEEPS_THE_ROWS__the_shape_all_eight_routes_have(self):
        """🔴 **THE PREVIOUS FIX CLOSED THE CASE THAT NEVER HAPPENS, AND THIS TEST BLESSED IT.**

        Making a narrowing open its own sink was supposed to end the ordering problem. But **all
        eight measured bypass routes are narrowings ABOVE an arm**, and `arm_turn_surface` still
        *replaced* — so the auto-armed sink was created, filled, and then discarded by the very
        arming it was meant to survive. A verifier measured `outage=False, rows=None`.

        And the test that stood here asserted the replacement **as the desired property**: I wrote a
        guard for the behaviour that was the defect. Arming now adopts — a sink present at the top of
        a turn is that turn's own early narrowing, because each request runs in its own context copy.
        """
        import contextvars

        def narrow_then_arm():
            instrument.record_catalogue_unavailable(stage="catalogue_unavailable", reason="boom")
            instrument.record_surface_withheld("book_list", stage="token_budget", reason="over")
            instrument.arm_turn_surface()                    # the arm that used to throw them away
            rec = instrument.AdvertisedToolsRecorder()
            return instrument.catalogue_outage_registered(), rec.withheld_json()

        outage, rows = contextvars.copy_context().run(narrow_then_arm)
        assert outage is True, "the arming discarded the outage recorded before it"
        assert rows and len(rows) == 2, f"narrowings lost to the arming that followed them: {rows}"

    def test_the_ROW_AND_THE_NOTICE_CANNOT_CONTRADICT_EACH_OTHER(self):
        """🔴 A state the OLD code could not reach, created by my own fix. With the recorder built
        **before** the arm — which is `_emit_chat_turn`'s literal order — the recorder held the
        auto-armed list while `catalogue_outage_registered()` read the replaced one. The column then
        carried the outage row while the model was told nothing, which is worse than either failure
        alone: the record and the screen disagree, and the record is what a later question trusts."""
        import contextvars

        def recorder_before_arm():
            instrument.record_catalogue_unavailable(stage="catalogue_unavailable", reason="boom")
            rec = instrument.AdvertisedToolsRecorder()       # adopts whatever exists now
            instrument.arm_turn_surface()                    # …and this used to replace it
            return rec.withheld_json(), instrument.catalogue_outage_registered()

        rows, told = contextvars.copy_context().run(recorder_before_arm)
        assert bool(rows) == bool(told), (
            f"the persisted row says {bool(rows)} and the model was told {told} — the record and "
            f"the screen disagree about the same turn"
        )

    def test_THE_OUTAGE_FACT_DOES_NOT_OUTLIVE_ITS_TURN(self):
        """🔴 A defect **I introduced in this round's own fix**, caught by two prompt-caching tests
        that pass alone and fail in the full run — the signature of state leaking between turns.

        The flag was left alone when arming adopted an existing sink, on the reasoning that the rows
        and the flag are the same fact. They are, which is precisely why the flag must be **derived**
        from the rows and never carried: a context that had already served a turn kept `True`, and a
        later turn inserted "TOOL CATALOGUE UNAVAILABLE" with no outage. Production copies the
        context per request, so this could not have been seen there until a user saw it.
        """
        import contextvars

        def two_turns_one_context():
            instrument.arm_turn_surface()
            instrument.record_catalogue_unavailable(stage="catalogue_unavailable", reason="boom")
            first = instrument.catalogue_outage_registered()
            instrument.AdvertisedToolsRecorder().withheld_json()      # drains, as a write would
            instrument.arm_turn_surface()                             # the NEXT turn
            return first, instrument.catalogue_outage_registered()

        first, second = contextvars.copy_context().run(two_turns_one_context)
        assert first is True
        assert second is False, (
            "a later turn inherited the previous turn's outage and would tell the model its tools "
            "are unreachable when nothing failed"
        )

    def test_A_RECORDER_ADOPTS_THE_TURNS_SINK_WITHOUT_ANYONE_REMEMBERING_TO(self):
        """🔴 Deleting `bind_sink` was measured **green at both entry points**, and a gate written
        to catch that immediately showed the deeper problem: the arming is in `stream_response` and
        the binding was in `_emit_chat_turn` — **two functions**, so the pair could drift apart
        exactly as the arm and the drain already had, twice.

        So adoption moved into `__init__`. A recorder built inside a turn is a recorder for that
        turn, and that is knowable at construction. This drives it rather than reading it: build a
        recorder in an armed context and require the row to reach the column with no wiring call at
        all."""
        import contextvars

        def run():
            instrument.arm_turn_surface()
            instrument.record_catalogue_unavailable(stage="catalogue_unavailable", reason="boom")
            rec = instrument.AdvertisedToolsRecorder()          # no bind_sink, deliberately
            return rec.withheld_json()

        rows = contextvars.copy_context().run(run)
        assert rows, "a recorder built inside an armed turn did not adopt its sink"
        assert rows[0]["scope"] == instrument.SCOPE_CATALOGUE

        # ...and a recorder built OUTSIDE a turn adopts nothing, rather than inventing a turn.
        assert contextvars.copy_context().run(
            lambda: instrument.AdvertisedToolsRecorder().withheld_json()) is None

    def test_a_PASS_that_offered_no_tools_is_not_a_tool_named_star(self):
        """🔴 §0.14.3 rejects the `tool: \"*\"` sentinel **by name**, and the code minted one two
        thousand lines away. A sentinel makes every consumer that counts tools return a wrong answer
        while still looking correct."""
        rec = instrument.AdvertisedToolsRecorder()
        rec.record_pass([], tool_choice=None)
        rec.record_pass_withheld(stage="pass_offered_no_tools", reason="forced final answer (D7)")
        rows = rec.withheld_json()
        assert rows and rows[0]["scope"] == instrument.SCOPE_PASS
        assert "tool" not in rows[0], "the sentinel came back"
        assert all(r.get("tool") != "*" for r in rows)

    @pytest.mark.parametrize("row", [
        {"scope": "catalogue", "stage": "s", "reason": "r"},
        {"scope": "pass", "stage": "s", "reason": "r"},
        {"scope": "declaration", "tool": "t", "stage": "s", "reason": "r"},
        {"tool": "t", "stage": "s", "reason": "r"},                       # legacy, no scope
        {"scope": "a_scope_from_the_future", "stage": "s", "reason": "r"},
        {"scope": "a_scope_from_the_future", "tool": "t", "stage": "s", "reason": "r"},
        {"stage": "s", "reason": "r"},                                    # neither
        {},                                                               # nothing at all
        {"scope": ["unhashable"], "stage": ["unhashable"], "tool": ["unhashable"]},
        {"scope": object(), "stage": object(), "reason": object(), "tool": object()},
        {"scope": "catalogue", "stage": "s", "reason": "r", "count": "not an int"},
        "not a dict at all",
        None,
        42,
    ])
    def test_ABSORB_IS_TOTAL__no_row_shape_can_kill_the_turn_or_the_write(self, row):
        """🔴 **FOURTH RECURRENCE OF THE SAME CLASS.** Every fix so far enumerated the scopes that
        carry no `tool`, and every time a new one arrived the enumeration was one behind: the reader
        crashed on the row the writer had just been taught to produce. A verifier fed 19 shapes and
        **7 still crashed** — an unhashable `stage` in the dedupe set, an unhashable `tool` in the
        other one, and four that died at `json.dumps` **after** the turn had already succeeded.

        A record that can kill the write it belongs to is not instrumentation. So this asserts the
        property rather than the enumeration: **absorb, reconcile and serialise, for every shape.**
        """
        import json

        rec = instrument.AdvertisedToolsRecorder()
        rec.record_pass(["book_list"], tool_choice="auto")
        rec.absorb([row])
        rows = rec.withheld_json()                     # the reader that has crashed four times
        assert rows is None or json.dumps(rows)        # and the write path that crashed four more
        if rows:
            for r in rows:
                assert isinstance(r.get("stage"), str) and r["stage"]
                assert isinstance(r.get("reason"), str) and r["reason"]
                assert "count" not in r or isinstance(r["count"], int)

    def test_a_FUTURE_scope_carrying_a_tool_keeps_its_scope(self):
        """`elif row.get("tool")` sat before the fallback, so a new scope that happened to carry a
        tool was filed as `declaration` **with its own scope discarded** — the one-behind
        enumeration again, this time in the branch ORDER rather than in the list."""
        rec = instrument.AdvertisedToolsRecorder()
        rec.record_pass(["book_list"], tool_choice="auto")
        rec.absorb([{"scope": "future_thing", "tool": "book_get", "stage": "s", "reason": "r"}])
        rows = rec.withheld_json()
        assert rows and rows[0]["scope"] == "future_thing", (
            f"the scope was rewritten to {rows[0].get('scope')!r}"
        )

    def test_AS_TEXT_RETURNS_A_PLAIN_STR__not_a_subclass(self):
        """R12's finding #3 was fixed and **left untested**, which is how it survived to be found
        again: `str(value)` on an object whose `__str__` returns a `str` SUBCLASS handed the dedupe
        set an unhashable key at the exact line whose comment says the crash is closed."""
        class Unhashable(str):
            __hash__ = None

        class Sneaky:
            def __str__(self):
                return Unhashable("boom")

        assert type(instrument._as_text(Sneaky())) is str
        assert type(instrument._as_text(Unhashable("x"))) is str
        rec = instrument.AdvertisedToolsRecorder()
        rec.absorb([{"scope": "catalogue", "stage": Sneaky(), "reason": Sneaky()}])
        assert rec.withheld_json()                    # the dedupe key did not explode

    def test_ABSORB_EMPTIES_THE_REAL_SINK__not_a_copy_of_it(self):
        """`sink = list(sink)` drained the **copy** and left the original full, so a checkpoint plus
        a terminal write absorbed the same rows twice — measured 1 row becoming 2. The copy was added
        to stop a container lying about `pop`; it stopped the drain instead."""
        class Weird(list):
            pass

        sink = Weird([{"scope": "catalogue", "stage": "s", "reason": "r"}])
        rec = instrument.AdvertisedToolsRecorder()
        rec.absorb(sink)
        assert list(sink) == [], "the real sink was not emptied; a second absorb duplicates it"
        rec.absorb(sink)
        assert len(rec.withheld_json()) == 1

    def test_a_NON_DICT_row_names_what_it_actually_WAS(self):
        """The second coercion branch was dead code, so a row of `42` recorded `stage: "unknown"` —
        losing the one fact a reader needs to find whoever appended it."""
        rec = instrument.AdvertisedToolsRecorder()
        rec.absorb([42])
        rows = rec.withheld_json()
        assert rows and "int" in rows[0]["reason"], rows

    def test_ARMING_CANNOT_RAISE_ON_ANY_SINK_CONTENT(self):
        """🔴 The derived-flag code used `isinstance(e, dict)` and a bare `.get` — **in the commit
        whose headline was that `isinstance` was the bug**. A rogue row made `arm_turn_surface`
        itself raise, and that is the FIRST STATEMENT of every turn entry point: a failure there
        takes the whole turn."""
        class Hostile(dict):
            def get(self, *a, **k):
                raise RuntimeError("no")

        import contextvars

        def run():
            instrument.surface_withheld.set([Hostile(), 42, None, "x"])
            return instrument.arm_turn_surface()

        assert contextvars.copy_context().run(run) is not None

    def test_the_outage_row_survives_reconciliation_because_it_has_no_name_to_reconcile(self):
        """`withheld_json` filters a withholding out when the tool turns out to have been advertised
        after all. An outage is a statement about the WHOLE catalogue — there is no name to look up,
        so the expression that asks `w["tool"] not in advertised` both crashes and, if made lenient,
        would silently discard the largest narrowing the system performs."""
        rec = instrument.AdvertisedToolsRecorder()
        rec.record_pass(["book_list", "glossary_search"], tool_choice="auto")
        rec.record_catalogue_withheld(stage="catalogue_unavailable", reason="boom")
        # `glossary_search` WAS advertised on this pass, so its per-declaration row is reconciled
        # away — proving the filter is live and that the outage row survives it on merit.
        rec.record_withheld("glossary_search", stage="token_budget", reason="over")
        rows = rec.withheld_json()
        assert rows is not None and len(rows) == 1
        assert rows[0].get("scope") == instrument.SCOPE_CATALOGUE

    def test_the_model_is_told_not_only_the_row(self):
        """Registering without telling the model reproduces the founding defect: a verifier watched
        the model say a withheld tool 'does not exist at all' while the row recorded it correctly.
        The row was honest and the screen was not.

        🔴 This used to assert the notice's STRING LITERAL was somewhere in the module — satisfied
        by one occurrence, while two of the three turn shapes (admin, resume) had no notice at all.
        The text is now one constant, so what is left to check here is its content; **which paths
        reach it** is the parametrised test below.
        """
        from app.services.stream_service import CATALOGUE_UNAVAILABLE_NOTICE as note
        assert "temporary" in note.lower(), "the model must be told this is temporary, not absence"
        assert "does not exist" in note, "the model must be told NOT to claim absence"
        assert "retry" in note.lower(), "and what to do instead of inventing a result"

    def test_ALL_THREE_TURN_SHAPES_reach_the_notice(self):
        """🔴 Two of the three were silent, and a source-literal gate could not tell.

        The fresh turn had it; the ADMIN turn was explicitly excluded (`and not admin_context`, with
        its catalogue fetched 350 lines *after* the prompt was assembled), and the RESUME turn — which
        re-derives its whole surface from scratch — never had it.

        🔴 **This docstring used to end "so a fourth entry point cannot inherit the silence by
        omission". That was false and a verifier measured it: the assertion is a SUBSET check over
        two names, so a third name is simply never asked about — and a fourth entry point
        (`voice_stream_response`) was already in the tree, unarmed.** What follows checks the two
        names it lists and nothing else; **discovery** of entry points is
        `TestTheTurnSinkIsArmedBeforeAnythingNarrows`, which enumerates them from the parse tree
        instead of naming them. A claim about "any fourth" belongs to the test that can see one.
        """
        import ast
        from pathlib import Path
        path = _swept_root() / "services" / "stream_service.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        users = {
            fn.name for fn in tree.body
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(isinstance(n, ast.Name) and n.id == "CATALOGUE_UNAVAILABLE_NOTICE"
                    for n in ast.walk(fn))
        }
        assert {"stream_response", "resume_stream_response"} <= users, (
            f"a turn entry point cannot tell the model about an outage: {sorted(users)}"
        )
        # ...and the admin branch must not be excluded from the READ, which is how it lost both
        # halves at once.
        src = _stream_src()
        assert "catalogue_outage_registered()" in src
        assert "and not admin_context" not in src.split("_catalogue_outage = instrument")[0][-400:], (
            "the outage read is gated on the non-admin branch again"
        )

    def test_an_EMPTY_catalogue_is_not_an_outage(self):
        """🔴 The defect the first version of this fix contained. `outage = not catalog` conflates
        an unavailable catalogue with a legitimately empty one — a user with no permissions has zero
        tools and no outage — which is the exact confusion U-2 exists to end, reproduced inside
        U-2's own fix. Three tests caught it by receiving an outage notice on a tool-free turn."""
        sink: list = []
        token = instrument.surface_withheld.set(sink)
        # The turn's fact now lives on the RECORDER, so starting a turn is what clears it —
        # `arm_turn_surface` releases the previous registration when the sink is empty, which is
        # what production does and what this used to hand-set a boolean to fake.
        instrument.arm_turn_surface()
        try:
            assert instrument.catalogue_outage_registered() is False
            instrument.record_surface_withheld("book_list", stage="token_budget", reason="over")
            assert instrument.catalogue_outage_registered() is False, (
                "a per-declaration narrowing is not a catalogue outage"
            )
            instrument.record_catalogue_unavailable(stage="catalogue_unavailable", reason="boom")
            assert instrument.catalogue_outage_registered() is True
        finally:
            instrument.surface_withheld.reset(token)

    def test_the_stream_reads_the_record_rather_than_inferring(self):
        """REJECTS the reintroduction. Inferring from emptiness is the shape that shipped once."""
        src = _stream_src()
        assert "_catalogue_outage = instrument.catalogue_outage_registered()" in src
        assert "_catalogue_outage = not _turn_catalog" not in src


#: 🔴 **DISCOVERED, NOT LISTED — twice over.** Round 8 replaced two hard-coded function names with
#: discovery inside two hard-coded MODULES, and round 9 walked past that in four ways: the fetch
#: extracted into a helper **one module over**, the same refactor through **two levels** of helper,
#: an entry point whose name starts with `_`, and an entry point in a **third module**. Each was
#: measured with the gate reporting `5 passed`, and the first two reproduced the end-to-end defect
#: (`told=False`) verbatim.
#:
#: So the scope is now every module under `app/services/` and `app/routers/`, and the helper walk
#: follows the call graph across modules to a fixed point. A boundary drawn at a file is a boundary
#: a refactor crosses by accident — which is exactly what "extract a helper" is.
#:
#: `_TURN_SCOPE_ROOT` / `_TURN_SCOPE_EXCLUDE` and the reason for their value now live at the TOP of
#: this module, beside `_swept_root()`, because six probe writers below typed `"app"` by hand while
#: the two gates read the constant — and a probe written outside the swept tree asserts nothing.


def _called_name(node):
    f = node.func
    if isinstance(f, ast.Attribute):
        return f.attr
    if isinstance(f, ast.Name):
        return f.id
    return None


def _narrowing_helpers_multi(by_name):
    """Names that reach a narrowing, over a name → [functions] index.

    Over-approximating on purpose: if **any** function with a given name narrows, the name counts.
    A gate that guesses may guess toward more scrutiny, never less — and the previous version keyed
    on the bare name with `setdefault`, so a same-named helper in a later module silently erased an
    earlier narrowing one (`_jsonb` and `_sse` collide today).
    """
    reaching = {
        name for name, fns in by_name.items()
        if any(isinstance(n, ast.Call) and _called_name(n) in _NARROWING_CALLS
               for fn in fns for n in ast.walk(fn))
    }
    changed = True
    while changed:
        changed = False
        for name, fns in by_name.items():
            if name in reaching:
                continue
            if any(isinstance(n, ast.Call) and _called_name(n) in reaching
                   for fn in fns for n in ast.walk(fn)):
                reaching.add(name)
                changed = True
    return reaching


def _narrowing_helpers(all_fns):
    """Names of functions that reach a narrowing, **transitively, to a fixed point.**

    🔴 Round 8's walk stopped at ONE level and stayed inside ONE module. Round 9 drove both limits:
    the fetch moved into a helper one module over (invisible), then through two levels of helper
    (invisible), and each reproduced `told=False` end-to-end while the gate said `5 passed`. A
    fixed-point closure has no depth to exceed and no file boundary to cross.
    """
    reaching = {
        name for name, fn in all_fns.items()
        if any(isinstance(n, ast.Call) and _called_name(n) in _NARROWING_CALLS for n in ast.walk(fn))
    }
    changed = True
    while changed:
        changed = False
        for name, fn in all_fns.items():
            if name in reaching:
                continue
            if any(isinstance(n, ast.Call) and _called_name(n) in reaching for n in ast.walk(fn)):
                reaching.add(name)
                changed = True
    return reaching


def _narrowings_in(fn, reaching):
    """Every call inside `fn` that reaches a narrowing — directly, or through any chain of helpers.
    The line reported is the CALL SITE, because that is where the narrowing happens for this turn."""
    found = []
    for n in ast.walk(fn):
        if not isinstance(n, ast.Call):
            continue
        name = _called_name(n)
        if name in _NARROWING_CALLS:
            found.append((n.lineno, name))
        elif name in reaching and name != fn.name:
            found.append((n.lineno, f"{name}->(narrows)"))
    return found


def _unconditional_calls(body, pred, narrows=None):
    """Every call satisfying `pred` that a reader can see is **not behind a branch**.

    One definition, used by BOTH the arming check and the delegation exemption — they had two, and
    the exemption's was `ast.walk`, which answers *"does this token appear anywhere in the tree"*
    when the question is *"does this run, before anything narrows"*. That gap was route 23: a
    delegating call under `if False:`, or inside a nested `def` nothing invokes, granted a blanket
    pass.

    Depth 1 through `with` / `async with` / `try` bodies, and no further. **It does not descend into
    a nested `def`** — a function definition is not an execution — nor into `if`, loops, or
    `except`/`finally` handlers.

    🔴 The first version matched only a call that WAS the statement's whole value, and the one live
    delegation in this repository is `return StreamingResponse(stream_response(...))` — a `Return`,
    with the delegate nested one level in. So the tightened exemption reddened `send_message`, which
    is correct code, and the gate was about to be loosened to make it pass. **The defect was in my
    definition of "unconditional", not in the router.** The statement kinds that carry an expression
    are enumerated, and the search runs over THAT STATEMENT'S expression — which keeps the property
    (nothing behind a branch a reader can see) while finding a call wherever it sits inside it.
    """
    _CARRIERS = (ast.Expr, ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Return)
    for s in body:
        if isinstance(s, _CARRIERS) and getattr(s, "value", None) is not None:
            for n in ast.walk(s.value):
                if isinstance(n, ast.Call) and pred(n):
                    yield n
        elif isinstance(s, (ast.With, ast.AsyncWith)):
            # 🔴 **W4's RULE WAS INSTALLED AT THE `try` DOOR AND NOT AT THIS ONE, EIGHT LINES
            # APART.** The token `[:1]` went in for `Try` with a nine-shape drive behind it, and its
            # twin here kept the whole body — so an arm SECOND inside a `with` reported
            # UNCONDITIONAL, and so did an arm second inside a `with` nested as the first statement
            # of a swallowing `try`, which is W4's own defect restored exactly. Measured by a
            # verifier on the real sweep: `arms=[7] conditional=[]` and `arms=[8] conditional=[]`.
            #
            # The argument is identical and I made it myself for `Try`: the block is ENTERED
            # unconditionally, so its first statement runs; the second runs only if the first did
            # not raise. Nothing about `with` weakens that — a `__enter__` that raises is the same
            # situation as a `try` body that raises, which is the very refutation that put `Try`
            # here in the first place.
            #
            # Reachability, measured not guessed: **45 `with`/`async with` under `app/`, 20 with
            # multi-statement bodies, 2 inside the turn entry points.** No arm sits in one today,
            # which is why the pristine gate was green for the right reason and this was latent.
            yield from _unconditional_calls(s.body[:1], pred, narrows)
        elif isinstance(s, ast.Try):
            # 🔴 **THE `Try` WIDENING OVERSHOT, AND IT WAS INTRODUCED BY THE FIX FOR ROUTE 18.**
            # Four probes that were RED before it are GREEN after — the worst being an arm as the
            # LAST statement of a `try` body with the narrowing in the `except` handler: the handler
            # runs precisely when the body did not finish, so that is a turn narrowing into nothing,
            # and the line numbers say the arm came first.
            #
            # A `try` body is entered unconditionally, which is why it counts at all. But it only
            # covers what is IN it: if a handler of the same `try` narrows, no arm inside the body
            # can be said to precede that narrowing.
            # 🔴 `narrows`, not `_NARROWING_CALLS` — **the same relation had two definitions eight
            # lines apart, in the same commit that fixed the previous instance of exactly that.**
            # The sibling filter uses the TRANSITIVE closure; this one used the bare primitive set,
            # so a handler narrowing through one hop of helper was invisible to it. The caller
            # supplies one predicate and both sites use it.
            _n = narrows or (lambda c: _called_name(c) in _NARROWING_CALLS)
            if not any(isinstance(n, ast.Call) and _n(n)
                       for h in s.handlers + [s.finalbody] if h is not None
                       for n in ast.walk(h if not isinstance(h, list)
                                         else ast.Module(body=h, type_ignores=[]))):
                # 🔴 **`s.body[:1]` — W4's rule, and it is ONE TOKEN, five rounds late.** R16-A
                # specified it: *accept a `try` body's arm only when no statement precedes it in the
                # chain.* A `try` is entered unconditionally, so its FIRST statement runs; the second
                # runs only if the first did not raise, which is the whole reason a `try` is there.
                # Every round since accepted the entire body and every round a verifier measured the
                # cost. Driven at 9/9 shapes, full suite at baseline.
                yield from _unconditional_calls(s.body[:1], pred, narrows)


def _turn_entry_calls():
    """Per turn entry point, from the PARSE TREE of **every** module under `app/services/` and
    `app/routers/`: `{mod::fn: (arms, raw_sets, narrowings, aliases, conditional_arms)}`.

    **Entry points are DISCOVERED, not listed** — including `_`-prefixed ones, because a leading
    underscore is a naming convention and not a guarantee that nothing routes to it.
    """
    base = _swept_root()
    trees = {}
    for path in sorted(base.rglob("*.py")):
        if any(part in _TURN_SCOPE_EXCLUDE for part in path.parts):
            continue
        rel = path.relative_to(base).as_posix()
        try:
            trees[rel] = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                           # pragma: no cover - a broken file is its own bug
            continue
    # 🔴 `tree.body` ONLY — so a **method**, a nested function and a lambda were all invisible, and
    # a verifier routed the admin door through a class method with the gate at `5 passed` and three
    # suites exactly at baseline while the admin turn lost both halves of U-2. `ast.walk` sees every
    # function in the module regardless of nesting.
    #
    # And the key was the bare NAME across all modules (`setdefault`), so two same-named helpers in
    # different files collapsed into one — measured: `_jsonb` and `_sse` collide today. Keyed by
    # module now, with a name index kept separately for the call-graph closure, which can only
    # over-approximate (a name that narrows in ANY module is treated as narrowing) — the safe
    # direction for a gate.
    by_name: dict[str, list] = {}
    for tree in trees.values():
        for f in ast.walk(tree):
            if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                by_name.setdefault(f.name, []).append(f)
    reaching = _narrowing_helpers_multi(by_name)
    # A router that DELEGATES to an armed entry point is covered by it. Without this the sweep
    # demands an arm from `send_message` (which calls `stream_response`) and a second arming is the
    # thing that discards what the first collected. Transitive, same fixed point as `reaching`.
    # 🔴 **ROUTE 20, AND MY OWN FIX CREATED IT.** I widened the sweep to all of `app/` and reused
    # the bare-name closure for BOTH relations. But the two are not symmetric:
    #
    #   * `reaching` (this narrows) over-approximates toward MORE scrutiny — a name that narrows
    #     anywhere is treated as narrowing everywhere. Safe.
    #   * `arming` (this is covered) over-approximates toward LESS scrutiny — it grants an
    #     **exemption**. With 68 files it was tolerable; at 115 files and 641 names a same-named
    #     arming helper anywhere in `app/` absolves a genuinely un-armed entry point. Measured:
    #     gate `6 passed`, control `2 failed`.
    #
    # **An over-approximation is only safe in the direction of suspicion.** So `arming` is keyed by
    # MODULE::NAME: a caller is covered only by a function it could actually be calling.
    arming = set()
    for mod, tree in trees.items():
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                isinstance(n, ast.Call) and _called_name(n) == "arm_turn_surface"
                for n in ast.walk(fn)
            ):
                arming.add(f"{mod}::{fn.name}")
    # A caller is covered by a function it can actually reach: one defined in its own module, or
    # one it IMPORTS. Bare-name matching across 641 names was the exemption hole; import-following
    # is the same relation with its real edges.
    visible = {}
    for mod, tree in trees.items():
        names = {f.name for f in ast.walk(tree)
                 if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("app."):
                src = (n.module or "").removeprefix("app.").replace(".", "/") + ".py"
                for a in n.names:
                    names.add(a.asname or a.name)
                    visible.setdefault((mod, a.asname or a.name), f"{src}::{a.name}")
        for nm in names:
            visible.setdefault((mod, nm), f"{mod}::{nm}")
    changed = True
    while changed:
        changed = False
        for mod, tree in trees.items():
            for fn in ast.walk(tree):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                key = f"{mod}::{fn.name}"
                if key in arming:
                    continue
                if any(isinstance(n, ast.Call)
                       and visible.get((mod, _called_name(n) or "")) in arming
                       for n in ast.walk(fn)):
                    arming.add(key)
                    changed = True

    out = {}
    for mod, tree in trees.items():
        for fn in ast.walk(tree):
            # `ast.walk`, not `tree.body`: a verifier routed the admin door through a CLASS METHOD
            # and the gate reported `5 passed` with three suites exactly at baseline.
            #
            # 🔴 ROUTE 19 — and `async def` ONLY was the same assumption one level down. A sync
            # entry point that narrows was invisible; nothing about a turn requires a coroutine.
            if not isinstance(fn, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            # 🔴 **ROUTES 21 AND 22 STOOD HERE, AND THE COMMIT THAT WROTE THEM WAS THE COMMIT THAT
            # CONDEMNED THEIR CLASS.** Ten lines above, in the fix for route 20: *"an
            # over-approximation is only safe in the direction of suspicion."* The same diff then
            # added two over-approximations in the direction of **exemption**:
            #
            #   * **Route 21** — `if fn.name.startswith("_") and no DIRECT narrowing call: continue`.
            #     `narrowings` is computed from `reaching`, the TRANSITIVE closure, so a `_`-prefixed
            #     entry point narrowing through one hop of helper was dropped before `_narrowings_in`
            #     ever ran. Measured `6 passed` against a byte-identical non-underscore control at
            #     `2 failed`. And `_turn_entry_calls`'s own docstring — twelve lines up, unedited —
            #     said entry points are discovered *"including `_`-prefixed ones, because a leading
            #     underscore is a naming convention and not a guarantee that nothing routes to it."*
            #     A guard loosened while the comment beside it claimed it had not been, which is this
            #     builder's own listed pattern, verbatim. Disabling it on the pristine tree revealed
            #     **+0**: it bought nothing and risked exactly the three functions
            #     (`_stream_with_tools`, `_emit_chat_turn`, `_run_subagent_call`) that were
            #     deliberately removed from `_NOT_A_TURN` *because discovery would catch them*.
            #
            #   * **Route 22** — `if fn.name in _NARROWING_CALLS: continue`, a bare-name exemption
            #     across all of `app/`, with no allow-list entry, no written reason, and outside
            #     `test_NO_ALLOW_LIST_ENTRY_IS_STALE`'s reach. Measured invisible on four of the five
            #     names — and **load-bearing**: disabling it turned the pristine gate `2 failed`, so
            #     it was silencing a real offender by name. The two functions it was written for now
            #     have `_NOT_A_TURN` entries with stated reasons, where the staleness test polices
            #     them; `app/agentruntime/` defines none of those five names today and CP-2's arming
            #     runtime is scheduled for exactly that package.
            #
            # Both are gone. The only exemption mechanism is the allow-list, which is the one with
            # a reason per entry and a test that the entry still exists.
            narrowings = sorted(_narrowings_in(fn, reaching))
            if not narrowings:
                continue                      # not a turn entry point: it narrows nothing
            # 🔴 **ROUTE 23 — THE DELEGATION EXEMPTION, AND IT WAS THE THIRD FIX TO CREATE THE NEXT
            # HOLE.** This granted a blanket pass to any function that *contains anywhere in its
            # tree* a call to something that arms. A verifier drove three defeats, each `6 passed`
            # against a control at `2 failed`:
            #
            #   * **ordering-blind** — narrow first, delegate afterwards. The delegate arms a sink
            #     the earlier narrowing never reached, which is the sixth recurrence exactly.
            #   * **dead-branch-blind** — the delegating call under `if False:`.
            #   * **liveness-blind** — the call inside a nested `def` nothing ever invokes.
            #
            # `ast.walk` answers *"does this token appear"*, and the question is *"does this run,
            # before anything narrows"*. So the exemption now requires a delegating call that is
            # **unconditionally executed** (top level, or a `with`/`try` body at depth 1 — the same
            # definition the arm itself uses, so the two cannot drift) and that **precedes every
            # narrowing**. Verified still correct for its one live beneficiary,
            # `routers/messages.py::send_message`.
            # 🔴 **ROUTE 24 — I COMPARED LINE NUMBERS AND PYTHON EVALUATES ARGUMENTS FIRST.**
            # `return stream_response(await c.get_tool_definitions())` puts the narrowing INSIDE the
            # delegating call, on the same line, and the fetch runs **before** the delegate is even
            # entered. Route 23 written on one line, exempted by the fix for route 23.
            #
            # A narrowing nested in the delegate's own arguments precedes it no matter what the line
            # numbers say, so those delegates do not count.
            _narrows = (lambda c: _called_name(c) in _NARROWING_CALLS
                        or _called_name(c) in reaching)
            _delegate_nodes = [c for c in _unconditional_calls(
                fn.body, lambda c: visible.get((mod, _called_name(c) or "")) in arming, _narrows)]
            _delegate_nodes = [
                c for c in _delegate_nodes
                if not any(isinstance(n, ast.Call)
                           and (_called_name(n) in _NARROWING_CALLS or _called_name(n) in reaching)
                           for a in list(c.args) + [k.value for k in c.keywords]
                           for n in ast.walk(a))
            ]
            _delegates = sorted(c.lineno for c in _delegate_nodes)
            if (f"{mod}::{fn.name}" in arming
                    and not any(isinstance(n, ast.Call)
                                and _called_name(n) == "arm_turn_surface" for n in ast.walk(fn))
                    # `<=`, not `<`: the delegating call IS usually the narrowing — `send_message`'s
                    # `stream_response(...)` both arms and reaches a narrowing, at one line. The
                    # property is *no narrowing happens BEFORE the delegation*, and a strict `<`
                    # states something else and reds correct code.
                    and _delegates and _delegates[0] <= min(ln for ln, _ in narrowings)):
                # It delegates to something that arms, before it narrows anything. Covered — and
                # arming again here is the discard the sixth recurrence was about.
                continue
            arms, raw_sets, aliases, conditional = [], [], [], []
            # An arm at the TOP LEVEL of the body is unconditional. One nested inside an `if`/`try`
            # is a turn that arms only sometimes, which a verifier measured green.
            # A top-level `arm_turn_surface()` — as a bare expression OR assigned, since the sink is
            # worth keeping (`_voice_sink = arm_turn_surface()`). What makes it unconditional is the
            # STATEMENT DEPTH, not the statement kind.
            #
            # 🔴 **ROUTE 18 — AND IT WAS A FALSE POSITIVE ON CORRECT CODE FOR THREE ROUNDS.** Only
            # `fn.body` counted, so an arm that is the first statement inside
            # `async with contextlib.AsyncExitStack():` reddened as *conditional* — measured
            # `1 failed` on an entry point that arms exactly once, unconditionally, before anything
            # narrows. **A gate that reds on correct code is one that gets deleted the first time it
            # is inconvenient**, and the shape it reds on is ordinary: `voice_stream_service.py:237`
            # is one refactor away from being written that way.
            #
            # 🔴 **AND THE REASON I GAVE FOR STOPPING AT `With` WAS REFUTED IN THE SAME ROUND.** I
            # wrote that `Try` must not count because *"an arm inside a `try` is one exception away
            # from a turn that narrows into nothing"* — and a verifier pointed out that a `with`
            # whose `__enter__` raises is the identical situation, **and it was already accepted**.
            # So the stated distinction did not exist; what I had actually drawn was a line around
            # the one shape somebody had measured, with a justification invented afterwards. That is
            # the rationalisation shape this run keeps paying for, and the second time in two rounds
            # the arm inside a `try:` body reddened **correct code**.
            #
            # The honest property is SYNTACTIC and is now stated as such: *the arm is not guarded by
            # a branch a reader can see.* A `with`, an `async with` and a `try` body at depth 1 all
            # satisfy it; an `if`/`else`, a loop and an `except`/`finally` handler do not. **What it
            # deliberately does NOT claim** is that the arm executes — no static rule can, because
            # `__enter__` can raise, and pretending otherwise is what made the previous version's
            # comment false. The gate's subject is *"was arming written as a decision or as a
            # condition"*, and that is answerable from the parse tree.
            top_level_arm_lines = {
                c.lineno for c in _unconditional_calls(
                    fn.body, lambda c: _called_name(c) == "arm_turn_surface", _narrows)
            }
            for n in ast.walk(fn):
                if isinstance(n, ast.Assign):
                    # `p = client.get_tool_definitions` — the alias route past a name-matching gate.
                    v = n.value
                    if isinstance(v, ast.Attribute) and v.attr in _NARROWING_CALLS:
                        aliases.append((n.lineno, v.attr))
                if not isinstance(n, ast.Call):
                    continue
                name = _called_name(n)
                f = n.func
                if name == "arm_turn_surface":
                    arms.append(n.lineno)
                    if n.lineno not in top_level_arm_lines:
                        conditional.append(n.lineno)
                elif (name == "set" and isinstance(f, ast.Attribute)
                        and isinstance(f.value, ast.Attribute)
                        and f.value.attr == "surface_withheld"):
                    raw_sets.append(n.lineno)
            out[f"{mod}::{fn.name}"] = (
                sorted(arms), sorted(raw_sets), narrowings, sorted(aliases), sorted(conditional),
            )
    return out


#: Entry points that reach a narrowing but are NOT turns — each needs a stated reason, because
#: "it is not a turn" is exactly what would be said about a turn nobody armed.
_NOT_A_TURN = {
    # 🔴 THREE ENTRIES WERE DELETED FROM HERE, and their deletion is the finding.
    # `_stream_with_tools`, `_emit_chat_turn` and `_run_subagent_call` were exempted **pre-emptively**
    # — discovery never produced them, so nothing exercised the exemption, and if one had later
    # BECOME a turn this list would have absolved it in silence. An allow-list nobody checks is a
    # permanent hole with a reason attached to it, which reads like care and behaves like a
    # blindfold. `test_NO_ALLOW_LIST_ENTRY_IS_STALE` now refuses an entry the sweep cannot see.
    #
    # `_compute_rail_drive_context` IS discovered and IS genuinely inside an armed turn.
    "services/stream_service.py::_compute_rail_drive_context",
    # `/v1/chat/tools/catalog` — the UI's tool-picker feed. It fetches and filters the catalogue,
    # so the sweep finds it, but **no model is offered anything**: there is no turn for a narrowing
    # to belong to, and `record_catalogue_unavailable` correctly no-ops unarmed rather than
    # attributing a row to a turn that never happened.
    #
    # 🔴 THE REASON ABOVE WAS FACTUALLY WRONG FOR TWO ROUNDS. It said the record "correctly no-ops
    # unarmed" — and this run DELETED that no-op: a narrowing now opens its own sink. The exemption
    # survived on a justification that had stopped being true, which is the same failure as a stale
    # allow-list entry, one level up: the entry was live, and its REASON was stale.
    #
    # The true reason: no model is offered anything here, so there is no turn for a narrowing to
    # belong to. What it now costs is one sink allocated per picker request and discarded with the
    # context — a real cost, stated, not a claim of zero.
    #
    # 🔶 Noted while classifying it, NOT fixed here because it is outside scope and a silent fix is
    # how scope drifts: it calls `get_tool_definitions()` with **no `user_id`**, so the picker shows
    # the platform catalogue without that user's external-MCP overlay.
    "routers/catalog.py::list_tools_catalog",
    # `PATCH /v1/chat/sessions/{id}` — it fetches the catalogue to VALIDATE that the names a user
    # pinned are real, and 422s on an unknown one. A settings write, not a turn: no model, no
    # surface, and the fetch narrows nothing — it is a membership check whose failure is a loud
    # HTTP error rather than a silent absence, which is the opposite of what CP-0.2 records.
    "routers/sessions.py::patch_session",
    # `POST .../permissions` → `_assert_known_tool` — the same shape: the catalogue is read to
    # reject an unknown tool name, and the failure is a 4xx the caller sees.
    "routers/tool_permissions.py::set_permission",
    "routers/tool_permissions.py::_assert_known_tool",
    # `tool_surface`'s own budgeting helpers. They ARE narrowing machinery — they run inside a turn
    # that has already armed, and arming here would discard what surface assembly collected. Found
    # only once the sweep was widened past `services/` + `routers/`, which is the widening working.
    "services/tool_surface.py::effective_enabled_tools",
    # 🔴 **THIS ENTRY IS ROUTE 22, CONVERTED FROM A BLANKET RULE INTO A DECISION.** It was exempt by
    # `if fn.name in _NARROWING_CALLS: continue` — a bare name matched across all of `app/`, with no
    # reason at any site and outside `test_NO_ALLOW_LIST_ENTRY_IS_STALE`'s reach. A verifier proved
    # that rule load-bearing: disabling it turned the gate `2 failed`, revealing exactly this
    # function. So the rule was silencing a real offender, and the offender was never judged.
    #
    # Judged now, and the reason is the same one that acquits `effective_enabled_tools` above and
    # is true of the code: its signature takes `withheld_sink: list[dict] | None = None` and its two
    # call sites (`stream_service.py:6073`, `:8119`) are both inside an already-armed turn. **A
    # function that RECEIVES the turn's sink is by definition running inside a turn somebody else
    # armed**, and arming here would replace a sink already holding rows — which is the discard the
    # sixth recurrence was about.
    "services/tool_surface.py::discovery_seed_for_surface",
}


#: Every call inside a turn entry point that can remove a declaration from what the model is
#: offered. A new one added here without an earlier arming is exactly the recurrence.
_NARROWING_CALLS = {
    "get_tool_definitions", "get_admin_tool_definitions",
    "filter_intent_gated_setup_tools", "discovery_seed_for_surface", "_budget_and_register",
}


class TestTheTurnSinkIsArmedBeforeAnythingNarrows:
    """🔴 SEVENTH RECURRENCE OF ARM-AFTER-USE — and the one that proves a substring window is not a
    gate.

    The sixth fix armed the sink above the intent gate, believed then to be the turn's first
    narrowing, and left a comment stating the rule in the imperative. U-2 then added an **earlier**
    narrowing — the catalogue fetch — and the arming stayed where it was: 382 lines below it, in the
    same function, under the sentence forbidding exactly that. A verifier measured the result on a
    real turn: `catalog: [] | _catalogue_outage: False`. Both halves of U-2 were inert in production
    while every U-2 test was green, because each armed its own sink first.

    The old gate could not see it. It searched a 900-character window before
    `filter_intent_gated_setup_tools(` — and that window was satisfied, correctly, by an arming that
    was nonetheless far too late for a call the window was not drawn around. **A gate anchored to one
    call site cannot notice a narrowing that moves earlier than the anchor.**

    So this compares LINE NUMBERS IN THE PARSE TREE: the arming against *every* call in
    `_NARROWING_CALLS`, in both entry points. Adding a narrowing above the arming reds it; deleting
    the arming reds it; re-arming anywhere in the body reds it. All three were injected into the real
    module and each was measured red before being reversed.

    **What this gate cannot see, measured rather than guessed.** It matches by *called name*, so an
    alias walks straight past it — `p = knowledge_client.get_tool_definitions; p(...)` above the
    arming was injected and stayed **green**. It also cannot see a narrowing that happens inside a
    callee rather than at a call site named here, and `_NARROWING_CALLS` is a hand-kept list: a
    genuinely new narrowing stage is invisible until someone adds it. That last one is the residual
    with teeth, and it is the same residual the previous gate died of — narrower now, because this
    list is one place and the old anchor was one call site.
    """

    def test_EVERY_DISCOVERED_entry_point_arms_exactly_once_and_unconditionally(self):
        found = {k: v for k, v in _turn_entry_calls().items() if k not in _NOT_A_TURN}
        # Discovered, not asserted-as-a-subset. The three known today; a fourth appearing here is
        # the gate WORKING, and it must then be armed like the rest — or be given a STATED reason
        # in `_NOT_A_TURN`, which is a decision someone has to write down rather than a silence.
        assert {k.split("::")[1] for k in found} >= {
            "stream_response", "resume_stream_response", "voice_stream_response",
        }, f"a turn entry point vanished or was renamed: {sorted(found)}"
        for fn, (arms, raw_sets, _, aliases, conditional) in found.items():
            assert len(arms) == 1, (
                f"{fn}: expected exactly one arm_turn_surface(), found {len(arms)} at {arms}. "
                f"A second arming DISCARDS everything the first collected; zero means every "
                f"narrowing in this turn registers nowhere."
            )
            assert not conditional, (
                f"{fn}: the arming at {conditional} is nested inside a branch, so the turn arms "
                f"only sometimes — measured green by a verifier on the previous gate"
            )
            assert not raw_sets, (
                f"{fn}: a raw surface_withheld.set() at {raw_sets} bypasses the named entry point"
            )
            assert not aliases, (
                f"{fn}: a narrowing call is aliased at {aliases}; this gate matches by called name, "
                f"so an alias walks past the ordering check below"
            )

    def test_NO_ALLOW_LIST_ENTRY_IS_STALE(self):
        """🔴 An allow-list nobody checks is a permanent hole with a reason attached to it.

        A verifier found three `_NOT_A_TURN` entries that discovery does not even produce — they
        were pre-emptive exemptions nothing exercised, so if one of them later BECAME a turn the
        list would silently absolve it. The failure mode is the same as a `# noqa` for a warning
        that no longer fires: it looks like care and behaves like a blindfold.
        """
        discovered = set(_turn_entry_calls())
        stale = sorted(_NOT_A_TURN - discovered)
        assert not stale, (
            f"{stale} are exempted and not discovered — nothing exercises the exemption, so it "
            f"cannot be trusted to still be correct. Delete the entry, or find out why the sweep "
            f"stopped seeing it."
        )

    def test_no_narrowing_precedes_the_arming__INCLUDING_THROUGH_A_HELPER(self):
        for fn, (arms, _, narrowings, _a, _c) in _turn_entry_calls().items():
            if fn in _NOT_A_TURN:
                continue
            assert arms, f"{fn}: no arm_turn_surface() at all — this is the defect verbatim."
            assert narrowings, f"{fn}: no narrowing call found — the gate has lost its subject"
            early = [(line, name) for line, name in narrowings if line < arms[0]]
            assert not early, (
                f"{fn}: {early} run BEFORE the sink is armed at line {arms[0]}. Whatever they "
                f"withhold registers nowhere — this is the defect, not a style point. "
                f"(`a->b` means the narrowing is inside helper `a`, at that call site.)"
            )

    def test_the_gate_reds_on_each_of_the_EIGHT_measured_bypasses(self):
        """The control, over **every** route a verifier has driven past this gate in two rounds.

        Round 8 found four: an alias (disclosed), a module-level helper (**a routine refactor**, and
        it reproduced the end-to-end defect while the gate said `14 passed`), a conditional arm, and
        a fourth entry point. Round 9 found four more past the *fixed* gate: a helper **one module
        over**, the same refactor through **two levels** of helper, a `_`-prefixed entry point, and
        an entry point in a **third module**. Each is exercised here on synthetic input, so a change
        to the comparison itself reds rather than silently narrowing the gate again.
        """
        deep = (
            "import x\n"
            "def _leaf(u):\n"
            "    return x.get_tool_definitions(user_id=u)\n"
            "def _mid(u):\n"
            "    return _leaf(u)\n"                       # two levels — round 9 route 2
            "async def stream_response(u):\n"
            "    cat = _mid(u)\n"
            "    if u:\n"
            "        x.arm_turn_surface()\n"              # conditional arm
            "    p = x.get_tool_definitions\n"            # alias route
            "    return cat, p\n"
            "async def _private_response(u):\n"           # `_`-prefixed — round 9 route 3
            "    return x.get_tool_definitions(user_id=u)\n"
        )
        tree = ast.parse(deep)
        all_fns = {f.name: f for f in tree.body
                   if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
        reaching = _narrowing_helpers(all_fns)
        assert {"_leaf", "_mid"} <= reaching, (
            "the transitive closure stopped short — a two-level helper is invisible (route 2)"
        )

        entries = [f for f in tree.body if isinstance(f, ast.AsyncFunctionDef)]
        assert {f.name for f in entries} == {"stream_response", "_private_response"}, (
            "discovery skips `_`-prefixed entry points — route 3"
        )
        first = all_fns["stream_response"]
        assert any("->" in n for _, n in _narrowings_in(first, reaching)), (
            "the helper route is invisible — round 8 route 1"
        )
        top_level = {s.value.lineno for s in first.body
                     if isinstance(s, (ast.Expr, ast.Assign)) and isinstance(s.value, ast.Call)
                     and _called_name(s.value) == "arm_turn_surface"}
        assert [n.lineno for n in ast.walk(first) if isinstance(n, ast.Call)
                and _called_name(n) == "arm_turn_surface" and n.lineno not in top_level], (
            "a conditional arm reads as unconditional — round 8 route 3"
        )
        assert [n.lineno for n in ast.walk(first) if isinstance(n, ast.Assign)
                and isinstance(n.value, ast.Attribute)
                and n.value.attr in _NARROWING_CALLS], "the alias route is invisible"
        assert _narrowings_in(all_fns["_private_response"], reaching), (
            "the `_`-prefixed entry point narrows and was ignored"
        )
        # Routes 1 and 4 — cross-module — are structural: `_TURN_SCOPE` is a directory sweep and
        # `all_fns` is built across every module in it, so a helper or an entry point in another
        # file is in scope by construction. Asserted on the real tree, not on a fixture:
        real = _turn_entry_calls()
        assert real, "the sweep found no entry point at all"
        assert any(k.startswith("services/voice_stream_service.py") for k in real), (
            "the sweep no longer reaches a second module — routes 1 and 4 reopen"
        )

    def test_the_emit_path_ADOPTS_the_armed_sink_rather_than_replacing_it(self):
        """`_emit_chat_turn` runs after surface assembly, so a fresh list there would discard the
        records this whole mechanism exists to carry."""
        src = _stream_src()
        assert "_surface_sink = instrument.surface_withheld.get()" in src, (
            "the turn replaces the armed sink instead of adopting it"
        )

    def test_the_armer_actually_arms(self):
        """The production function, driven — not a hand-made sink. A bare context registers nothing
        (the defect's own shape); after `arm_turn_surface()` the same call lands."""
        import contextvars

        # 🔴 THIS ASSERTED THAT AN UNARMED CONTEXT RECORDS **NOTHING**, and that property has been
        # deliberately removed — it was the property that made ordering load-bearing, and eight
        # measured routes walked past the gate protecting it. A narrowing now opens its own sink.
        # What survives, and is the thing worth asserting, is that arming starts a turn CLEAN:
        # `record_*` adopts, `arm_turn_surface` replaces.
        def _unarmed_still_records():
            instrument.record_catalogue_unavailable(stage="catalogue_unavailable", reason="boom")
            return instrument.catalogue_outage_registered()

        assert contextvars.copy_context().run(_unarmed_still_records) is True, (
            "a narrowing with no sink was lost — the defect eight bypass routes all ended in"
        )

        def _armed():
            sink = instrument.arm_turn_surface()
            instrument.record_catalogue_unavailable(stage="catalogue_unavailable", reason="boom")
            return instrument.catalogue_outage_registered(), sink

        outage, sink = contextvars.copy_context().run(_armed)
        assert outage is True
        assert sink and sink[0]["scope"] == instrument.SCOPE_CATALOGUE


class TestTheFactsTHIS_ROUND_TIGHTENED_ARE_EACH_GUARDED:
    """🔴 **THREE CONSECUTIVE ROUNDS SHIPPED STRENGTHENINGS THAT NOTHING WOULD NOTICE BEING
    REVERTED.** A verifier weakened each one and measured the suite green on most of them, then
    proved every weakening restores a real defect end-to-end. *"A fix without a red-able test is not
    a closed finding"* is a standing rule of this run; the round that closed three arm-order routes
    added **zero** assertions and left the suite count unchanged at `2 failed, 115 passed`.

    Each test below names the defect its weakening restores, not the line it covers.
    """

    # ── The outage fact's four orderings ────────────────────────────────────────────────────────
    #
    # The fact moved from a `ContextVar[bool]` (lifetime: the context, i.e. a pooled thread) onto the
    # recorder (lifetime: exactly one turn). A verifier proved no single assignment of the boolean
    # was correct in both orders — monotone reds two tests, lowering keeps the erasure — so the four
    # orderings are asserted together. Two of them were green before; the other two are the live
    # defects the rehousing exists to make unconstructible.

    def _turn(self, *, drain=False, arm_first=True):
        from app.services import instrument

        rec = None
        if arm_first:
            instrument.arm_turn_surface()
        instrument.record_catalogue_unavailable(stage="catalogue_unavailable", reason="boom")
        if not arm_first:
            rec = instrument.AdvertisedToolsRecorder()
            instrument.arm_turn_surface()          # adopts a NON-empty sink: this turn narrowed
        if drain:
            rec = rec or instrument.AdvertisedToolsRecorder()
            rec.absorb(instrument.surface_withheld.get())
        return instrument.catalogue_outage_registered()

    def test_THE_OUTAGE_FACT_SURVIVES_A_DRAIN__and_does_not_survive_the_TURN(self):
        """🔴 **THE ORDERING TABLE, ASSERTED — AND THE CLAIM IT REPLACES WAS THAT THIS COULD NOT
        BE DONE.**

        The previous version of this test asserted the arm-after-drain ordering as a **defect**,
        under a note saying no arrangement inside `instrument.py` could satisfy every ordering
        without a turn identity. A verifier refuted that in one line: the arrangement is the one that
        was there before — the write in `record_catalogue_unavailable` plus the derivation at the arm
        — and the argument I had rested the impossibility on was **my own sentence, gone vacuous**
        (with the writer deleted, "monotone" and "lowering" are the same program, and the monotone
        variant reds 0 of 2255).

        Six orderings, all measured against this tree rather than reasoned about:

        | ordering | | |
        |---|---|---|
        | arm → record → read | `True` | the live production shape |
        | arm → record → **drain** → read | `True` | the write is what buys this |
        | record → recorder → arm → drain → read | `True` | an arm joining a turn that already narrowed |
        | two recorders in one turn | `True` | neither owns the fact, so neither can lose it |
        | turn A drains → turn B arms → read | `False` | the derivation is what buys this |

        **The one residual, named rather than buried:** a turn that records and *never* calls
        `arm_turn_surface()` leaves its row in the context for the next turn. That rides the
        **sink**, not this flag, so no arrangement of this variable addresses it — and the shape that
        produces it (an entry point that narrows without arming) is what
        `TestTheTurnSinkIsArmedBeforeAnythingNarrows` statically forbids. Two mechanisms, one hole,
        and the other mechanism is the one that owns it.
        """
        import contextvars

        from app.services import instrument

        def _turn(*, drain, arm_first=True):
            rec = None
            if arm_first:
                instrument.arm_turn_surface()
            instrument.record_catalogue_unavailable(stage="catalogue_unavailable", reason="boom")
            if not arm_first:
                rec = instrument.AdvertisedToolsRecorder()
                instrument.arm_turn_surface()      # adopts a NON-empty sink: this turn narrowed
            if drain:
                rec = rec or instrument.AdvertisedToolsRecorder()
                rec.absorb(instrument.surface_withheld.get())
            return instrument.catalogue_outage_registered()

        ctx = contextvars.copy_context
        assert ctx().run(lambda: _turn(drain=False)) is True, (
            "the live production ordering lost the outage — the model would not be told its tools "
            "were unreachable, which is U-2's founding defect"
        )
        assert ctx().run(lambda: _turn(drain=True)) is True, (
            "THE DRAIN ERASED THE TURN'S OUTAGE. The persisted row now says outage while the model "
            "was told nothing — worse than either being wrong alone. This is what the write in "
            "`record_catalogue_unavailable` exists for; three rounds measured that write `inert` "
            "and deleting it is what made this ordering fail."
        )
        assert ctx().run(lambda: _turn(arm_first=False, drain=True)) is True, (
            "arming after a narrowing erased the narrowing's own fact"
        )

        def _two_recorders():
            instrument.arm_turn_surface()
            instrument.record_catalogue_unavailable(stage="s", reason="r")
            first = instrument.AdvertisedToolsRecorder()
            first.absorb(instrument.surface_withheld.get())
            instrument.AdvertisedToolsRecorder()          # a second one, same turn
            return instrument.catalogue_outage_registered()

        assert ctx().run(_two_recorders) is True, (
            "a second recorder in one turn lost the first one's fact — the failure mode of homing "
            "this on the recorder, which a verifier measured and which is why it is not homed there"
        )

        def _two_turns():
            first = _turn(drain=True)
            instrument.arm_turn_surface()                 # turn B, same context, drained sink
            return first, instrument.catalogue_outage_registered()

        first, second = ctx().run(_two_turns)
        assert (first, second) == (True, False), (
            f"turn A={first}, turn B={second}. A `True` in turn B is the pooled-worker leak: a "
            f"healthy turn told its tools were unreachable. A `False` in turn A is the drain erasure."
        )

    def test_THE_RECORDER_IS_THE_SECOND_WITNESS__and_it_splits_what_the_flag_cannot(self):
        """🔴 **The ordering I called unaddressable, closed by a six-line patch a verifier
        wrote.** My argument was that `O_K` and the two-turn case are byte-identically the same
        execution so no assignment of the flag can split them. The premise is true; the conclusion
        does not follow. They are identical *in the ContextVars* and differ in **which recorder the
        reader holds** — in `O_K` the drained row is in a recorder that is still live, in the
        two-turn case turn B builds its own.

        Flag-only answers 3 of 9 orderings wrong, including `O_R`, an eighth the previous round did
        not find. The recorder as a second witness answers 8 of 9. The survivor is `O_J` — a turn
        that records and never arms — and that one **is** genuinely sink-borne, which is what the
        comment said before `O_K` was discovered. I answered the discovery by widening the excuse.
        """
        import contextvars

        from app.services import instrument

        def _O_K():
            instrument.arm_turn_surface()
            instrument.record_catalogue_unavailable(stage="s", reason="r")
            rec = instrument.AdvertisedToolsRecorder()
            rec.absorb(instrument.surface_withheld.get())
            instrument.arm_turn_surface()                 # a second entry point, same turn
            return instrument.catalogue_outage_registered(rec)

        def _O_R():
            instrument.arm_turn_surface()
            instrument.record_catalogue_unavailable(stage="s", reason="r")
            rec = instrument.AdvertisedToolsRecorder()
            rec.absorb(instrument.surface_withheld.get())
            instrument.arm_turn_surface()
            rec.absorb(instrument.surface_withheld.get())  # drains again, now empty
            return instrument.catalogue_outage_registered(rec)

        def _O_D():
            instrument.arm_turn_surface()
            instrument.record_catalogue_unavailable(stage="s", reason="r")
            instrument.AdvertisedToolsRecorder().absorb(instrument.surface_withheld.get())
            instrument.arm_turn_surface()                 # turn B, same context
            return instrument.catalogue_outage_registered(
                instrument.AdvertisedToolsRecorder())     # turn B's OWN recorder

        ctx = contextvars.copy_context
        assert ctx().run(_O_K) is True, (
            "a second arming within one turn erased the outage the first one recorded — the ordering "
            "the builder called unaddressable, and the recorder is what addresses it"
        )
        assert ctx().run(_O_R) is True, "a second drain erased it"
        assert ctx().run(_O_D) is False, (
            "turn A's outage reached turn B through its OWN recorder — the recorder must witness "
            "only what it drained, or it is the leak the flag already was"
        )

    # ── The three value bounds ──────────────────────────────────────────────────────────────────

    def test_a_HOSTILE_SCOPE_VALUE_cannot_take_the_turn_down_at_the_ARM(self):
        """🔴 The row TYPE was bounded and the row's CONTENTS were not, in the commit whose headline
        was that `isinstance` was the bug. `arm_turn_surface` is the first statement of every turn
        entry point, so a `RuntimeError` there takes the whole turn with it — the
        crash-inside-its-own-fix pattern at the one place where it costs everything."""
        import contextvars

        from app.services import instrument

        class Hostile:
            def __eq__(self, other):
                raise RuntimeError("a comparison that runs user code")

            def __hash__(self):
                return 0

        def _drive():
            sink = instrument.arm_turn_surface()
            sink.append({"scope": Hostile(), "stage": "s", "reason": "r"})
            instrument.arm_turn_surface()                     # must not raise
            return instrument.catalogue_outage_registered()   # nor must this

        assert contextvars.copy_context().run(_drive) is False

    def test_COUNT_FALSE_IS_NOT_A_COUNT__at_every_door_it_can_enter_by(self):
        """🔴 Five rounds. `True` IS an `int` in Python, so `isinstance(count, int)` let
        `count: false` persist into the jsonb as a boolean where every reader expects a number — and
        `count: true` would persist as a size of `1`, a fabricated number for an outage whose entire
        point is that the size is unknown. Bounded at all three doors, not the one named."""
        import contextvars

        from app.services import instrument

        # 🔴 **THE TWO DOORS ARE ASSERTED SEPARATELY, AND THE THIRD IS NAMED AS REDUNDANT.** Driving
        # all three through one pipeline made each individual bound SILENT — weakening any one left
        # the suite green because a later one caught it. That is defence in depth working and a test
        # that cannot see it, which is the same "an alternation is not two assertions" mistake this
        # run has now made twice in one file. So: door 1 is read at the SINK, door 3 at the RECORDER,
        # and `absorb`'s bound is stated for what it is — a defence that feeds door 3, redundant by
        # construction and deliberately not claimed as independently guarded.
        def _door_1():
            sink = instrument.arm_turn_surface()
            instrument.record_catalogue_unavailable(stage="s", reason="r", count=False)
            return list(sink)

        def _door_3():
            rec = instrument.AdvertisedToolsRecorder()
            rec.record_catalogue_withheld(stage="s3", reason="r", count=True)
            return rec.withheld_json()

        for door, rows in (("record_catalogue_unavailable", contextvars.copy_context().run(_door_1)),
                           ("AdvertisedToolsRecorder.record_catalogue_withheld",
                            contextvars.copy_context().run(_door_3))):
            assert rows, f"{door} recorded nothing, so this asserts nothing"
            for r in rows:
                assert type(r.get("count")) is not bool, (
                    f"a boolean reached the `count` column through {door}: {r}. Absent and zero are "
                    f"different facts, and `true` is neither of them."
                )

    def test_A_SINK_THAT_RESISTS_CLEARING_LOSES_NOTHING(self):
        """🔴 The read and the clear shared one `try`, so a container that resists `del` discarded
        rows the read had ALREADY produced — the comment said *"read defensively, then clear"* and
        the code threw the read away when the clear failed. A strict behavioural regression against
        the artifact it replaced, on inputs that one handled. A hostile container must degrade to
        the PREVIOUS defect (a row recorded twice) rather than to silence: a duplicate row is
        visible and a lost one is not."""
        from app.services import instrument

        class Undeletable(list):
            def __delitem__(self, key):
                raise RuntimeError("this container resists clearing")

        rows = [{"scope": instrument.SCOPE_CATALOGUE, "stage": "s", "reason": "r"}]
        for sink in (Undeletable(rows), tuple(rows), (r for r in rows)):
            rec = instrument.AdvertisedToolsRecorder()
            rec.absorb(sink)
            assert rec.withheld_json(), (
                f"a {type(sink).__name__} sink lost EVERY row; a matched plain list records it"
            )


class TestTheARM_ORDER_GATE_SEES_THE_SHAPES_IT_WAS_BLIND_TO:
    """🔴 **ROUTES 19-22, AND THE GATE'S OWN FIXES WERE UNGUARDED.** Three routes were closed by a
    round that added no assertion over any of them, and the same commit opened two more. Every probe
    below is a real module written under `app/`, swept by the real `_turn_entry_calls()`, and removed
    in a `finally` — because a gate over a synthetic AST proves the helper works, not the sweep.
    """

    _PROBE = '''
from app.client.knowledge_client import KnowledgeClient

{decorator}def {name}(user_id):
    tools = {call}
    return tools
'''

    def _sweep(self, name, *, body, prefix="_lwprobe"):
        """Write one module under `app/services/`, sweep it, remove it. Never left behind."""
        import pathlib

        base = _swept_root() / "services"
        path = base / f"{prefix}_{name}.py"
        path.write_text(body, encoding="utf-8")
        try:
            return _turn_entry_calls()
        finally:
            path.unlink(missing_ok=True)

    def _narrows_unarmed(self, name, body):
        found = self._sweep(name, body=body)
        key = next((k for k in found if k.endswith(f"::{name}")), None)
        return key, (found.get(key) if key else None)

    def test_a_SYNC_def_entry_point_is_discovered(self):
        """ROUTE 19. `ast.AsyncFunctionDef` only — a sync entry point that narrows was invisible,
        and nothing about a turn requires a coroutine."""
        key, entry = self._narrows_unarmed("sync_probe", (
            "from app.client.knowledge_client import KnowledgeClient\n"
            "def sync_probe(c):\n"
            "    return c.get_tool_definitions()\n"
        ))
        assert key and not entry[0], f"a sync entry point that narrows was not discovered: {key}"

    def test_a_SAME_NAMED_ARMING_HELPER_ELSEWHERE_does_not_absolve_it(self):
        """ROUTE 20, created by the fix that widened the sweep to all of `app/`. `arming` was keyed
        by BARE NAME across 641 names, and it grants an EXEMPTION — so an arming helper anywhere in
        `app/` absolved a genuinely un-armed entry point. An over-approximation is only safe in the
        direction of suspicion."""
        import pathlib

        base = _swept_root()
        decoy = base / "agentruntime" / "_lwprobe_decoy.py"
        decoy.write_text(
            "from app.services.instrument import arm_turn_surface\n"
            "def twin_probe():\n"
            "    return arm_turn_surface()\n", encoding="utf-8")
        try:
            key, entry = self._narrows_unarmed("twin_probe", (
                "from app.client.knowledge_client import KnowledgeClient\n"
                "async def twin_probe(c):\n"
                "    return await c.get_tool_definitions()\n"
            ))
            assert key and not entry[0], (
                "a same-named arming helper in another package absolved an un-armed entry point"
            )
        finally:
            decoy.unlink(missing_ok=True)

    def test_an_UNDERSCORED_entry_point_narrowing_TRANSITIVELY_is_discovered(self):
        """ROUTE 21, opened by the fix for route 20 — twelve lines below a docstring saying entry
        points are discovered *"including `_`-prefixed ones, because a leading underscore is a
        naming convention and not a guarantee that nothing routes to it."* `narrowings` comes from
        the TRANSITIVE closure and the filter admitted only a DIRECT primitive call, so one hop of
        helper made it invisible. The three functions deliberately removed from `_NOT_A_TURN` are
        all `_`-prefixed."""
        key, entry = self._narrows_unarmed("_under_probe", (
            "from app.client.knowledge_client import KnowledgeClient\n"
            "def _under_helper(c):\n"
            "    return c.get_tool_definitions()\n"
            "async def _under_probe(c):\n"
            "    return _under_helper(c)\n"
        ))
        assert key and not entry[0], (
            "a `_`-prefixed entry point narrowing through one helper was invisible to the sweep"
        )

    def test_an_entry_point_NAMED_LIKE_A_PRIMITIVE_is_discovered(self):
        """ROUTE 22, opened by the same fix: `if fn.name in _NARROWING_CALLS: continue`, a bare-name
        exemption across all of `app/`, with no allow-list entry, no stated reason, and outside
        `test_NO_ALLOW_LIST_ENTRY_IS_STALE`'s reach. It was load-bearing — disabling it turned the
        pristine gate `2 failed` — so it was silencing a real offender by name. `app/agentruntime/`
        defines none of those names today and CP-2's arming runtime is scheduled for that package."""
        for primitive in sorted(_NARROWING_CALLS):
            body = (
                "from app.client.knowledge_client import KnowledgeClient\n"
                f"async def {primitive}(c):\n"
                "    return await c.get_admin_tool_definitions()\n"
            )
            found = self._sweep(f"named_{primitive}", body=body)
            key = next((k for k in found
                        if k.startswith("services/_lwprobe_named_") and k.endswith(primitive)), None)
            assert key and not found[key][0], (
                f"an entry point named {primitive!r} was exempted by its NAME, with no reason "
                f"recorded and no staleness test over it"
            )

    def test_a_TOP_LEVEL_ARM_INSIDE_AN_ASYNC_WITH_is_not_CONDITIONAL(self):
        """ROUTE 18 — and this one is a FALSE POSITIVE on correct code, three rounds. Only `fn.body`
        counted, so an arm that is the first statement inside `async with AsyncExitStack():` reddened
        as conditional. **A gate that reds on correct code is one that gets deleted the first time it
        is inconvenient**, and the shape is ordinary — `voice_stream_service.py:237` is one refactor
        from being written that way."""
        key, entry = self._narrows_unarmed("with_probe", (
            "import contextlib\n"
            "from app.client.knowledge_client import KnowledgeClient\n"
            "from app.services.instrument import arm_turn_surface\n"
            "async def with_probe(c):\n"
            "    async with contextlib.AsyncExitStack():\n"
            "        arm_turn_surface()\n"
            "        return await c.get_tool_definitions()\n"
        ))
        assert key, "the probe was not discovered, so this asserts nothing"
        arms, _raw, _narrowings, _aliases, conditional = entry
        assert arms and not conditional, (
            f"an unconditional arm inside `async with` was reported CONDITIONAL: {entry}"
        )

    def test_the_DELEGATION_EXEMPTION_is_not_ordering_dead_branch_or_liveness_BLIND(self):
        """🔴 **ROUTE 23 — the third arm-order fix to create the next hole.** The exemption for a
        function that delegates to something that arms was computed with `ast.walk`, which answers
        *"does this token appear anywhere in the tree"* when the question is *"does this run, before
        anything narrows"*. Three defeats, each `6 passed` against a control at `2 failed`: narrow
        first and delegate afterwards; the delegating call under `if False:`; the delegating call
        inside a nested `def` nothing invokes.

        The exemption now uses the SAME definition of "unconditional" as the arming check, so the
        two cannot drift — which is how route 23 was born in the first place, one relation computed
        two ways.
        """
        _IMPORTS = ["from app.client.knowledge_client import KnowledgeClient",
                    "from app.services.stream_service import stream_response"]
        cases = {
            "narrow-then-delegate": ("d1_probe", _IMPORTS + [
                "async def d1_probe(c):",
                "    tools = await c.get_tool_definitions()",
                "    return stream_response(tools)"]),
            "delegation under a dead branch": ("d2_probe", _IMPORTS + [
                "async def d2_probe(c):",
                "    if False:",
                "        return stream_response(None)",
                "    return await c.get_tool_definitions()"]),
            "delegation inside an uncalled nested def": ("d3_probe", _IMPORTS + [
                "async def d3_probe(c):",
                "    def _never():",
                "        return stream_response(None)",
                "    return await c.get_tool_definitions()"]),
        }
        for label, (fn, lines) in cases.items():
            key, entry = self._narrows_unarmed(fn, "\n".join(lines) + "\n")
            assert key and not entry[0], (
                f"{label}: the delegation exemption absolved an entry point that narrows with no "
                f"arming. The exemption is about what RUNS before the narrowing, not about which "
                f"tokens appear in the tree."
            )

    def test_an_ARM_INSIDE_A_TRY_BODY_is_not_CONDITIONAL_either(self):
        """🔴 **W2 — route 18's class in a new spelling, and my stated reason for it was refuted in
        the same round.** I excluded `Try` because *"an arm inside a `try` is one exception away
        from a turn that narrows into nothing"* — and a verifier pointed out that a `with` whose
        `__enter__` raises is the identical situation and was **already accepted**. The distinction
        did not exist; I had drawn a line around the one shape somebody had measured and invented
        the justification afterwards.

        The property is syntactic and now says so: *the arm is not guarded by a branch a reader can
        see.* It does not claim the arm executes — no static rule can."""
        key, entry = self._narrows_unarmed("try_probe", "\n".join([
            "from app.client.knowledge_client import KnowledgeClient",
            "from app.services.instrument import arm_turn_surface",
            "async def try_probe(c):",
            "    try:",
            "        arm_turn_surface()",
            "        return await c.get_tool_definitions()",
            "    except Exception:",
            "        return []"]) + "\n")
        assert key, "the probe was not discovered, so this asserts nothing"
        arms, _raw, _narrowings, _aliases, conditional = entry
        assert arms and not conditional, (
            f"an arm as the first statement of a `try:` body was reported CONDITIONAL: {entry}. "
            f"That is a false positive on correct code, and a gate that reds on correct code is one "
            f"that gets deleted the first time it is inconvenient."
        )

    def test_EVERY_PROBE_IS_WRITTEN_INTO_THE_TREE_THE_GATES_ACTUALLY_SWEEP(self):
        """🔴 **SIX ROUNDS: SIX PROBE WRITERS TYPED THE SCOPE ROOT WHILE BOTH GATES READ IT.**

        Every probe test in this class is an experiment whose independent variable is *"a module
        appears inside the swept tree"*. Six of them named that tree with a literal `"app"`, and the
        two gates derive it from `_TURN_SCOPE_ROOT`. Move or rename the root — which `_TURN_SCOPE_
        ROOT`'s own comment says is coming, because CP-2's runtime lands in a new package — and the
        gates follow while every probe lands outside the sweep. Each of those tests then passes,
        having asserted nothing, and this file's whole record of routes 17–25 becomes theatre.

        This is the same defect the terminal-write gate convicts other code of by name (*"a gate
        whose file set is TYPED OUT cannot notice a writer arriving somewhere else"*) — committed by
        the tests written to prove it.

        Held as a property, not as six repairs, because the seventh writer is the one that matters.

        🔴 **AND THE FIRST VERSION OF THIS GATE CAUGHT 2 OF 8 VEHICLES.** A verifier appended eight
        probe-writer shapes to this file and ran the real gate:

        * half one matched a `BinOp(/)` with the literal on the right, so **`.joinpath("app")`,
          `os.path.join` and string concatenation all walked past it**;
        * half two asserted that the *identifier* `_swept_root` or `_sweep` **appears somewhere in
          the function** — so a **dead `_ = _swept_root`** beside a typed root absolved it. *A test
          satisfied by a comment is not a test*; this was **a test satisfied by a token**, the
          fourth instance in this run and the second inside a repair for another;
        * and it only looked at `write_text`/`write_bytes` inside a `FunctionDef`, so `open(p, "w")`,
          `shutil.copyfile`, a write in a **lambda**, and a write at **module scope** were invisible.

        Both halves now bind what they are about. The literal is refused **anywhere** it appears,
        not in one syntactic form; and the path is required to *derive* from `_swept_root()` by
        assignment, which a mention cannot satisfy.
        """
        src = Path(__file__).read_text(encoding="utf-8")
        typed, stray = self._probe_writer_offenders(src)
        assert not typed, (
            f"line(s) {typed} spell the scope root {_TURN_SCOPE_ROOT!r} as a literal instead of "
            f"going through `_swept_root()`. The gates read `_TURN_SCOPE_ROOT`; a probe written "
            f"anywhere else is outside the sweep, and the test that wrote it goes green asserting "
            f"nothing. `/`, `.joinpath`, `os.path.join` and concatenation are all the same defect."
        )

        assert not stray, (
            f"{stray} write a file whose path does not DERIVE from `_swept_root()` - so it may "
            f"land outside the tree the gates sweep, and the assertion that follows would pass over "
            f"an experiment that never happened. Mentioning the helper is not deriving from it: a "
            f"dead `_ = _swept_root` defeated the previous version of this clause."
        )

        # \U0001F534 **THE CONTROL - the eight shapes a verifier used to defeat the first version,
        # plus two of my own.** Each is appended to this module's source in memory and the same
        # analysis is re-run; every one must be reported. Appending to the real file on disk is what
        # the verifier did, and it is what left it needing a byte-exact restore.
        VEHICLES = {
            "the typed root the gate names": [
                "def _v1():",
                "    p = Path(__file__).resolve().parents[1] / 'app' / 'services' / 'p.py'",
                "    p.write_text('x', encoding='utf-8')"],
            "`.joinpath` instead of `/`": [
                "def _v2():",
                "    p = Path(__file__).resolve().parents[1].joinpath('app').joinpath('p.py')",
                "    p.write_text('x', encoding='utf-8')"],
            "`.joinpath` PLUS a dead mention of the helper": [
                "def _v3():",
                "    _ = _swept_root",
                "    p = Path(__file__).resolve().parents[1].joinpath('app').joinpath('p.py')",
                "    p.write_text('x', encoding='utf-8')"],
            # 🔴 **AND v3 IS CAUGHT BY THE *LITERAL* CLAUSE, SO IT DOES NOT CONTROL THE DEAD-TOKEN
            # BYPASS AT ALL.** My own reversion prover exposed that: a control that is satisfied by
            # a different clause than the one it names measures nothing about that clause. This one
            # carries no literal, so only half two can catch it.
            "a dead mention of the helper, with NO literal to catch it": [
                "def _v3b():",
                "    _ = _swept_root",
                "    p = Path('/tmp').joinpath('services', 'p.py')",
                "    p.write_text('x', encoding='utf-8')"],
            "written through `open(path, 'w')`": [
                "def _v4():",
                "    p = Path(__file__).resolve().parents[1].joinpath('app', 'p.py')",
                "    open(p, 'w').write('x')"],
            "written through `shutil.copyfile`": [
                "def _v5():",
                "    p = Path(__file__).resolve().parents[1].joinpath('app', 'p.py')",
                "    shutil.copyfile('a', p)"],
            "written inside a lambda": [
                "_v6 = lambda: Path('x').joinpath('app', 'p.py').write_text('x')"],
            "written at module scope": [
                "_v7 = Path(__file__).resolve().parents[1].joinpath('app', 'p.py')",
                "_v7.write_text('x', encoding='utf-8')"],
            "an unrelated local named `_sweep`": [
                "def _v8():",
                "    _sweep = 1",
                "    p = Path(__file__).resolve().parents[1].joinpath('app', 'p.py')",
                "    p.write_text('x', encoding='utf-8')"],
            "os.path.join, which is not a BinOp at all": [
                "def _v9():",
                "    import os.path",
                "    p = os.path.join('app', 'p.py')",
                "    open(p, 'w').write('x')"],
            "concatenation": [
                "def _v10():",
                "    p = Path('x' + 'app' + '/p.py')",
                "    p.write_text('x', encoding='utf-8')"],
        }
        blind = []
        for label, lines in VEHICLES.items():
            t2, s2 = self._probe_writer_offenders(src + "\n\n" + "\n".join(lines) + "\n")
            if not (set(t2) - set(typed) or set(s2) - set(stray)):
                blind.append(label)
        assert not blind, (
            f"{len(blind)} of {len(VEHICLES)} probe-writer vehicles are invisible: {blind}. The "
            f"first version of this gate caught 2 of 8, and one of the six it missed was a DEAD "
            f"mention of the helper it asks for."
        )

    @staticmethod
    def _probe_writer_offenders(src: str):
        """`(literal_lines, non_deriving_writes)` for a module's source. Shared with the control."""
        tree = ast.parse(src)

        # Half one: the literal, ANYWHERE. Its own definition is the single exemption, by line.
        _defn = next((n.lineno for n in ast.walk(tree)
                      if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "_TURN_SCOPE_ROOT"
                              for t in n.targets)), -1)
        typed = sorted({
            n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and n.value == _TURN_SCOPE_ROOT and n.lineno != _defn
        })

        # Half two: the PATH must DERIVE from the helper. A mention is not a derivation.
        _WRITES = ("write_text", "write_bytes", "touch", "mkdir", "unlink", "symlink_to")
        _SAFE_ROOTS = {"_swept_root", "_sweep", "tmp_path", "mkdtemp", "TemporaryDirectory"}
        stray = []

        def _path_expr(call):
            """The expression naming the file this call writes, or None if it is not a write."""
            attr = getattr(call.func, "attr", None)
            if attr in _WRITES:
                return call.func.value
            name = attr or getattr(call.func, "id", None)
            if name == "open" and len(call.args) >= 2:
                mode = call.args[1]
                if isinstance(mode, ast.Constant) and set(str(mode.value)) & set("wax+"):
                    return call.args[0]
            if name in ("copyfile", "copy", "copy2", "copytree") and len(call.args) >= 2:
                return call.args[1]
            if name in ("rmtree", "remove") and call.args:
                return call.args[0]
            return None

        scopes = [tree] + [n for n in ast.walk(tree)
                           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))]
        for scope in scopes:
            # Taint to a fixed point, within this scope: a name assigned from anything that reaches
            # a safe root is itself safe. **An assignment, never a mention** - `_ = _swept_root`
            # binds `_`, not the path, and that is the whole of the dead-token bypass.
            derived = set(_SAFE_ROOTS)
            for _ in range(12):
                grew = False
                for n in ast.walk(scope):
                    if not isinstance(n, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                        continue
                    value = getattr(n, "value", None)
                    if value is None or not any(
                            (isinstance(x, ast.Name) and x.id in derived)
                            or (isinstance(x, ast.Attribute) and x.attr in derived)
                            for x in ast.walk(value)):
                        continue
                    targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                    for t in targets:
                        for el in ([t] if isinstance(t, ast.Name) else getattr(t, "elts", [])):
                            if isinstance(el, ast.Name) and el.id not in derived:
                                derived.add(el.id)
                                grew = True
                if not grew:
                    break
            for call in ast.walk(scope):
                if not isinstance(call, ast.Call):
                    continue
                path = _path_expr(call)
                if path is None:
                    continue
                if any((isinstance(x, ast.Name) and x.id in derived)
                       or (isinstance(x, ast.Attribute) and x.attr in derived)
                       for x in ast.walk(path)):
                    continue
                stray.append(f"{getattr(scope, 'name', '<module>')}:{call.lineno}")
        return typed, sorted(set(stray))

    def test_ONLY_THE_FIRST_STATEMENT_OF_A_TRY_BODY_IS_UNCONDITIONAL(self):
        """🔴 **W4 — SPECIFIED IN ROUND 16, SHIPPED IN ROUND 20 AS ONE TOKEN, AND UNTESTED UNTIL
        NOW.** The rule is `s.body[:1]`: a `try` is entered unconditionally, so its FIRST statement
        runs — and its second runs only if the first did not raise, which is the entire reason a
        `try` is there. Accepting the whole body means an arm behind a statement that can fail is
        treated as an arm that always happens.

        Three consecutive rounds shipped a claim about this with no artifact. The token was added
        with *"driven at 9/9 shapes"* recorded in a verdict and **reverting it left 137 passed** —
        so the suite could not tell the two rules apart, and the shape the rule exists to reject was
        never in it. A verifier eventually wrote this test rather than reporting the gap again.

        The vehicle has to be an arm that is **second** in a `try` body: first-statement probes are
        accepted by both rules and prove nothing. Every other statement here is deliberately
        ordinary — a preceding `await` is exactly what a real turn does before it arms.
        """
        key, entry = self._narrows_unarmed("w4_probe", "\n".join([
            "from app.client.knowledge_client import KnowledgeClient",
            "from app.services.instrument import arm_turn_surface",
            "async def w4_probe(c):",
            "    try:",
            "        prefs = await c.get_preferences()",
            "        arm_turn_surface()",
            "        return await c.get_tool_definitions()",
            "    except Exception:",
            "        return []"]) + "\n")
        assert key, "the probe was not discovered, so this asserts nothing"
        arms, _raw, _narrowings, _aliases, conditional = entry
        assert arms, "the arm was not seen at all, so this probe measures the wrong thing"
        assert conditional == arms, (
            f"an arm as the SECOND statement of a `try:` body was counted as UNCONDITIONAL: "
            f"{entry}. It runs only if `prefs = await c.get_preferences()` did not raise — and the "
            f"handler that catches that raise is the path where the turn narrows into a sink "
            f"nothing armed."
        )

        # ...and the control, so this is not a blanket refusal of arms inside `try`: the FIRST
        # statement is still unconditional, which is what route 18/W2 established and what a
        # `s.body[:0]` overshoot would break without any other test noticing.
        key2, entry2 = self._narrows_unarmed("w4_first_probe", "\n".join([
            "from app.client.knowledge_client import KnowledgeClient",
            "from app.services.instrument import arm_turn_surface",
            "async def w4_first_probe(c):",
            "    try:",
            "        arm_turn_surface()",
            "        return await c.get_tool_definitions()",
            "    except Exception:",
            "        return []"]) + "\n")
        assert key2 and entry2[0] and not entry2[4], (
            f"the control regressed: an arm as the FIRST statement of a `try:` body must stay "
            f"unconditional, and reporting it CONDITIONAL is a false positive on correct code "
            f"({entry2})"
        )

        # 🔴 **AND THE SAME RULE AT THE `with` DOOR, WHICH THE FIRST REPAIR LEFT OUT.** `[:1]` went
        # in for `Try` with a nine-shape drive behind it and its twin eight lines above kept the
        # whole body — the twelfth pair in this run repaired at one end, inside the repair for W4.
        # A verifier measured both shapes UNCONDITIONAL on the real sweep.
        for label, lines in {
            "an arm 2nd in a `with` body": [
                "import contextlib",
                "from app.client.knowledge_client import KnowledgeClient",
                "from app.services.instrument import arm_turn_surface",
                "async def w4_with_probe(c):",
                "    async with contextlib.AsyncExitStack():",
                "        prefs = await c.get_preferences()",
                "        arm_turn_surface()",
                "        return await c.get_tool_definitions()"],
            "an arm 2nd in a `with` nested 1st in a swallowing `try`": [
                "import contextlib",
                "from app.client.knowledge_client import KnowledgeClient",
                "from app.services.instrument import arm_turn_surface",
                "async def w4_nested_probe(c):",
                "    try:",
                "        async with contextlib.AsyncExitStack():",
                "            prefs = await c.get_preferences()",
                "            arm_turn_surface()",
                "            return await c.get_tool_definitions()",
                "    except Exception:",
                "        return []"],
        }.items():
            name = lines[3].split("def ")[1].split("(")[0]
            key3, entry3 = self._narrows_unarmed(name, "\n".join(lines) + "\n")
            assert key3, f"{label}: the probe was not discovered, so this asserts nothing"
            arms3, _r, _n, _a, cond3 = entry3
            assert arms3 and cond3 == arms3, (
                f"{label} was counted as UNCONDITIONAL: {entry3}. It runs only if the preceding "
                f"`await` did not raise — and in the nested case the handler swallows that raise, "
                f"so the turn narrows into a sink nothing armed while the line numbers say the arm "
                f"came first. That is W4's own defect, at the door its repair did not reach."
            )

        # ...and the `with` control, so `[:1]` here is not a blanket refusal either: route 18's one
        # live beneficiary is an arm that IS the first statement of an `async with`.
        key4, entry4 = self._narrows_unarmed("w4_with_first_probe", "\n".join([
            "import contextlib",
            "from app.client.knowledge_client import KnowledgeClient",
            "from app.services.instrument import arm_turn_surface",
            "async def w4_with_first_probe(c):",
            "    async with contextlib.AsyncExitStack():",
            "        arm_turn_surface()",
            "        return await c.get_tool_definitions()"]) + "\n")
        assert key4 and entry4[0] and not entry4[4], (
            f"the `with` control regressed: an arm as the FIRST statement of an `async with` must "
            f"stay unconditional — `voice_stream_service.py` is one refactor from that shape, and a "
            f"gate that reds on correct code is one that gets deleted ({entry4})"
        )

    def test_the_TERMINAL_WRITE_GATE_sees_a_writer_in_ANY_module(self):
        """🔴 **T8 — and it was the module list.** Ten in-module defeats red (alias, `*args`,
        `**kwargs`, a returning helper, `executemany`, a rename, SQL split across locals, a lost
        writer, a gained writer) — and a writer in any OTHER module binding `None` was `1 passed`,
        three ways, because `_mods` was a hardcoded two-tuple. The arm-order gate sixty lines away
        derives its file set with `rglob`; this one wrote it down.

        **`app/agentruntime/` is where CP-2's runtime lands**, so a terminal write there would have
        been invisible to this gate by construction — not by oversight, by design."""
        import pathlib

        base = _swept_root()
        probe = "\n".join([
            "async def probe_write(conn, msg_id):",
            "    await conn.execute(",
            '        "UPDATE chat_messages SET withheld_tools = $1 WHERE message_id = $2",',
            "        None, msg_id,",
            "    )"]) + "\n"
        for where in ("agentruntime", "routers", "services"):
            path = base / where / "_lwprobe_writer.py"
            path.write_text(probe, encoding="utf-8")
            try:
                inst = TestU2ACatalogueOutageIsRegistered()
                # 🔴 **THE ORACLE WAS `match="withheld_tools"`, WHICH MATCHES THREE OF THE GATE'S
                # FOUR ASSERTIONS** — the named-writer subset check, the `>= 4` anchor check and the
                # offender list all carry that word. So this test could not tell *"the probe was
                # caught"* from *"the gate broke in some unrelated way and reddened first"*, and an
                # anchor that stopped matching would have kept it green while proving nothing. It
                # binds to the PROBE'S OWN MODULE PATH now, which appears in exactly one message.
                with pytest.raises(AssertionError, match=_probe_offender(where, "_lwprobe_writer")):
                    inst.test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE__not_a_literal_None()
            finally:
                path.unlink(missing_ok=True)

    def test_TOOL_READ_ONCE__the_pair_the_source_fix_left_behind(self):
        """🔴 The same function whose `source` read-twice this effort fixed read `tool` twice as
        well, and the fix went to the read a sweep had named rather than to the pair — the flaw six
        rounds have recorded, committed inside the commit that closed the other half. A verifier
        drove it: the row classified `breaker` from `read_file` and stamped
        `declaration: delete_everything`."""
        from app.services import instrument

        class TwoFaced(dict):
            def __init__(self, real):
                super().__init__(real)
                self._n = 0

            def get(self, key, default=None):
                if key == "tool":
                    self._n += 1
                    return "read_file" if self._n == 1 else "delete_everything"
                return super().get(key, default)

        out = instrument.ensure_tool_call_instrumented(TwoFaced({"tool": "read_file"}))
        assert out["declaration"] == "read_file", (
            f"the row was classified from one value and stamped with another: {out}"
        )

    def test_the_TERMINAL_GATE_sees_SQL_HOISTED_TO_A_MODULE_CONSTANT(self):
        """🔴 **T9e — the headline defeat, and it is the most ordinary refactor there is.**
        Hoisting the statement out of the function (`_SQL = "UPDATE chat_messages SET withheld_tools
        = $1 …"`) made the gate blind, because `sql_locals` was computed from the FUNCTION's
        bindings only. Also covered here: a write at **module scope**, which has no enclosing
        function at all and was skipped for that reason."""
        import pathlib as _pl

        base = _swept_root()
        probes = {
            "module constant": [
                '_SQL = "UPDATE chat_messages SET withheld_tools = $1 WHERE message_id = $2"',
                "async def probe_write(conn, msg_id):",
                "    await conn.execute(_SQL, None, msg_id)"],
            "bare-name executor": [
                "async def probe_write2(execute, msg_id):",
                "    await execute(",
                '        "UPDATE chat_messages SET withheld_tools = $1 WHERE message_id = $2",',
                "        None, msg_id,",
                "    )"],
        }
        for label, lines in probes.items():
            path = base / "services" / "_lwprobe_hoisted.py"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            try:
                inst = TestU2ACatalogueOutageIsRegistered()
                # Bound to this probe's own module — `match="withheld_tools"` was satisfied by three
                # of the gate's four assertions and therefore by any of them going red.
                with pytest.raises(AssertionError,
                                   match=_probe_offender("services", "_lwprobe_hoisted")):
                    inst.test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE__not_a_literal_None()
            finally:
                path.unlink(missing_ok=True)

    def test_the_TERMINAL_GATE_sees_THE_COLUMN_NAME_HOISTED_TO_A_CONSTANT(self):
        """🔴 **T11d — SIX ROUNDS, AND THE SUBJECT IS THE LIVE WRITE.** Every production statement
        that persists this column is an f-string, and the *only* thing keeping any of them visible
        to the gate was the column name appearing as a **literal** inside it. Hoisting a column name
        to a constant is the most ordinary refactor there is — T9e is the same refactor applied to
        the SQL one level out, and it made the whole gate blind — so this is not a synthetic hazard:
        it is the one the live spelling is one edit away from.

        Four vehicles, each an ordinary way to write the same statement. Two of them additionally
        cover the bare-name `segment_merge_sql(...)`, which had no `.attr` at all and so read as
        *"not the column"* rather than as a call the gate could not resolve.
        """
        base = _swept_root() / "services"
        probes = {
            "interpolated column name": [
                '_COL = "withheld_tools"',
                "async def probe_write(conn, msg_id):",
                '    await conn.execute(',
                '        f"UPDATE chat_messages SET {_COL} = $1 WHERE message_id = $2",',
                "        None, msg_id,",
                "    )"],
            "column name through TWO bindings": [
                '_COL_A = "withheld_tools"',
                "_COL_B = _COL_A",
                "async def probe_write(conn, msg_id):",
                '    await conn.execute(',
                '        f"UPDATE chat_messages SET {_COL_B} = $1 WHERE message_id = $2",',
                "        None, msg_id,",
                "    )"],
            # 🔴 **A4 — THE TABLE HOIST, WHICH THE FIRST REPAIR WAS BLIND TO.** `ast.walk` is
            # breadth-first, so an alias's spelling always landed AFTER every literal: `withheld_
            # tools =` was never contiguous and the fix survived only because `UPDATE chat_messages`
            # was still a literal. This is T9e's refactor one level out — cited as the precedent in
            # the same comment that left its twin open.
            "the TABLE name hoisted too": [
                '_COL = "withheld_tools"',
                '_TBL = "chat_messages"',
                "async def probe_write(conn, msg_id):",
                "    await conn.execute(",
                '        f"UPDATE {_TBL} SET {_COL} = $1 WHERE message_id = $2",',
                "        None, msg_id,",
                "    )"],
            "segment_merge_sql on a hoisted name": [
                "from app.services import instrument",
                '_COL = "withheld_tools"',
                "async def probe_write(conn, msg_id):",
                "    await conn.execute(",
                '        f"INSERT INTO chat_messages (message_id) VALUES ($2) ON CONFLICT DO '
                'UPDATE SET {instrument.segment_merge_sql(_COL)}",',
                "        None, msg_id,",
                "    )"],
            "bare-name segment_merge_sql": [
                "from app.services.instrument import segment_merge_sql",
                "async def probe_write(conn, msg_id):",
                "    await conn.execute(",
                '        f"INSERT INTO chat_messages (message_id) VALUES ($2) ON CONFLICT DO '
                'UPDATE SET {segment_merge_sql(\'withheld_tools\')}",',
                "        None, msg_id,",
                "    )"],
        }
        for label, lines in probes.items():
            path = base / "_lwprobe_hoistcol.py"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            try:
                inst = TestU2ACatalogueOutageIsRegistered()
                with pytest.raises(AssertionError,
                                   match=_probe_offender("services", "_lwprobe_hoistcol")):
                    inst.test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE__not_a_literal_None()
            finally:
                path.unlink(missing_ok=True)

    def test_the_TERMINAL_GATE_DOES_NOT_RED_ON_CORRECT_CODE_IN_ANOTHER_MODULE(self):
        """🔴 **A3 — THE FIRST T11d REPAIR RED ON CORRECT CODE, TWICE, CROSS-MODULE.** The prompt
        asked whether the over-approximation could do this, quoting the standard the gate is held
        to: *"a gate that reds on correct code is one that gets deleted the first time it is
        inconvenient."* It could, and a verifier executed both vehicles.

        One global alias set for all of `app/`, with no import graph, means: module A performs the
        hoist T11d exists to survive, and every OTHER module that happens to reuse the identifier is
        convicted. The comment claimed the over-approximation *"costs a few extra binds to check"*.
        **It costs the identifier namespace of the whole tree**, and `_COL`, `col`, `_SQL`, `sql`
        and `q` are ordinary names.

        A constant crosses a module boundary exactly one way — an `import` — so the alias maps are
        scoped to the binding module plus the modules that import from it. Both vehicles below are
        **correct code** and must leave the gate green.
        """
        base = _swept_root() / "services"
        pairs = {
            "an unrelated `_COL` parameter in another module": {
                "_lwprobe_fp_a.py": ['_COL = "withheld_tools"'],
                "_lwprobe_fp_b.py": [
                    "async def rename_content(conn, mid, _COL):",
                    '    await conn.execute(',
                    '        f"UPDATE chat_messages SET content = {_COL} WHERE message_id = $1",',
                    "        mid,",
                    "    )"],
            },
            "a generic executor helper taking `_SQL`": {
                "_lwprobe_fp_c.py": [
                    '_SQL = "UPDATE chat_messages SET withheld_tools = $1 WHERE message_id = $2"'],
                "_lwprobe_fp_d.py": [
                    "async def run_any(conn, _SQL, arg):",
                    "    await conn.execute(_SQL, arg)"],
            },
        }
        for label, files in pairs.items():
            written = []
            try:
                for name, lines in files.items():
                    p = base / name
                    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
                    written.append(p)
                inst = TestU2ACatalogueOutageIsRegistered()
                # No `pytest.raises`: correct code must simply pass.
                inst.test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE__not_a_literal_None()
            except AssertionError as exc:
                raise AssertionError(
                    f"{label}: the gate reddened on CORRECT code — {exc}. An alias that crosses a "
                    f"module boundary without an import is not an alias, it is a name collision, "
                    f"and convicting on one is how this gate gets deleted."
                ) from exc
            finally:
                for p in written:
                    p.unlink(missing_ok=True)

    def test_the_TERMINAL_GATE_FAILS_CLOSED_on_a_file_it_cannot_parse(self):
        """`except SyntaxError: continue` meant an unparseable module left the sweep with no record.
        A gate that skips what it cannot read is green over exactly the files most likely to be
        wrong."""
        import pathlib as _pl

        path = _swept_root() / "services" / "_lwprobe_broken.py"
        path.write_text("def broken(:\n", encoding="utf-8")
        try:
            inst = TestU2ACatalogueOutageIsRegistered()
            with pytest.raises(AssertionError, match="could not be parsed"):
                inst.test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE__not_a_literal_None()
        finally:
            path.unlink(missing_ok=True)

    def test_a_NARROWING_IN_THE_DELEGATES_ARGUMENTS_precedes_it(self):
        """🔴 **ROUTE 24 — I compared line numbers and Python evaluates arguments first.**
        `return stream_response(await c.get_tool_definitions())` puts the narrowing INSIDE the
        delegating call, on the same line, and the fetch runs before the delegate is entered. It is
        route 23 written on one line, exempted by the fix for route 23."""
        key, entry = self._narrows_unarmed("arg_probe", "\n".join([
            "from app.client.knowledge_client import KnowledgeClient",
            "from app.services.stream_service import stream_response",
            "async def arg_probe(c):",
            "    return stream_response(await c.get_tool_definitions())"]) + "\n")
        assert key and not entry[0], (
            "a narrowing nested in the delegating call's own arguments was treated as happening "
            "after it — the exemption compared source position against execution order"
        )

    def test_an_ARM_IN_A_TRY_WHOSE_HANDLER_NARROWS_is_not_COVERED(self):
        """🔴 **The `Try` widening overshot, and the fix for route 18 introduced it.** An arm
        as the LAST statement of a `try` body with the narrowing in the `except` handler: the handler
        runs precisely when the body did not finish, so that is a turn narrowing into nothing — and
        the line numbers say the arm came first. A `try` body is entered unconditionally, which is
        why it counts at all; it only covers what is IN it."""
        key, entry = self._narrows_unarmed("handler_probe", "\n".join([
            "from app.client.knowledge_client import KnowledgeClient",
            "from app.services.instrument import arm_turn_surface",
            "async def handler_probe(c):",
            "    try:",
            "        arm_turn_surface()",
            "    except Exception:",
            "        return await c.get_tool_definitions()",
            "    return []"]) + "\n")
        assert key, "the probe was not discovered, so this asserts nothing"
        arms, _raw, _narrowings, _aliases, conditional = entry
        assert conditional or not arms, (
            f"an arm in a `try` body was treated as covering a narrowing in that try's own handler, "
            f"which runs only when the body did not complete: {entry}"
        )

    def test_the_TERMINAL_GATE_sees_EVERY_SPELLING_OF_THE_SAME_WRITE(self):
        """🔴 **Five of these were CAUGHT before I qualified the SQL match, and my
        qualification blinded them.** A verifier attributed each against a control: concatenation,
        `.format`, `%`, `" ".join` and **two spaces**. Damping a false positive by narrowing a
        matcher is how a gate loses the cases it was built for, so the SQL is assembled from every
        string in the expression and whitespace-normalised instead."""
        import pathlib as _pl

        base = _swept_root() / 'services'
        spellings = {
            'two spaces': '        "UPDATE  chat_messages SET withheld_tools  =  $1 WHERE id = $2",',
            'concatenation': '        "UPDATE chat_messages SET " + "withheld_tools = $1 WHERE id = $2",',
            'format': '        "UPDATE chat_messages SET {} = $1 WHERE id = $2".format("withheld_tools"),',
            'join': '        " ".join(["UPDATE chat_messages SET", "withheld_tools = $1 WHERE id = $2"]),',
        }
        for label, sql in spellings.items():
            path = base / '_lwprobe_spelling.py'
            path.write_text('async def probe_write(conn, mid):' + chr(10)
                            + '    await conn.execute(' + chr(10) + sql + chr(10)
                            + '        None, mid,' + chr(10) + '    )' + chr(10), encoding='utf-8')
            try:
                inst = TestU2ACatalogueOutageIsRegistered()
                # Bound to this probe's own module. These four spellings are the ones a matcher
                # narrowing already blinded once; an oracle that any red satisfies could not have
                # told anyone.
                with pytest.raises(AssertionError,
                                   match=_probe_offender('services', '_lwprobe_spelling')):
                    inst.test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE__not_a_literal_None()
            finally:
                path.unlink(missing_ok=True)

    def test_THE_RECORDER_DOOR_IS_BOUNDED__and_a_CARRIED_recorder_is_the_new_failure_mode(self):
        """🔴 **The parameter fixed a false NEGATIVE and opened a false POSITIVE I never
        asserted.** A recorder that outlives its turn reports THAT turn's outage for THIS one - 228
        sequences, measured exhaustively by a verifier - and the failure is U-2's founding defect
        verbatim: telling a healthy turn its tools are unreachable. My test drove the *fresh*
        recorder case; the **carried** case, which this parameter makes possible for the first time,
        was the one it never drove.

        And the door carried no type bound at all while every other door in the module does: five
        argument types crashed it from inside prompt assembly, the sixth occurrence of bounding a
        container without bounding what it holds."""
        import contextvars

        from app.services import instrument

        for bad in (42, 'x', [], {}, object()):
            with pytest.raises(TypeError, match='recorder'):
                instrument.catalogue_outage_registered(recorder=bad)

        # The carried case, driven rather than reasoned about: turn A's recorder must not answer
        # for turn B. It is the caller's contract - the one wired caller builds and reads in the
        # same function - and this asserts the shape that would violate it.
        def _carried():
            instrument.arm_turn_surface()
            instrument.record_catalogue_unavailable(stage='s', reason='r')
            rec_a = instrument.AdvertisedToolsRecorder()
            rec_a.absorb(instrument.surface_withheld.get())
            instrument.arm_turn_surface()                    # turn B
            return instrument.catalogue_outage_registered(), rec_a.catalogue_outage()

        no_recorder, carried_still_holds = contextvars.copy_context().run(_carried)
        assert no_recorder is False, 'turn B saw turn A outage with no recorder passed'
        assert carried_still_holds is True, (
            'turn A recorder forgot its own row, so the carried-recorder hazard is not what this '
            'test claims and the assertion above proves nothing'
        )

