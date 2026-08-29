#!/usr/bin/env python
"""The loop's GATE — evidence checks that fail, instead of a goal that can be rationalised around.

🔴 WHY A SCRIPT AND NOT A LONGER GOAL. The deep-dive loop ran for 31 cycles under a written goal,
and the goal did not hold. Measured, in this repo's own history:

  * cycles 22-26 — four tools recorded terminally BLOCKED on a premise ("a budget-dropped tool is
    unreachable") that had never been checked. All four were later withdrawn and proved PROVEN.
  * 2026-08-13 — a "sweep" was proposed and built that talks straight to MCP endpoints, i.e.
    BELOW every layer where 14 of the ledger's 23 defects live. It marked composition_list_outline
    clean; the real turn created three chapters in the author's book.

Both were rationalisations of prose. Prose is negotiable; an exit code is not. So the bars live
here, as checks over evidence that must exist ON DISK before a conclusion may be recorded.

**What a script can check** — all of this is deterministic and identical for all 285 tools:
store snapshot taken before AND after, K>=3 repeats, the store diff on a read-intent scenario,
a falsifier proven RED on the ORIGINAL defect, the owning suite's exit code, the deployed md5,
and that the conclusion is one of exactly two words.

**What it cannot check, stated so its green is never mistaken for proof**: whether the root cause
is right, and whether the invariant named is the real one. Those need judgement. What the gate
CAN do is refuse to let judgement be skipped — the invariant must be written down and proved
against every past incident of its class, which is the check that caught R1 being incomplete on
the day it was written.

The per-tool differences are not in the process. They are two pieces of DATA — the prompt and the
owning store — and the strongest assertion in the loop ("a read-intent turn changed nothing")
needs no per-tool knowledge at all.

Usage:
    python scripts/toolloop/gate.py check   <batch.json>
    python scripts/toolloop/gate.py conclude <batch.json> --tool NAME --state proven|blocked
"""
from __future__ import annotations

import argparse
import functools

import selection_rate
import json
import hashlib
import pathlib
import re
import sys


def _sha(text) -> str:
    """Must match fe_runner._sha exactly — the two sides of the same commitment."""
    if not text:
        return ""
    return hashlib.sha256(str(text).strip().encode("utf-8")).hexdigest()[:16]

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"

MIN_REPEATS = 3
TERMINAL = ("proven", "blocked")

#: The two evidence classes. `renamed` is a redirect row and is neither.
GATE_BACKED = "gate-backed"
PROSE_NOTE = "prose-note (pre-gate)"


@functools.lru_cache(maxsize=512)
def _tools_in_batch(path: str) -> frozenset:
    """Which tools an evidence file actually carries an entry for. Cached — recompute reads ~130."""
    try:
        d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except Exception:
        return frozenset()
    if not isinstance(d, dict):
        return frozenset()
    return frozenset(x["tool"] for x in (d.get("tools") or [])
                     if isinstance(x, dict) and x.get("tool"))


def is_gate_backed(tool: str, row: dict) -> bool:
    """🔴 THE LEDGER'S OWN DEFINITION, APPLIED — not the label the row wrote about itself.

    The definition has always been written down: "a conclusion is 'gate-backed' when it CITES an
    evidence file that exists and that gate.py can re-check". Nothing checked a row against it,
    and 43 of the 173 rows carrying the label cited NO FILE AT ALL. The headline "173 of 198
    gate-backed" was overstated by 42; the re-checkable figure is 131.

    CITATION IS THE POINT, and the tempting shortcut is what makes that worth saying. All 43 of
    those tools DO have an entry in some file on disk — two to five files each. Picking one and
    calling it the citation would invent the very thing the label is supposed to guarantee: that
    a specific, named measurement can be re-run. A row that does not cite one is not gate-backed,
    however much evidence exists near it.
    """
    ev = row.get("evidence_file")
    if not ev:
        return False
    p = ROOT / ev
    return p.exists() and tool in _tools_in_batch(p.as_posix())


#: A defect row's `state`, CLOSED. The prose stays in `status`; only this is ever counted.
#: `withdrawn` is a defect that turned out not to be one; `superseded` folded into another row
#: and must name it. See the comment in `recompute_progress` for what the open set cost.
DEFECT_STATES = ("open", "fixed", "proven", "withdrawn", "superseded")


class Gate:
    def __init__(self, batch: dict, path: pathlib.Path):
        self.b = batch
        self.path = path
        self.fail: list[str] = []
        self.ok: list[str] = []

    def _check(self, cond: bool, label: str, why: str) -> bool:
        (self.ok if cond else self.fail).append(label if cond else f"{label} — {why}")
        return cond

    # ── the bars ──────────────────────────────────────────────────────────────────────────
    def live(self, t: dict) -> None:
        runs = t.get("runs") or []
        self._check(
            len(runs) >= MIN_REPEATS, f"[{t['tool']}] LIVE repeats",
            f"{len(runs)} run(s); the consumer is stochastic so one sample proves nothing "
            f"(need >= {MIN_REPEATS})")
        self._check(
            all(r.get("via") == "fe_runner" for r in runs), f"[{t['tool']}] LIVE path",
            "a run not driven through the real chat path does not count — the MCP endpoint sits "
            "below every layer the defects live in")
        errs = [r for r in runs if r.get("error")]
        # 🔴 A PROVISION FAILURE IS NOT A TRANSPORT FAILURE, and calling it one sends the reader at
        # the platform. Measured 2026-08-23: memory_forget errored 5 of 5 and this bar reported "a
        # transport failure is not a model result". Every run's own error read
        # "PROVISION MCPToolError: ... the assistant has reached its memory_remember limit (10) for
        # this chat session" — the SEED could not build the fixture. The verdict is the same (this
        # is not evidence about the tool) and the DIAGNOSIS is opposite: one is the provider, the
        # other is a fixture whose seed hits a per-session cap.
        #
        # The loop has paid for this exact confusion before, one level up: an `err` COUNT of 5 was
        # recorded as "5 of 5 lost to transport errors" in three commits while every run said
        # SEED ASSERTION FAILED. Reading the error STRING rather than its presence is the fix, and
        # it costs one substring.
        _prov = [r for r in errs if str(r.get("error") or "").lstrip().upper().startswith("PROVISION")]
        _why = (f"{len(errs)} run(s) errored; a transport failure is not a model result")
        if _prov:
            _why = (f"{len(errs)} run(s) errored and {len(_prov)} of them is a PROVISION failure — "
                    f"the SEED could not build the fixture, so this is not the platform: "
                    f"{str(_prov[0].get('error'))[:150]}")
        # D-FAILED-SNAPSHOT-COUNTED-AS-A-STORE-CHANGE, the diagnosis half. A run whose STORE
        # SNAPSHOT could not be taken is unusable for the same reason and points somewhere
        # ELSE: not the provider, not the fixture, but Postgres refusing the probe (measured
        # 2026-08-22 at 96 of 100 connections). Same verdict, third diagnosis.
        _snap = [r for r in errs
                 if str(r.get("error") or "").lstrip().upper().startswith("SNAPSHOT")]
        if _snap:
            _why = (f"{len(errs)} run(s) errored and {len(_snap)} of them is a SNAPSHOT failure "
                    f"— the store could not be READ, so this run measures nothing about the "
                    f"tool and nothing about the fixture either: "
                    f"{str(_snap[0].get('error'))[:150]}")
        self._check(not errs, f"[{t['tool']}] LIVE clean", _why)
        # 🔴 THE GATE COULD NOT TELL "THE TOOL RAN" FROM "THE TURN RAN".
        #
        # Until 2026-08-14 the LIVE bars were: enough repeats, the real path, no transport error.
        # Every one of those is a property of the TURN. None asks whether the tool under test was
        # ever invoked, so a batch in which the model used a different tool entirely passed LIVE
        # outright — and the batch that exposed it is this file's own predecessor:
        # `settings_provider_inventory` called 0/3 (the model answered from settings_list_models)
        # and `composition_conformance_run` called 0/3, both scoring three green LIVE checks.
        #
        # That is the loop's own headline defect pointed at its own instrument: a check that
        # reports success without looking at the thing it claims to verify. It matters more here
        # than anywhere else, because this gate is the authority a conclusion rests on.
        #
        # Deliberately >= 1 rather than all K: the consumer is stochastic and a 1-of-3 call is a
        # real finding worth concluding on, so the COUNT is put in the message either way. What
        # cannot stand is 0 — a tool never invoked has not been exercised, whatever the turn did.
        # A gated proposal (a confirm card) counts: the tool ran and its gate held.
        called = int(t.get("called_count") or 0)
        # 🔴 "PROVEN" OVER A 1-IN-50 TOOL AND OVER A 50-IN-50 TOOL ARE NOT THE SAME SENTENCE.
        # D-A-LOW-RATE-TOOL-CANNOT-BE-PROVEN-WITHOUT-SAMPLING-FOR-A-VERDICT: for a tool the model
        # picks reliably this bar is a fair test; for one it picks 15% of the time a fresh K=5
        # batch is close to a coin flip, and whichever way it lands the batch is concludable in
        # one direction and not the other.
        #
        # Measured across every batch on disk 2026-08-27: 19 of 65 measured tools sit below a
        # 0.5 selection rate — translation_job_control at 1 call in 50 — and EVERY ONE of the
        # non-zero ones is already `proven`.
        #
        # The bar is NOT changed. What counts as reachable-at-a-rate is DQ-T51 and belongs to the
        # owner; changing it here would redefine `proven` for every stochastic tool in the
        # denominator by side effect. The rate is STATED so a reader knows which sentence they
        # are being handed.
        # ── DQ-T51, answered by the owner 2026-08-28 ────────────────────────────────────────
        # "STATE A RATE BAR. A tool chosen in >= N of M runs counts as reachable; below that the
        # row is a SELECTION defect, not an unproven tool." The owner declined letting a direct
        # probe satisfy LIVE — the real chat path stays the bar.
        #
        # The bar is DERIVED (selection_rate._reachable_bar): p = 1-(1-0.95)**(1/5) = 0.4507, the
        # rate at which a K=5 batch has 95% chance of containing a call. At or above it, `called
        # 0/5` is evidence about the TOOL. Below it the zero is mostly a lost draw, so calling
        # the tool unproven measures the draw and not the tool.
        #
        # WHAT CHANGED HERE: below the bar this stops being a LIVE failure and becomes a NAMED
        # SELECTION finding. It is NOT a pass — the verdict still says the tool was not called
        # and still refuses to conclude `proven` — but it no longer reads as "this tool is
        # broken" when what is broken is that the model rarely picks it.
        _rate = selection_rate.rate_for(t["tool"])
        _below_bar = bool(_rate) and _rate["rate"] < selection_rate.LOTTERY_BELOW
        if called >= 1 or not _below_bar:
            _rate_note = ""
            if _below_bar:
                _rate_note = (f" [selection rate {_rate['rate']:.2f} across the corpus — "
                              f"{_rate['calls']}/{_rate['runs']}; this verdict rests on a draw "
                              "the model loses more often than it wins]")
            self._check(
                called >= 1, f"[{t['tool']}] LIVE called ({called}/{len(runs)}){_rate_note}",
                "the tool under test was never invoked on any run — the model answered by "
                "another route, so nothing here is evidence about THIS tool")
        else:
            # 🔴 NOT A PASS AND NOT A LIVE FAILURE — a different sentence. `_check` would have to
            # be one or the other, so this is recorded as its own bar, and `conclude` cannot read
            # it as green: a SELECTION verdict never yields `proven`.
            self._check(
                False,
                f"[{t['tool']}] SELECTION below the reachability bar "
                f"({_rate['calls']}/{_rate['runs']} = {_rate['rate']:.2f} < "
                f"{selection_rate.LOTTERY_BELOW:.2f})",
                "the model picks this tool too rarely for a K=5 batch to be a fair test — at "
                "this rate a zero is a lost draw, not a finding about the tool. This is a "
                "SELECTION defect (why is it not chosen?), NOT an unproven tool, and re-running "
                "until a call appears would be sampling for a verdict (DQ-T51).")

    def data(self, t: dict) -> None:
        """The store bar, checked on EVERY run rather than on one aggregate pair.

        The batch used to carry a single before/after for the whole tool. That shape cannot
        express the thing the loop most needs to know about a stochastic consumer: WHICH runs
        wrote. With one book per repeat, each run owns its own snapshot pair, so "2 of 5 turns
        wrote" is checkable — and a single run that wrote fails the bar even when the other four
        were clean. An aggregate pair would have averaged that away, and averaging away the one
        run that damaged the store is exactly how this defect survived two releases.
        """
        runs = [r for r in (t.get("runs") or []) if isinstance(r, dict)]
        # Back-compat: a hand-written batch may still carry one top-level store pair.
        legacy = t.get("store") or {}
        pairs = [(r.get("store") or {}) for r in runs] or ([legacy] if legacy else [])
        with_both = [p for p in pairs if p.get("before") is not None and p.get("after") is not None]
        self._check(
            bool(pairs) and len(with_both) == len(pairs),
            f"[{t['tool']}] DATA snapshots",
            f"{len(with_both)} of {len(pairs)} run(s) carry the owning store BEFORE and AFTER; "
            "the tool's own response is not evidence of what it wrote")
        # 🔴 "A FALSIFIER EXISTS" AND "THE FALSIFIER HELD" ARE DIFFERENT SENTENCES, and the bar
        # printed the same `ok` for both. D-THE-GBUILD-SCENARIO-CANNOT-TEST-ITS-OWN-FALSIFIER:
        # composition-glossary-build-with-an-ontology predicts POST-CALL behaviour — entities
        # created with no confirm card, op not `start`, an invented run_id — and every one of
        # those needs the tool to have RUN. Across 39 live runs it was never called once, so the
        # prediction has never been evaluated, and the line above still read `ok`.
        #
        # Measured over every batch file on disk 2026-08-27: 241 of 671 tool entries (36%) carry
        # a falsifier on a batch where `called_count` is 0.
        #
        # IT STILL PASSES, deliberately. The bar asks whether a prediction was WRITTEN, and it
        # was; `LIVE called` already fails these batches, and making this one fail too would red
        # every `blocked` conclusion that legitimately rests on a tool that could not be
        # exercised — re-freezing a baseline larger to look stricter. What changes is that the
        # label no longer lets an UNEVALUATED prediction read as a satisfied one.
        _called = int(t.get("called_count") or 0)
        _fals_label = (f"[{t['tool']}] DATA falsifier"
                       + (" (UNEVALUATED — the tool was never called, so nothing could have "
                          "refuted it)" if _called == 0 else ""))
        self._check(bool(t.get("falsifier")), _fals_label,
                    "state explicitly what result would REFUTE this conclusion")
        # 🔴 THE BAR ABOVE ONLY ASKS THAT A FALSIFIER EXISTS. It cannot tell that the run
        # REFUTED it, so a batch whose own stored calls contradict its prediction still passed —
        # twice, measured: b18-gen-control passed 8 of 9 while every composition_generate call
        # carried model_ref="default" (the invention its falsifier names), and c-regwf passed
        # while 4 of 5 runs reported NINE workflows as studio-available when the studio has six.
        # In both cases the only thing between the batch and `proven` was a human reading prose.
        #
        # This does NOT recompute falsifiers — the gate still cannot judge "the model invented an
        # id" from a batch; that needs the claim expressed as data per falsifier. It closes the
        # cheaper hole: a refutation SOMEONE HAS ALREADY WRITTEN DOWN must fail the bar, so
        # `conclude --state proven` refuses and the only way past is to fix the cause and re-run.
        violated = sorted(k for k in t if str(k).startswith("falsifier_violated"))
        self._check(
            not violated, f"[{t['tool']}] DATA falsifier not violated",
            "this entry RECORDS its own refutation (" + ", ".join(violated) + ") — a batch whose "
            "prediction was measured false is not evidence for the conclusion it was written to "
            "test. Fix the cause and re-run; do not conclude `proven` over it")
        amended = t.get("falsifier_amended_after_run")
        self._check(
            not amended, f"[{t['tool']}] DATA falsifier not back-dated",
            "the falsifier was CHANGED after the run it judges. A prediction edited once the "
            "result is known is a description, not a falsifier. Re-run against the new one, or "
            "keep the one that was actually committed to")
        # 🔴 A READ THAT WROTE NOTHING CAN STILL BE WRONG, AND THE GATE COULD NOT SEE IT.
        # Measured 2026-08-14: a fixture with three entities, exactly ONE tagged 'ai-suggested'.
        # Asked "Are there any suggested entries waiting for me to review?", the model answered
        # "3 suggested entries" on 2 of 3 runs — it read the injected story_state block, which
        # holds every entity, and reported the total as the review queue. Store unchanged, no
        # error, DATA read-is-read green: a confidently false answer that passed every bar.
        #
        # This is the 2026-08-13 incident in mirror image ("you haven't declared any" over a
        # populated table), and the only thing that made it visible was a seed where the right
        # answer and the lazy answer DIFFER. So the expectation is declared in the scenario and
        # checked here, rather than being prose I grade by eye after seeing the reply.
        # 🔴 AND THE BAR ITSELF WAS VACUOUS FOR MOST OF ITS LIFE. Measured 2026-08-14 across
        # every evidence file and scenario on disk: 45 answer_expect declarations, of which
        # all_of=24, none_of=13, any_of=2 — while this code read ONLY must_contain (2) and
        # must_not_contain (8). An unrecognised key produced an EMPTY requirement list, and an
        # empty list is satisfied by anything, so the check reported PASS. The bar written to
        # catch a confidently false answer was silent on the majority of the tools that declared
        # one, including glossary_curation_list, the incident it was written for.
        #
        # THE INVARIANT: a declared expectation is either READ or the gate REFUSES. Silence over
        # an unknown key is what let the vocabulary drift for twelve batches, so an unknown key is
        # now a hard failure rather than a no-op — the one thing that cannot drift again.
        exp = t.get("answer_expect") or {}
        if exp:
            KNOWN = {"all_of": "must", "must_contain": "must",
                     "none_of": "mustnt", "must_not_contain": "mustnt",
                     "any_of": "any", "why": None}
            unknown = sorted(k for k in exp if k not in KNOWN)
            self._check(
                not unknown, f"[{t['tool']}] DATA answer_expect is READABLE",
                f"unrecognised key(s) {unknown} in answer_expect — the gate cannot check what it "
                f"cannot read, and an unread expectation PASSES silently. Known keys are "
                f"{sorted(k for k in KNOWN if k != 'why')}")
            must, mustnt, any_of = [], [], []
            for k, bucket in KNOWN.items():
                if bucket is None or k not in exp:
                    continue
                vals = [str(x).lower() for x in (exp.get(k) or [])]
                {"must": must, "mustnt": mustnt, "any": any_of}[bucket].extend(vals)
            declared = bool(must or mustnt or any_of)
            bad = []
            for r in runs:
                a = str(r.get("answer") or "").lower()
                if not a:
                    # 🔴 AN EMPTY REPLY USED TO `continue` HERE, WHICH IS THE SAME BLINDNESS ONE
                    # level down: composition_arc_get produced ZERO prose on 3 of 3 runs and this
                    # bar passed over all three. A turn with no text cannot satisfy a declared
                    # all_of, and reporting it as satisfied hides an empty answer from the gate.
                    #
                    # BUT THE CONTROL REFUTES THE OBVIOUS VERSION OF THAT RULE, so it is folded in
                    # here rather than left to be rediscovered. Measured over every run on disk:
                    # 113 of 347 turns had no prose — and 92 of those 113 ended SUSPENDED ON A
                    # CONFIRM CARD, where the card IS the output and prose is legitimately absent.
                    # Failing those would fail correct Tier-A behaviour, and would have wrongly
                    # withdrawn glossary_extract_entities_from_doc. Only the 21 genuinely silent
                    # turns — no card, no approval, no text — are the defect.
                    if declared and not (r.get("left_suspended") or r.get("approvals")):
                        bad.append((r.get("rep"), ["<EMPTY REPLY, no card>"], []))
                    continue
                miss = [m for m in must if m not in a]
                hit = [m for m in mustnt if m in a]
                if any_of and not any(m in a for m in any_of):
                    miss.append(f"<none of {any_of}>")
                if miss or hit:
                    bad.append((r.get("rep"), miss, hit))
            self._check(
                not bad, f"[{t['tool']}] DATA answer is true",
                f"{len(bad)} of {len(runs)} replies failed the declared expectation "
                f"{bad[:3]} — a read that wrote nothing can still be confidently wrong, and "
                "that is the failure this loop has now seen in both directions")
        if with_both and t.get("intent") == "read":
            # 🔴 A DOWNSTREAM QUEUE ROW IS NOT THE TOOL'S OWNING STORE, AND IT WAS FAILING THIS BAR
            # FOR TOOLS THAT CANNOT WRITE IT. `extraction_pending` is the knowledge-extraction
            # OUTBOX: a relay fills it asynchronously from domain events, so a row the FIXTURE's own
            # book/chapter creation caused can land between a turn's before and after snapshots and
            # be attributed to whatever tool was running.
            #
            # MEASURED 2026-08-23 across every evidence file on disk: of 176 runs with ANY store
            # change, 81 — 46% — changed NOTHING BUT extraction_pending, spread over 14+ tools
            # including ones with no path to it at all: settings_model_set_favorite (12),
            # jobs_pause (5), registry_list_workflows (2). This bar exists to catch a READ that
            # wrote (3 outline rows became 6); it was instead reporting the harness's own async
            # bookkeeping.
            #
            # Scoped rather than removed: the queue is EXCLUDED from the read-is-read comparison
            # only. It stays in the snapshot, because for a tool that really does write content the
            # queue row is a genuine downstream effect and worth seeing.
            # 🔴 A GLOBAL COUNT CANNOT BE ATTRIBUTED TO A TURN EITHER. `neo4j.Fact.total` is
            # counted globally ON PURPOSE — store_snapshot's own note says a fact stored with
            # project_id NULL is invisible to the per-project count, so the total exists to catch
            # it. That makes it useful for SEEING a write and useless for BLAMING one: it moved by
            # exactly 2 on run after run, climbing 370 -> 372 -> 374 -> 376 -> 378 -> 380 across
            # DIFFERENT tools in the same batch, including read-only ones.
            #
            # MEASURED 2026-08-23 across every evidence file: of 177 runs with any store change, 82
            # changed only the outbox queue, 7 only this global count and 1 only the two together —
            # 51% of everything this bar sees is unattributable bookkeeping. The per-project neo4j
            # counts stay in scope; only the deliberately-global one is excluded, and only from
            # read-is-read.
            # 🔴 AND AN ACCESS LOG IS WRITTEN *BY* READING, so counting it makes read-is-read
            # fail every read tool that touches an entity — the exact tools it exists to protect.
            # entity_access_log gained rows on all 5 runs of tool_load, a read whose scenario never
            # even called it.
            #
            # MEASURED 2026-08-23 across every evidence file: of 182 runs with any store change, 135
            # — 74% — changed NOTHING BUT these three bookkeeping keys, and only 47 carried a real
            # owning-store change. Those 47 are exactly the tools that should show one:
            # book_chapter_create, glossary_ontology_upsert, plan_propose_spec,
            # composition_outline_node_edit. The bar's signal was buried under three-to-one noise.
            _QUEUES = ("loreweave_knowledge.extraction_pending", "neo4j.Fact.total",
                       "loreweave_knowledge.entity_access_log")

            def _owning(pair):
                b = {k: v for k, v in (pair["before"] or {}).items() if k not in _QUEUES}
                a = {k: v for k, v in (pair["after"] or {}).items() if k not in _QUEUES}
                return b, a

            wrote = [i for i, p in enumerate(with_both)
                     if (lambda ba: ba[0] != ba[1])(_owning(p))]
            self._check(
                not wrote, f"[{t['tool']}] DATA read-is-read",
                f"the owning store CHANGED on {len(wrote)} of {len(with_both)} read-intent "
                f"run(s) (rep {wrote}) — that is a defect whatever the model said "
                "(measured 2026-08-13: 3 outline rows became 6)")

    def code(self, t: dict) -> None:
        for d in t.get("defects") or []:
            # 🔴 A MALFORMED ENTRY MUST REFUSE, NOT CRASH. `defects` is a list of OBJECTS naming a
            # test file and its RED proof. One scenario carried `["DQ-T3"]` — a bare deferred-
            # question reference — and `d.get` raised AttributeError on the str, which aborted the
            # whole run: 41 tools in one batch went un-evaluated because of one entry in one of
            # them. A gate that dies on bad input is strictly worse than one that reports it, and
            # this gate is the authority a conclusion rests on.
            if not isinstance(d, dict):
                self._check(
                    False, f"[{t['tool']}] defects entry is not an object",
                    f"got {type(d).__name__} {str(d)[:40]!r} — a defect must name its test file and "
                    "its RED proof. A deferred question belongs in the ledger's "
                    "`deferred_questions`, not here, because the CODE bar cannot check it")
                continue
            n = d.get("id", "?")
            self._check(bool(d.get("test_file")) and (ROOT / d.get("test_file", "x")).exists(),
                        f"[{t['tool']}] {n} test exists", "no regression test on disk")
            self._check(bool(d.get("red_on_original")),
                        f"[{t['tool']}] {n} RED proof",
                        "the falsifier was never proven RED on the ORIGINAL defect, so it may "
                        "assert nothing")
            self._check(bool(d.get("invariant")), f"[{t['tool']}] {n} invariant named",
                        "FIX THE INVARIANT, NOT THE INSTANCE — if you cannot name it, you have "
                        "not found the bug")
            self._check(bool(d.get("past_incidents_checked")),
                        f"[{t['tool']}] {n} class checked",
                        "an invariant must be proved against EVERY past incident of its class, "
                        "not just the one that surfaced it")
        if t.get("defects"):
            s = t.get("suite") or {}
            self._check(s.get("exit_code") == 0 and s.get("passed", 0) > 0,
                        f"[{t['tool']}] CODE suite", f"owning suite not green: {s or '(not run)'}")
            dep = t.get("deploy") or {}
            self._check(bool(dep.get("verified_by_content")),
                        f"[{t['tool']}] CODE deployed",
                        "deployed image not verified BY CONTENT against source")

    #: Words that mean "I did not do this". A ship_audit is a record of what was EXERCISED, and
    #: an entry that says it is owed is a to-do wearing an audit's clothes.
    # 🔴 THE VOCABULARY WAS TOO NARROW AND I SLIPPED PAST IT THREE TIMES IN ONE RUN — twice by
    # accident and once I caught myself mid-write. "NOT EXERCISED ...", "INAPPLICABLE, NOT
    # EXERCISED ..." and "not run" all say plainly that nothing was done, and none of them matched,
    # so the bar accepted them as evidence. A ship_audit is what was EXERCISED; anything that says
    # otherwise in plain English must fail, whatever wording it chose.
    OWED = ("owed", "not yet", "todo", "tbd", "pending", "n/a", "later", "skip",
            "not exercised", "unexercised", "inapplicable", "not run", "cannot be exercised",
            "could not be exercised", "not measured")

    def ship(self, t: dict) -> None:
        """SHIP is the bar that separates a POC from a product, so it is the easiest to fake.

        🔴 THE FIRST VERSION CHECKED ONLY THAT THE FIELD WAS NON-EMPTY, AND I IMMEDIATELY FILLED
        IT WITH "owed — a book with zero outline nodes" AND GOT A GREEN GATE. Every machine bar
        passed, the batch read as concluded, and not one refusal, tenancy check or empty case had
        actually been run. A presence check cannot tell an audit from a promise to do one; it has
        to read what the entry SAYS.
        """
        audit = t.get("ship_audit")
        self._check(bool(audit), f"[{t['tool']}] SHIP audit",
                    "record the refusal/gate/empty-case sweep, not just the happy path")
        if not isinstance(audit, dict):
            return
        owed = [k for k, v in audit.items()
                if isinstance(v, str) and any(w in v.lower()[:40] for w in self.OWED)]
        self._check(
            not owed, f"[{t['tool']}] SHIP exercised",
            f"{len(owed)} case(s) recorded as not done ({', '.join(sorted(owed))}) — a ship_audit "
            "is what was EXERCISED. Run them, or conclude the tool `blocked` and say why")

    def run(self) -> bool:
        for t in self.b.get("tools", []):
            self.live(t)
            self.data(t)
            self.code(t)
            self.ship(t)
        return not self.fail


def cmd_check(a) -> int:
    path = pathlib.Path(a.batch)
    g = Gate(json.loads(path.read_text(encoding="utf-8")), path)
    passed = g.run()
    for line in g.ok:
        print(f"  ok    {line}")
    for line in g.fail:
        print(f"  FAIL  {line}")
    print(f"\n{len(g.ok)} passed, {len(g.fail)} failed")
    if not passed:
        print("\nThe batch may NOT be concluded. Each line above names the evidence that is "
              "missing, not an opinion about it.")
    return 0 if passed else 1


def cmd_refresh(a) -> int:
    """Re-read the JUDGEMENT fields from the scenario spec into an existing evidence file.

    The measured fields — runs, store snapshots, counts — are never touched: they were written by
    the run and re-running is the only way to change them. Only falsifier / ship_audit / defects
    are refreshed, because those are mine to write and a ten-minute live re-run is not the right
    price for recording a defect I found while reading the results.

    The separation is the point. What the harness measured and what I assert live in different
    files, and this copies strictly one way.
    """
    bp = pathlib.Path(a.batch)
    batch = json.loads(bp.read_text(encoding="utf-8"))
    spec = json.loads(pathlib.Path(a.scenarios).read_text(encoding="utf-8"))
    by_scenario = {s["id"]: s for s in spec["scenarios"]}
    n = 0
    for t in batch.get("tools", []):
        sc = by_scenario.get(t.get("scenario"))
        if not sc:
            continue
        # 🔴 THE FALSIFIER IS THE ONE FIELD REFRESH MAY NOT QUIETLY REWRITE. ship_audit, defects,
        # suite and deploy are RECORDS OF WORK DONE — they can only be written after the work, so
        # back-filling them is the point of this command. A falsifier is the opposite: it is a
        # commitment made BEFORE the result is known, and one written afterwards is just a
        # description of what happened wearing a prediction's clothes. The run stamped its hash;
        # a changed falsifier is recorded as amended and the gate fails on it rather than being
        # silently overwritten here.
        if "falsifier" in sc:
            stamped = t.get("falsifier_sha")
            now = _sha(sc["falsifier"])
            if stamped and now != stamped:
                t["falsifier_amended_after_run"] = {
                    "was_sha": stamped, "now_sha": now, "new_text": sc["falsifier"]}
            elif not stamped:
                t["falsifier"] = sc["falsifier"]
                n += 1
        for field in ("ship_audit", "defects", "suite", "deploy"):
            if field in sc:
                t[field] = sc[field]
                n += 1
    bp.write_text(json.dumps(batch, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8")
    print(f"refreshed {n} judgement field(s) in {bp} from {a.scenarios}")
    return 0


def recompute_progress(ledger: dict) -> dict:
    """🔴 EVERY COUNTER IN `progress` IS DERIVED HERE, OR IT DOES NOT BELONG IN `progress`.

    Measured 2026-08-22, after the deep-dive closed at 198/198: SEVEN fields of the `progress`
    block disagreed with the ledger's own rows, and a reader opening the file saw **40 of 198**.

        concluded_in_release_surface  40   rows say 198
        remaining_in_release_surface 158   rows say 0
        last_batch            batch-17     evidence on disk goes to batch 41
        evidence_split.gate_backed    62   rows say 173
        evidence_split.prose_note     30   rows say 25
        defects_proven                23   defects say 25
        deferred_questions             7   there are 12

    The block's own text claims it "is now RECOMPUTED from this ledger's own rows" — which was
    true of the five counters the previous fix covered and false of these seven, because the
    recompute was an inline `pr.update({...})` inside `_record` that listed the fields it happened
    to care about. A partial recompute that advertises itself as total is worse than no recompute:
    the stale half is now stamped as derived.

    THE INVARIANT, and why it is a function rather than a longer literal: there is ONE place that
    knows what `progress` means, both `_record` (which writes it) and `cmd_audit` (which refuses
    when it drifts) call it, and a field that cannot be derived from the rows must not be a
    counter here at all. `_note`, `_stale_block_note` and `_numerator_note` are prose and are left
    exactly as they are.

    WHAT IT DOES NOT FIX: nothing checks that a `state` in a row is TRUE about the tool. This
    guards the arithmetic between the rows and the headline, not the honesty of a row.
    """
    tools = ledger["tools"]
    defects = ledger.get("defects") or {}
    den = ledger.get("denominator") or {}

    # A DEPRECATED tool (visibility=legacy ∪ superseded_by) is not part of what ships. The five
    # already-concluded rows the denominator correction moved out keep their evidence and carry
    # `counts_toward_release: false`, because the work happened and is still true about those
    # tools — but they are not the numerator. Counting them read 114/198 where the shippable
    # figure was 109/198, which is this same class one level down: a number not derived from the
    # SSOT drifts toward "done".
    def counts(v: dict) -> bool:
        return v.get("counts_toward_release") is not False

    live_items = [(t, v) for t, v in tools.items() if counts(v)]
    live = [v for _, v in live_items]
    concluded = sum(1 for v in live if v.get("state") in TERMINAL)
    surface = den.get("federated_tools")

    # `last_batch` from the evidence actually on disk, not from whoever last remembered to type
    # it. Both naming conventions are in use — `batch40.json` and `b41-norail.json` — and an
    # anchored `batch(\d+)` silently stopped at 40 while four batch-41 files sat beside it.
    best = (-1, "")
    for v in tools.values():
        f = v.get("evidence_file") or ""
        m = re.search(r"/(?:batch|b)(\d+)", f)
        if m and int(m.group(1)) > best[0]:
            best = (int(m.group(1)), f)
    last_batch = ledger.get("progress", {}).get("last_batch")
    if best[0] >= 0:
        parts = best[1].split("/")
        date = parts[-2] if len(parts) > 1 else ""
        last_batch = f"batch-{best[0]} ({date})" if date else f"batch-{best[0]}"

    # 🔴 A COUNTER MUST NEVER PARSE ENGLISH. This read `state or status` and classified the result
    # with `startswith`. `status` is free prose — 104 of 156 rows carried only that field, median
    # 89 characters, max 311 — and it is conventionally written in capitals ("OPEN — measured
    # 2026-08-23"). `startswith("open")` matched none of them, so 57 open defects fell into
    # `defects_other` and the headline read 14 open against an actual 71. The remainder bucket is
    # what made it survivable: a row that matched nothing was absorbed instead of noticed.
    #
    # So `state` is now the ONLY field consulted and it is a CLOSED set. An unrecognised or
    # missing state RAISES. There is deliberately no `defects_other` to fall into.
    by_state = {s: 0 for s in DEFECT_STATES}
    for name, d in defects.items():
        s = d.get("state") if isinstance(d, dict) else None
        if s not in by_state:
            raise ValueError(
                f"defect {name!r} has state {s!r}, which is not one of {DEFECT_STATES}. "
                "Give it one — a row the counter cannot classify must never be silently absorbed."
            )
        by_state[s] += 1
    return {
        "tools_declared": sum((den.get("group_sizes") or {}).values()) or None,
        "tools_concluded": concluded,
        "tools_in_cycle": sum(1 for v in tools.values() if v.get("state") == "in_cycle"),
        "tools_proven": sum(1 for v in live if v.get("state") == "proven"),
        "tools_blocked": sum(1 for v in live if v.get("state") == "blocked"),
        # Every state in the closed set gets its own key, so the buckets SUM to the total by
        # construction and no row can hide in a remainder. `defects_other` is gone on purpose.
        **{f"defects_{s}": n for s, n in by_state.items()},
        "defects_total": len(defects),
        "deferred_questions": len(ledger.get("deferred_questions") or {}),
        "last_batch": last_batch,
        "release_surface": surface,
        "shippable_denominator": surface,
        "concluded_in_release_surface": concluded,
        "remaining_in_release_surface": (surface - concluded) if surface is not None else None,
        # DERIVED from whether the row cites a re-checkable file, never from the label it wrote
        # about itself. See is_gate_backed() for what trusting the label cost.
        "evidence_split": {
            **(ledger.get("progress", {}).get("evidence_split") or {}),
            "gate_backed": sum(1 for t, v in live_items if is_gate_backed(t, v)),
            "prose_note_pre_gate": sum(
                1 for t, v in live_items
                if v.get("state") in TERMINAL and not is_gate_backed(t, v)),
        },
        "tools_concluded_including_deprecated": sum(
            1 for v in tools.values() if v.get("state") in TERMINAL),
    }


#: Counters that USED to be derived and no longer are. `.update()` cannot remove a key, so a
#: retired one would sit in the block forever reading whatever it last held — and `defects_other`
#: is precisely the remainder bucket that hid 57 open defects. A counter that stops being derived
#: must stop being stored.
RETIRED_PROGRESS_KEYS = ("defects_other",)


def apply_progress(ledger: dict) -> None:
    """Write every derived counter back into `progress`, and drop the retired ones.

    NOT CHECKED HERE: that no OTHER hand-typed key is loitering in the block. The three `_note`
    fields legitimately are prose, so a blanket "unknown key" rule would need them classified
    first. Named rather than silently skipped.
    """
    ledger["progress"].update(recompute_progress(ledger))
    for retired in RETIRED_PROGRESS_KEYS:
        ledger["progress"].pop(retired, None)


def progress_drift(ledger: dict) -> dict:
    """{field: (stored, derived)} for every counter that disagrees. Empty dict = consistent."""
    stored = ledger.get("progress") or {}
    out = {}
    for k, want in recompute_progress(ledger).items():
        if k == "evidence_split":
            for sk, sv in want.items():
                if stored.get(k, {}).get(sk) != sv:
                    out[f"{k}.{sk}"] = (stored.get(k, {}).get(sk), sv)
        elif stored.get(k) != want:
            out[k] = (stored.get(k), want)
    return out


#: The ONE field that marks a defect row as waiting on an owner decision. The generator
#: (`goal_prompt_defects.py`) reads this name and no other: it sorts these last, never points
#: NEXT at one, and `--check` ends the whole run when every open contract row carries it.
DQ_FIELD = "blocked_by_dq"

#: Names that MEAN the same thing and are not it. `dq` is not hypothetical — see below.
DQ_ALIASES = ("dq", "dq_blocked", "blocked_by", "deferred_question")


def dq_alias_drift(ledger: dict) -> dict:
    """{row: [alias, ...]} for every defect marked blocked under a name the generator cannot see.

    🔴 A SECOND NAME FOR THE SAME CONCEPT SILENTLY DISABLED THE RESUME POINTER. Measured
    2026-08-26: five OPEN rows carried `dq` (DQ-T31, T44, T45, T46, T47) while seven carried
    `blocked_by_dq`, and the generator reads only the latter. So the queue offered rows whose
    next step is an owner decision as if they were actionable — it pointed NEXT at
    D-RESTORE-WITH-NO-WAY-TO-SEE-WHAT-IS-RESTORABLE, blocked on DQ-T44, and every row it
    displayed was blocked while seven unblocked ones existed and had to be derived by hand.

    Worse, `--check` ENDS THE RUN when everything left is blocked. Under-counting blocked rows
    means the stop condition cannot be reached honestly: the run is told to keep going by an
    instrument that cannot see the blocks. The count and the pointer are the two things this
    loop steers by, and one typo'd field name broke both.

    This is the same question `progress_drift` asks — does the ledger agree with itself? — so
    it is answered in the same place, and an alias FAILS the audit rather than being migrated
    silently: a row rewritten by a tool is a row nobody re-read.
    """
    out = {}
    for name, row in (ledger.get("defects") or {}).items():
        if not isinstance(row, dict):
            continue
        found = [f for f in DQ_ALIASES if row.get(f)]
        if found:
            out[name] = found
    return out


#: A deferred question is in exactly one of these. Prose belongs in `state_note`.
DQ_STATES = ("open", "answered", "withdrawn")


def dq_state_drift(ledger: dict) -> dict:
    """{dq: what_is_wrong} for every deferred question whose state is not a readable token.

    🔴 THE SAME DISEASE AS dq_alias_drift, ONE BLOCK OVER — and that row said this block was
    NOT checked. Censused 2026-08-26: of 25 questions, 18 carried `state`, 3 carried `status`,
    5 carried NEITHER, and `state` was not a token at all — one held an entire paragraph,
    another the phrase 'recommend withdrawn — pending owner'.

    It matters because `blocked_by_dq` is only half a link. A defect row points at a question,
    and whether that row is ACTIONABLE depends on whether the question is still open. Seven
    questions had no machine-readable state, so anything reading one saw nothing.

    🔴 AND TRANSCRIBING THEM ALMOST WENT WRONG IN THE OBVIOUS WAY. A first pass tested
    `"ANSWERED" in status.upper()` before the open branch, and DQ-T31's status reads
    "OPEN — product decision, recorded per the RUNBOOK rather than answered" — so an OPEN
    product decision was marked ANSWERED. That question BLOCKS THREE contract defects; the
    wrong token would have presented all three as ready to work on a decision the owner never
    made. A substring is not a state, which is exactly why the state has to be a token.
    """
    out = {}
    for name, dq in (ledger.get("deferred_questions") or {}).items():
        if not isinstance(dq, dict):
            continue
        st = dq.get("state")
        if st is None:
            out[name] = "no `state` at all — unreadable to anything deciding if it is settled"
        elif st not in DQ_STATES:
            out[name] = f"state is prose, not one of {DQ_STATES}: {str(st)[:60]!r}"
    return out


#: The word a `status` line opens with, mapped to the states it CONTRADICTS. A status is prose
#: and may say anything after its first word; what it may not do is open by asserting a
#: disposition the row does not have.
_STATUS_LEAD_CONTRADICTS = {
    "OPEN": {"fixed", "proven", "withdrawn", "superseded"},
    "BLOCKED": {"fixed", "proven"},
    "FIXED": {"open"},
    "PROVEN": {"open"},
    "CLOSED": {"open"},
    "DONE": {"open"},
    "WITHDRAWN": {"open", "fixed", "proven"},
}


def stale_dq_blocks(ledger: dict) -> dict:
    """{defect: (dq, its_state)} for every OPEN row blocked on a question that is NO LONGER OPEN.

    🔴 THE HALF `dangling_dq_links` DOES NOT ASK. That check catches a row pointing at a question
    nobody registered; this one catches a row pointing at a question that WAS registered and has
    since been answered or withdrawn. Both leave the row mis-filed, but in opposite directions:
    a dangling link makes a row unblockable forever, a stale block makes an ACTIONABLE row look
    like it is waiting on the owner — so the queue hides work that is ready, and `--check` can
    report "everything left is blocked" while real work sits behind a closed question.

    That is the stop condition failing silently, which is the one failure this whole instrument
    exists to prevent. Measured clean on 2026-08-30 (0 stale blocks across 14 blocked rows), and
    checked from now on so it stays that way rather than being re-derived by hand each time.

    Scoped to OPEN rows on purpose: a FIXED row may legitimately keep the `blocked_by_dq` it
    carried while it was open, as part of its history.
    """
    dqs = ledger.get("deferred_questions") or {}
    out = {}
    for name, row in (ledger.get("defects") or {}).items():
        if not isinstance(row, dict) or row.get("state") != "open":
            continue
        ref = row.get(DQ_FIELD)
        if not ref or ref not in dqs:
            continue  # unregistered is dangling_dq_links' question, not this one
        st = (dqs[ref] or {}).get("state")
        if st != "open":
            out[name] = (ref, st)
    return out


#: A cited evidence file, matched as a WHOLE path with no internal separator in the filename.
#: Deliberately strict: a row legitimately writes shorthand for a set of files
#: ("…/c-motiflink10/11/15/16/17/18.json"), which is prose about six batches and not a path, and
#: a looser pattern reports it as one missing file every single run — an instrument crying wolf
#: is one people learn to skip.
_EVIDENCE_PATH = re.compile(r"docs/eval/toolloop/[\w.\-]+/[\w.\-]+\.json")


def missing_evidence_paths(ledger: dict) -> dict:
    """{defect: [path, ...]} for every row citing an evidence file that is not on disk.

    🔴 A ROW WHOSE EVIDENCE CANNOT BE OPENED CANNOT BE RE-CHECKED, and this loop's standing rule
    is that a ledger claim is a lead rather than a fact. Found 2026-08-30 by hand:
    D-FIXTURE-NAME-IS-THE-MOST-PLAUSIBLE-LOOKING-ID cites a batch from nine days BEFORE the
    measurement it is offered as evidence for — and that batch never calls the tool the row names
    and records the model doing the right thing 5/5. The claim may still be true; nobody can tell.

    This catches the ABSENT file, which is the cheap half. It cannot catch a path that exists but
    does not contain the instance the row describes — that one needs a reader, and it is why the
    finding above took a person rather than a check.
    """
    out: dict[str, list[str]] = {}
    for name, row in (ledger.get("defects") or {}).items():
        if not isinstance(row, dict):
            continue
        blob = "\n".join(str(v) for v in row.values())
        gone = sorted({m for m in _EVIDENCE_PATH.findall(blob)
                       if not (ROOT / m).exists()})
        if gone:
            out[name] = gone
    return out


def status_state_drift(ledger: dict) -> dict:
    """{defect: what_is_wrong} for every row whose `status` prose contradicts its `state`.

    🔴 FOUND 2026-08-27 BY A READER GETTING IT WRONG, which is the only way this kind of drift
    ever surfaces. A stop hook read the ledger and reported three CONTRACT defects as open and
    actionable — `D-A-REQUIRED-ARGUMENT-ONLY-THE-AUTHOR-CAN-SUPPLY-HAS-NO-ASK-PATH`,
    `D-A-REQUIRED-ID-NO-TOOL-CAN-SUPPLY`, `D-KG-BUILD-TAKES-A-PROJECT-ID-…`. All three carry
    `state: fixed`. All three OPEN THEIR `status` WITH THE WORD "OPEN", because that line was
    written when the row was filed and never rewritten when it was closed; the real disposition
    went into `state_reason` instead.

    Seven rows were in that condition. `state` is the machine-readable field and every derived
    count already reads it, so no number was wrong — what was wrong is that the FIRST LINE A
    HUMAN READS said the opposite of the row, and a reader who trusts prose over a field is not
    being careless, they are reading the part written for them.

    The status is NOT rewritten by this check. A row edited by a tool is a row nobody re-read,
    which is the rule `dq_alias_drift` states one block up."""
    out = {}
    for name, row in (ledger.get("defects") or {}).items():
        if not isinstance(row, dict):
            continue
        state = str(row.get("state") or "").strip().lower()
        text = str(row.get("status") or "").lstrip()
        if not state or not text:
            continue
        lead = text.split()[0].strip("—-:,.–").upper()
        if state in _STATUS_LEAD_CONTRADICTS.get(lead, set()):
            out[name] = f"state={state!r} but `status` opens with {lead!r}"
    return out


def dangling_dq_links(ledger: dict) -> dict:
    """{defect: dq} for every row blocked by a question that is not registered.

    A row blocked on a question nobody wrote down can never be unblocked, and the owner has
    nothing to decide. It also silently shrinks the actionable queue.
    """
    dqs = ledger.get("deferred_questions") or {}
    out = {}
    for name, row in (ledger.get("defects") or {}).items():
        if not isinstance(row, dict):
            continue
        ref = row.get(DQ_FIELD)
        if ref and ref not in dqs:
            out[name] = ref
    return out


def _record(a, path: pathlib.Path, row: dict, reason: str) -> None:
    """🔴 THE GATE USED TO SAY "may be recorded" AND WRITE NOTHING.

    Measured 2026-08-14: batch 14 passed all five of its per-tool decisions, I read "gate PASSED"
    as the end of the step, and no ledger row was ever written. `scengen.py --next` then re-derived
    the SAME five tools as the next batch, which is the only reason it surfaced at all. A sweep of
    every evidence file on disk found exactly those five with evidence and no row, so the seam had
    bitten once — but a passed gate that depends on a human remembering to transcribe it is a
    progress number that drifts silently, which is the defect class this loop exists to remove.

    THE INVARIANT: the gate's decision and the ledger are written in ONE step, by the gate. The
    note is assembled from what was MEASURED — counts, store movement, the evidence path — and
    never from prose invented here; judgement still belongs in the batch file, where the gate can
    re-check it.
    """
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    tools = ledger["tools"]
    runs = row.get("runs") or []
    moved = sum(1 for r in runs
                if (r.get("store") or {}).get("before") != (r.get("store") or {}).get("after"))
    prev = tools.get(a.tool, {})
    note = (f"{a.state.upper()} by scripts/toolloop/gate.py against {path.as_posix()}. "
            f"MEASURED: surfaced {row.get('surfaced_count')}/{len(runs)}, "
            f"called {row.get('called_count')}/{len(runs)}, "
            f"suspended-on-card {row.get('suspended_count')}/{len(runs)}, "
            f"owning store moved on {moved}/{len(runs)} run(s). "
            f"ship_audit and falsifier are on file in the same entry.")
    if reason:
        note += f" BLOCKED REASON: {reason}"
    tools[a.tool] = {**prev, "state": a.state, "cycle": ledger.get("progress", {}).get("last_batch"),
                     "note": note, "evidence_file": path.as_posix(),
                     "evidence_class": "gate-backed", "counts_toward_release": True}
    # Every counter, from one place. See recompute_progress() for why it is not an inline literal.
    apply_progress(ledger)
    LEDGER.write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + chr(10), encoding="utf-8")


def cmd_audit(a) -> int:
    """Evidence that exists on disk but has NO ledger row — the seam _record now closes, kept as a
    standing check so the class cannot come back by another route (a hand-edited ledger, a batch
    concluded before this fix, a row deleted in a merge)."""
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    tools = ledger["tools"]
    orphans = {}
    for f in sorted(pathlib.Path("docs/eval/toolloop").rglob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        for e in (d.get("tools") or []):
            if isinstance(e, dict) and e.get("tool") and e["tool"] not in tools:
                orphans.setdefault(e["tool"], f.as_posix())
    # 🔴 THE SECOND SEAM: the rows can be complete while the HEADLINE lies about them.
    # `audit` checked only that evidence on disk has a row. Measured 2026-08-22 with 203 rows and
    # a clean audit, the `progress` block still read `concluded_in_release_surface: 40` against
    # 198 — so "audit clean" was true and the file's own summary was wrong by 158. Both are the
    # same question (does the ledger agree with itself?) and they are now answered together.
    drift = progress_drift(ledger)
    # 🔴 THE THIRD SEAM: the rows can agree with the headline and still be invisible to the
    # thing that STEERS the run. See dq_alias_drift — one row blocked under the wrong field
    # name is a row the queue offers as actionable and the stop condition cannot count.
    aliases = dq_alias_drift(ledger)
    dq_states = dq_state_drift(ledger)
    dangling = dangling_dq_links(ledger)
    status_drift = status_state_drift(ledger)
    stale_blocks = stale_dq_blocks(ledger)
    missing_ev = missing_evidence_paths(ledger)
    if (not orphans and not drift and not aliases and not dq_states and not dangling
            and not status_drift and not stale_blocks and not missing_ev):
        print(f"audit clean — every tool with evidence has a ledger row ({len(tools)} rows), "
              "`progress` agrees with them, and every DQ block is readable by the generator")
        return 0
    if orphans:
        print(f"REFUSED — {len(orphans)} tool(s) have evidence on disk and NO ledger row:")
        for n, f in sorted(orphans.items(), key=lambda x: (x[1], x[0])):
            print(f"  {n:40} {f}")
    if drift:
        print(f"REFUSED — `progress` disagrees with the rows in {len(drift)} field(s). "
              "It is DERIVED; re-run any `conclude`, or fix the rows — never the number:")
        for k, (stored, want) in sorted(drift.items()):
            print(f"  {k:36} stored={stored!r:24} rows say {want!r}")
        # --fix-progress is NOT "edit the gate to make it pass". It recomputes the block FROM the
        # rows, which is the only legitimate repair; nothing here can move a number the rows do
        # not support, and every change it makes is printed above before it is written.
        if getattr(a, "fix_progress", False):
            apply_progress(ledger)
            LEDGER.write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + chr(10),
                              encoding="utf-8")
            print(f"  -> rewrote {len(drift)} field(s) from the rows. Re-run `audit` to confirm.")
    if stale_blocks:
        print(f"REFUSED — {len(stale_blocks)} OPEN row(s) are blocked on a question that is no "
              "longer open. The queue is hiding work that is READY, and `--check` can report "
              "'everything left is blocked' while these sit behind a closed decision:")
        for n, (dq, st) in sorted(stale_blocks.items()):
            print(f"  {n:52} {dq} is {st!r}")
    if missing_ev:
        print(f"REFUSED — {len(missing_ev)} row(s) cite an evidence file that is not on disk. "
              "A claim nobody can re-open is a claim nobody can check:")
        for n, paths in sorted(missing_ev.items()):
            for path in paths:
                print(f"  {n:52} {path}")
    if aliases:
        print(f"REFUSED — {len(aliases)} defect row(s) mark a DQ block under a name the "
              f"generator cannot read. It reads `{DQ_FIELD}` and nothing else, so these rows are "
              "offered as actionable and the run's stop condition cannot count them:")
        for name, found in sorted(aliases.items()):
            print(f"  {name:58} {found}")
        print(f"  -> rename the field to `{DQ_FIELD}` on each row. NOT auto-migrated on purpose: "
              "a row rewritten by a tool is a row nobody re-read.")
    if dangling:
        print(f"REFUSED — {len(dangling)} defect(s) are blocked by a deferred question that is "
              "NOT REGISTERED. Such a row can never be unblocked and the owner has nothing "
              "to decide:")
        for name, ref in sorted(dangling.items()):
            print(f"  {name:58} -> {ref}")
    if dq_states:
        print(f"REFUSED — {len(dq_states)} deferred question(s) have no readable state. "
              f"`blocked_by_dq` is only half a link: whether a blocked defect is ACTIONABLE "
              f"depends on whether its question is still open. State must be one of "
              f"{DQ_STATES}; put prose in `state_note`:")
        for name, why in sorted(dq_states.items()):
            print(f"  {name:12} {why}")
    if status_drift:
        print(f"REFUSED — {len(status_drift)} defect row(s) open their `status` prose with a "
              "disposition the row does not have. Every derived count reads `state`, so no "
              "number is wrong — what is wrong is that the FIRST LINE A HUMAN READS says the "
              "opposite of the row, and a reader who trusts it is reading the part written for "
              "them:")
        for name, why in sorted(status_drift.items()):
            print(f"  {name:58} {why}")
        print("  -> rewrite the LEAD of `status` to match `state`, keeping the original sentence "
              "as the record of what it said when filed. NOT auto-migrated: a row rewritten by a "
              "tool is a row nobody re-read.")
    return 1


def cmd_conclude(a) -> int:
    if a.state not in TERMINAL:
        print(f"'{a.state}' is not terminal. Exactly two words are: {TERMINAL}. "
              "'works', 'tested', 'mostly', 'known issue' and a progress report are not.")
        return 2
    path = pathlib.Path(a.batch)
    batch = json.loads(path.read_text(encoding="utf-8"))
    row = next((t for t in batch.get("tools", []) if t.get("tool") == a.tool), None)
    if row is None:
        print(f"{a.tool} is not in this batch")
        return 4
    g = Gate(batch, path)
    g.run()
    # 🔴 CONCLUDING TOOL X MUST NOT REQUIRE TOOL Y'S EVIDENCE. This used to gate on the WHOLE
    # batch, so one tool that legitimately cannot be concluded froze every tool beside it —
    # measured 2026-08-14: memory_recall_entity passed all nine of its bars while the batch stayed
    # refused because two OTHER tools were never called. `check` remains whole-batch and strict;
    # only this per-tool decision is scoped to the tool it names.
    mine = [line for line in g.fail if line.startswith(f"[{a.tool}]")]
    if a.state == "blocked":
        # A blocked tool is one the evidence says could NOT be exercised, so demanding the very
        # bars that describe being exercised is circular. What it must never be is a quiet exit:
        # the reason is required, in the batch file, where the gate can read it.
        reason = str(row.get("blocked_reason") or "").strip()
        if len(reason) < 40:
            print("REFUSED — `blocked` needs a `blocked_reason` in the batch entry saying what "
                  "stopped the tool being exercised, in enough words to be checkable later. "
                  "'blocked' with no reason is the progress report this loop forbids.")
            return 1
        excused = ("LIVE called", "SHIP exercised")
        hard = [line for line in mine if not any(e in line for e in excused)]
        if hard:
            print(f"REFUSED — {a.tool} cannot be concluded `blocked` while the TURN itself is "
                  "unproven; these are not excused by being blocked:")
            for line in hard:
                print(f"  FAIL  {line}")
            return 1
        _record(a, path, row, reason)
        print(f"gate PASSED for {a.tool} → RECORDED blocked in the ledger")
        print(f"  reason on file: {reason[:160]}")
        print("  (a blocked tool is NOT progress — it is a tool this platform cannot ship yet)")
        return 0
    if mine:
        print(f"REFUSED — the evidence for {a.tool} is incomplete:")
        for line in mine:
            print(f"  FAIL  {line}")
        return 1
    if not LEDGER.exists():
        print(f"ledger missing: {LEDGER}")
        return 3
    _record(a, path, row, "")
    print(f"gate PASSED for {a.tool} → RECORDED {a.state} in the ledger")
    print("  (the gate proves the EVIDENCE exists; it does not prove the root cause is right)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("batch")
    c.set_defaults(fn=cmd_check)
    r = sub.add_parser("refresh")
    r.add_argument("batch")
    r.add_argument("scenarios")
    r.set_defaults(fn=cmd_refresh)
    d = sub.add_parser("conclude")
    d.add_argument("batch")
    d.add_argument("--tool", required=True)
    d.add_argument("--state", required=True)
    d.set_defaults(fn=cmd_conclude)
    au = sub.add_parser("audit")
    au.add_argument("--fix-progress", action="store_true",
                    help="recompute the `progress` block FROM the rows (never the other way)")
    au.set_defaults(fn=cmd_audit)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
