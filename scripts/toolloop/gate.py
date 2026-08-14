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
        exp = t.get("answer_expect") or {}
        if exp:
            must = [str(x).lower() for x in (exp.get("must_contain") or [])]
            mustnt = [str(x).lower() for x in (exp.get("must_not_contain") or [])]
            bad = []
            for r in runs:
                a = str(r.get("answer") or "").lower()
                if not a:
                    continue
                miss = [m for m in must if m not in a]
                hit = [m for m in mustnt if m in a]
                if miss or hit:
                    bad.append((r.get("rep"), miss, hit))
            self._check(
                not bad, f"[{t['tool']}] DATA answer is true",
                f"{len(bad)} of {len(runs)} replies failed the declared expectation "
                f"{bad[:3]} — a read that wrote nothing can still be confidently wrong, and "
                "that is the failure this loop has now seen in both directions")
        if with_both and t.get("intent") == "read":
            wrote = [i for i, p in enumerate(with_both) if p["before"] != p["after"]]
            self._check(
                not wrote, f"[{t['tool']}] DATA read-is-read",
                f"the owning store CHANGED on {len(wrote)} of {len(with_both)} read-intent "
                f"run(s) (rep {wrote}) — that is a defect whatever the model said "
                "(measured 2026-08-13: 3 outline rows became 6)")

    def code(self, t: dict) -> None:
        for d in t.get("defects") or []:
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


def cmd_conclude(a) -> int:
    if a.state not in TERMINAL:
        print(f"'{a.state}' is not terminal. Exactly two words are: {TERMINAL}. "
              "'works', 'tested', 'mostly', 'known issue' and a progress report are not.")
        return 2
    path = pathlib.Path(a.batch)
    batch = json.loads(path.read_text(encoding="utf-8"))
    g = Gate(batch, path)
    if not g.run():
        print("REFUSED — the evidence for this batch is incomplete:")
        for line in g.fail:
            print(f"  FAIL  {line}")
        return 1
    if not LEDGER.exists():
        print(f"ledger missing: {LEDGER}")
        return 3
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    row = next((t for t in batch["tools"] if t["tool"] == a.tool), None)
    if row is None:
        print(f"{a.tool} is not in this batch")
        return 4
    print(f"gate PASSED for {a.tool} → may be recorded {a.state}")
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
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
