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
        self._check(not errs, f"[{t['tool']}] LIVE clean",
                    f"{len(errs)} run(s) errored; a transport failure is not a model result")
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
        self._check(
            called >= 1, f"[{t['tool']}] LIVE called ({called}/{len(runs)})",
            "the tool under test was never invoked on any run — the model answered by another "
            "route, so nothing here is evidence about THIS tool")

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
        self._check(bool(t.get("falsifier")), f"[{t['tool']}] DATA falsifier",
                    "state explicitly what result would REFUTE this conclusion")
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
            _QUEUES = ("loreweave_knowledge.extraction_pending",)

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
    OWED = ("owed", "not yet", "todo", "tbd", "pending", "n/a", "later", "skip")

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

    live = [v for v in tools.values() if counts(v)]
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

    def defect_state(d) -> str:
        return str((d.get("state") or d.get("status") or "") if isinstance(d, dict) else "")

    proven_d = sum(1 for d in defects.values() if defect_state(d).startswith("proven"))
    open_d = sum(1 for d in defects.values() if defect_state(d).startswith("open"))
    return {
        "tools_declared": sum((den.get("group_sizes") or {}).values()) or None,
        "tools_concluded": concluded,
        "tools_in_cycle": sum(1 for v in tools.values() if v.get("state") == "in_cycle"),
        "tools_proven": sum(1 for v in live if v.get("state") == "proven"),
        "tools_blocked": sum(1 for v in live if v.get("state") == "blocked"),
        "defects_proven": proven_d,
        "defects_open": open_d,
        # Neither counter above claims the total, so the difference is stated rather than lost.
        # Three of these rows are shipped invariant fixes recorded with `commit`/`test` and no
        # `state` at all — a shape the two counters would silently drop.
        "defects_total": len(defects),
        "defects_other": len(defects) - proven_d - open_d,
        "deferred_questions": len(ledger.get("deferred_questions") or {}),
        "last_batch": last_batch,
        "release_surface": surface,
        "shippable_denominator": surface,
        "concluded_in_release_surface": concluded,
        "remaining_in_release_surface": (surface - concluded) if surface is not None else None,
        "evidence_split": {
            **(ledger.get("progress", {}).get("evidence_split") or {}),
            "gate_backed": sum(1 for v in live if v.get("evidence_class") == "gate-backed"),
            "prose_note_pre_gate": sum(
                1 for v in live
                if v.get("state") in TERMINAL and v.get("evidence_class") != "gate-backed"),
        },
        "tools_concluded_including_deprecated": sum(
            1 for v in tools.values() if v.get("state") in TERMINAL),
    }


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
    ledger["progress"].update(recompute_progress(ledger))
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
    if not orphans and not drift:
        print(f"audit clean — every tool with evidence has a ledger row ({len(tools)} rows), "
              "and `progress` agrees with them")
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
            ledger["progress"].update(recompute_progress(ledger))
            LEDGER.write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + chr(10),
                              encoding="utf-8")
            print(f"  -> rewrote {len(drift)} field(s) from the rows. Re-run `audit` to confirm.")
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
