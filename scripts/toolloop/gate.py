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
import pathlib
import sys

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
        snap = t.get("store") or {}
        has_both = bool(snap.get("before")) and bool(snap.get("after"))
        self._check(has_both, f"[{t['tool']}] DATA snapshots",
                    "need the owning store BEFORE and AFTER; the tool's own response is not "
                    "evidence of what it wrote")
        self._check(bool(t.get("falsifier")), f"[{t['tool']}] DATA falsifier",
                    "state explicitly what result would REFUTE this conclusion")
        if has_both and t.get("intent") == "read":
            diff = snap["before"] != snap["after"]
            self._check(
                not diff, f"[{t['tool']}] DATA read-is-read",
                "the owning store CHANGED on a read-intent turn — that is a defect whatever the "
                "model said (measured 2026-08-13: 3 outline rows became 6)")

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

    def ship(self, t: dict) -> None:
        self._check(bool(t.get("ship_audit")), f"[{t['tool']}] SHIP audit",
                    "record the refusal/gate/empty-case sweep, not just the happy path")

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
    d = sub.add_parser("conclude")
    d.add_argument("batch")
    d.add_argument("--tool", required=True)
    d.add_argument("--state", required=True)
    d.set_defaults(fn=cmd_conclude)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
