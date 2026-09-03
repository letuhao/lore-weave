#!/usr/bin/env python3
"""Derive the resolution loop's runstate from the two contracts. Nothing here is typed.

    python scripts/toolloop/problem_remaining.py            # the headline + the next cycle
    python scripts/toolloop/problem_remaining.py --verbose  # every problem, every tool

The predecessor loop learned this the expensive way: a hand-typed progress number always drifts
toward what was true when someone last remembered to edit it. `contracts/tool-deep-dive-ledger.json`
carried `concluded_in_release_surface: 40` for twenty-four batches while its own rows held 198.

So the ONLY inputs are:
  * contracts/tool-resolution-problems.json  — the frozen problem -> tools partition
  * contracts/tool-deep-dive-ledger.json     — the per-tool state, written by gate.py conclude

and the cycle ORDER is recomputed from the ordering rule on every run rather than read from the
`cycle` field. If the file's stored cycle numbers disagree with the rule, this script says so and
exits non-zero: a denominator you can reorder by editing is not a denominator.
"""
from __future__ import annotations

import argparse
import collections
import re
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROBLEMS = ROOT / "contracts" / "tool-resolution-problems.json"
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"


def order_key(p: dict) -> tuple:
    """The ordering rule, in code. (a) false statements desc, (b) tools desc, (c) id asc."""
    return (-len(p["false_statement_tools"]), -len(p["tools"]), p["id"])


def load() -> tuple[dict, dict]:
    if not PROBLEMS.exists():
        sys.exit(f"missing: {PROBLEMS}")
    if not LEDGER.exists():
        sys.exit(f"missing: {LEDGER}")
    probs = json.loads(PROBLEMS.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    return probs, ledger


def state_of(ledger: dict, tool: str) -> str:
    row = ledger["tools"].get(tool)
    if row is None:
        return "MISSING"
    if row.get("counts_toward_release") is False:
        return "EXCLUDED"
    return row.get("state") or "?"


def open_dqs(ledger: dict) -> list[tuple[str, str]]:
    """Every deferred question that is not answered, READ FROM THE LEDGER.

    🔴 IT USED TO BE A HAND-TYPED LIST in tool-resolution-problems.json
    (`deferred_questions_backlog.registered_open`), last edited 2026-08-22. DQ-T36..T43 were
    opened after that and NONE of them was in it, so the loop's own "check the backlog before you
    stop" printed 10 questions while 16 were open. Three of the missing ones were even filed in
    the same file under `unregistered`, with ledger rows reading `open` beside them.

    A question counts as ANSWERED only when its own state says so. A row with no state at all is
    OPEN — the safe direction, because forgetting to state one must not retire the question.
    """
    out = []
    for k, v in (ledger.get("deferred_questions") or {}).items():
        if not isinstance(v, dict):
            continue
        st = str(v.get("state") or v.get("status") or "").strip()
        head = st.upper()
        if head.startswith(("ANSWERED", "SHIPPED", "CLOSED", "WITHDRAWN")):
            continue
        out.append((k, st.splitlines()[0][:60] if st else "no state recorded — counted OPEN"))
    return sorted(out, key=lambda kv: (len(kv[0]), kv[0]))


def _is_empty(p: dict) -> bool:
    """No tools left — every one moved out on a named cause.

    🔴 0 of 0 SATISFIES `done == n` AND READS AS "CLEARED". P11-DISTRIBUTION emptied on
    2026-08-23 when its last tool moved to P5 on measured cause, and the headline promoted it
    to cleared without a single tool having been proven under it. Emptying a problem is a
    statement about where its tools BELONG, not about whether its invariant holds — P11's own
    open defect (a low-rate tool cannot be proven without sampling for a verdict) outlived the
    tool that surfaced it.
    """
    return not (p.get("tools") or [])


def _field_date(name: str, text: str = "") -> str:
    """The latest YYYY-MM-DD a field's NAME or TEXT carries, or "".

    🔴 THE NAME ALONE WAS NOT ENOUGH, and P8-ANSWERABILITY is why. Its veto lived in `diagnosis`
    -- an UNDATED name whose TEXT opens "BOTH TOOLS READ PROVEN AND THE PROBLEM SAYS OF ITSELF
    THAT IT CANNOT BE CLEARED" and goes on to quote `blocked_on_dq_2026_08_23`. That is a record
    of 2026-08-23, and the only ways to clear the problem were to DELETE it or to rename it --
    both of which destroy or disguise history to satisfy a checker, which the loop's own goal
    forbids in as many words. So the checker reads the date the field itself states.
    """
    # BOTH SEPARATORS. The text usually cites a sibling FIELD NAME, which uses underscores
    # (`blocked_on_dq_2026_08_23`), while prose uses hyphens. Matching only hyphens read
    # P8's `diagnosis` as undated when it names its date in the very sentence that vetoes.
    ds = [d.replace("_", "-") for d in
          re.findall(r"20\d\d[-_]\d\d[-_]\d\d", text or "")]
    m = re.search(r"(20\d\d)[_-](\d\d)[_-](\d\d)", name)
    if m:
        ds.append(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
    return max(ds) if ds else ""


def _status_date(status: str) -> str:
    """The LATEST date the status text carries, or ""."""
    ds = re.findall(r"20\d\d-\d\d-\d\d", status or "")
    return max(ds) if ds else ""


def _definition_complete(p: dict) -> tuple[bool, str]:
    """Does the problem meet the CLEARED definition, beyond its tools reading proven?

    Reads the problem's OWN words first. P8-ANSWERABILITY carries
    `blocked_on_dq_2026_08_23` beginning "P8 CANNOT BE CLEARED WITHOUT DQ-T32" in a field
    that is not `status`, and the headline still called it CLEARED — so scanning only
    `status` would have missed the plainest possible statement that it is not.

    🔴 BUT A DATED FIELD IS A RECORD OF WHEN IT WAS WRITTEN, NOT A CLAIM ABOUT NOW.
    Measured 2026-09-03: P3-NAME-TO-ID reported unmet because `cannot_clear_2026_08_23` still
    contains "CANNOT BE CLEARED" — while its own `status` reads "CLEARED 2026-08-24 — 7 of 7
    proven" and it carries a cleared_note. The blocker named in that field (a tool that could
    not be adjudicated) was resolved the NEXT DAY, and the field was correctly left in place as
    history. A checker that reads a superseded record as a live veto marks finished work open
    forever, and the only way to satisfy it is to DELETE the history — which is the opposite of
    what this ledger is for.

    So a dated field is skipped when the status is strictly newer. Every DQ these problems cite
    (DQ-T31/32/33/35/36/41) was answered by 2026-08-31 while the fields naming them as blockers
    are dated 2026-08-22..24, so this is the general case here, not one row's special pleading.
    An UNDATED field still vetoes: with no date it cannot be shown superseded.
    """
    own = (p.get("status") or "").strip()
    sdate = _status_date(own)
    # 🔴 SUPERSESSION APPLIES ONLY UNDER A STATUS THAT ITSELF CLAIMS CLEARED. Without this gate a
    # merely NEWER status -- including one that says "still blocked" -- would silence a veto, which
    # is the opposite of what the rule is for. A problem that does not claim to be finished can
    # never suppress a field saying it is not.
    _may_supersede = own.upper().startswith(("CLEARED", "FIXED"))
    for key, val in p.items():
        if key in ("tools", "cycle") or not isinstance(val, str):
            continue
        if "CANNOT BE CLEARED" not in val.upper():
            continue
        fdate = _field_date(key, val)
        if _may_supersede and fdate and sdate and sdate > fdate:
            continue  # superseded: the status was written after the state this field records
        return False, f"`{key}` says it CANNOT BE CLEARED: {val.split('.')[0][:80]}"
    if _is_empty(p):
        return False, ("EMPTY — every tool moved out on a named cause; nothing was proven "
                       "under it and its invariant is untouched")
    if own and not own.upper().startswith(("CLEARED", "FIXED")):
        return False, f"its own status says: {own.splitlines()[0][:70]}"
    if not (p.get("cleared_note") or "").strip():
        return False, "no cleared_note — condition (4), what the fix does NOT cover, is unwritten"
    return True, ""


# 🔴 THE VERDICT WAS THE TOOL COUNT AND THE DEFINITION WAS A FOOTNOTE.
# `_definition_complete` was already right and already flagged 13 of 16 — but the headline
# word stayed CLEARED, the summary line read `cleared=16 remaining=0`, and the script signed
# off with "No problem remains. Stopping is legitimate." A loop whose STOP signal is computed
# from a different rule than its own definition will always stop early. So the verdict is now
# derived from the definition, and the count that gets quoted is the honest one.
def verdict(p: dict, done: int, n: int) -> str:
    if done < n:
        return "in_progress"
    if _is_empty(p):
        return "empty"
    return "cleared" if _definition_complete(p)[0] else "tools_proven_invariant_open"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true", help="every problem and every tool")
    a = ap.parse_args()

    probs, ledger = load()
    ordered = sorted(probs["problems"], key=order_key)

    # 🔴 THE PARTITION MUST STAY MECE, AND A DUPLICATE ONCE SLIPPED THROUGH. Moving a tool into a
    # problem that already listed it put `memory_timeline` in P13 twice, and the denominator read
    # 66 where the contract says 65. It was caught because I happened to read the number — which is
    # not a control. The denominator is the one thing in this loop that may never drift, so a tool
    # appearing twice, or vanishing, is a refusal rather than a line in a report.
    seen: dict[str, str] = {}
    dupes: list[str] = []
    for p in probs["problems"]:
        for t in p["tools"]:
            if t in seen:
                dupes.append(f"{t} (in {seen[t]} and {p['id']})")
            seen[t] = p["id"]
    if dupes:
        print("PARTITION IS NOT MECE — a tool appears in more than one problem, so the "
              "denominator is wrong in both directions at once:")
        for d in dupes:
            print(f"  {d}")
        print("Fix the file, not this script.")
        return 2

    # The stored cycle numbers must be the rule's output, not someone's preference.
    stored = [p["id"] for p in sorted(probs["problems"], key=lambda p: p["cycle"])]
    computed = [p["id"] for p in ordered]
    if stored != computed:
        print("ORDERING DRIFT — the stored `cycle` numbers are not what the ordering rule produces.")
        print(f"  stored:   {', '.join(stored)}")
        print(f"  computed: {', '.join(computed)}")
        print("Fix the file, not this script.")
        return 2

    rows = []
    for i, p in enumerate(ordered, 1):
        states = [state_of(ledger, t) for t in p["tools"]]
        done = sum(1 for s in states if s == "proven")
        rows.append((i, p, states, done))

    # 🔴 "CLEARED" MEANT "EVERY TOOL READS PROVEN" AND NOTHING ELSE, WHILE THIS SCRIPT PRINTED A
    # FOUR-PART DEFINITION AT THE BOTTOM THAT IT DID NOT CHECK. Measured 2026-08-23: of the five
    # problems the headline called CLEARED, P12-RAIL-PINNED-TURN's own status field read
    # "DIAGNOSED — the mechanism is named and proven by a control; the FIX is not written", and
    # P13-SILENT-TURN's read "OPEN — recording fixed, ROOT CAUSE IDENTIFIED, cause not fixed".
    # Four of the five carried no `cleared_note` at all, which is condition (4).
    #
    # The tool-completion count is still the right SIGNAL — it is what the denominator rule is
    # written in — so it is kept and shown unchanged. What is added is the second half: whether the
    # problem ALSO satisfies the definition this script has been printing. Where the two disagree
    # the row is flagged, because a problem whose fix was never written is not one to stop on, and
    # the loop's own progress line was the last place that would have said so.
    cleared = [r for r in rows if r[3] == len(r[1]["tools"])]

    verdicts = {p["id"]: verdict(p, done, len(p["tools"])) for _i, p, _s, done in rows}
    by = collections.Counter(verdicts.values())

    unsound = [(r, _definition_complete(r[1])[1]) for r in cleared
               if not _definition_complete(r[1])[0]]
    blocked_tools = sum(len(p["tools"]) for p in probs["problems"])
    proven_tools = sum(r[3] for r in rows)

    print(
        f"problems={len(rows)}  cleared={by['cleared']}  "
        f"TOOLS PROVEN / INVARIANT OPEN={by['tools_proven_invariant_open']}  "
        f"empty={by['empty']}  in_progress={by['in_progress']}  |  "
        f"tools_in_denominator={blocked_tools} proven={proven_tools} "
        f"still_blocked={blocked_tools - proven_tools}"
    )
    # The tool count is still shown, because it is what the denominator rule is written in — but
    # it is no longer the verdict. `cleared` above means the four-part definition, nothing less.
    if unsound:
        print(f"⚠ {len(unsound)} of the {len(cleared)} problem(s) whose TOOLS all read proven do "
              f"NOT meet the definition printed below:")
        for (i, p, _s, _d), why in unsound:
            print(f"    {p['id']:<24} {why}")
    print()

    for i, p, states, done in rows:
        n = len(p["tools"])
        mark = ("EMPTY" if _is_empty(p) else "CLEARED") if done == n else f"{done}/{n}"
        fs = len(p["false_statement_tools"])
        fs_note = f"  [{fs} tool(s) made a FALSE STATEMENT to the author]" if fs else ""
        mark = {"cleared": "CLEARED", "empty": "EMPTY",
                "tools_proven_invariant_open": "TOOLS PROVEN"}.get(verdicts[p["id"]], mark)
        gap = "" if done < n else ("" if _definition_complete(p)[0]
                                   else "  ⚠ TOOLS PROVEN, DEFINITION NOT MET")
        print(f"  C{i:<3} {p['id']:<24} {mark:>8}  {p['title']}{fs_note}{gap}")
        if a.verbose:
            for t, s in sorted(zip(p["tools"], states)):
                print(f"          {s:<9} {t}")
            print()

    nxt = next((r for r in rows if r[3] < len(r[1]["tools"])), None)
    print()
    if nxt is None:
        # 🔴 THIS USED TO SAY "Stopping is legitimate" ON THE TOOL COUNT ALONE, with the twelve
        # unmet problems printed above it as a warning nobody had to act on. A stop signal
        # computed from a different rule than the definition will always stop early.
        print("No problem has a tool left to run — every tool in the denominator reads `proven`.")
        if unsound:
            print()
            print(f"🔴 STOPPING IS NOT YET LEGITIMATE. {len(unsound)} problem(s) have every tool "
                  f"proven and do NOT meet the CLEARED definition. A tool clearing its gate is not "
                  f"an invariant fix, and no further TOOL RUN can close these — each needs its "
                  f"invariant written, enforced at one chokepoint, and a falsifier proven RED:")
            for (_i, p, _s, _d), why in unsound:
                print(f"    {p['id']:<26} {why}")
        else:
            print("Every problem also meets the four-part definition. Stopping is legitimate.")
        print()
        print("DQ backlog, DERIVED from the ledger (never the hand-typed list):")
        for k, why in open_dqs(ledger):
            print(f"  open {k:<8} {why}")
        # 🔴 THE EXIT CODE MUST AGREE WITH THE VERDICT PRINTED DIRECTLY ABOVE IT.
        #
        # This returned 0 unconditionally — so a run that printed "STOPPING IS NOT YET LEGITIMATE"
        # over 13 unmet problems handed back SUCCESS. Measured 2026-09-03: the resolution
        # RUNBOOK carried `STATUS: COMPLETE` while this script refused the stop, and any CI check
        # or `$?` read scored the refusal as a pass. That is the same shape as the two other
        # instruments the same audit found lying by construction (`gate.py`'s name-shaped
        # last_batch, a frozen release_surface yielding a NEGATIVE remainder reported as clean).
        #
        # This is the THIRD time this function's stop signal has been wrong, and the previous two
        # fixes both corrected what it PRINTS while leaving what it RETURNS alone — see the
        # ledger rows at 4812 and 5713. A verdict nobody can act on programmatically is a warning,
        # not a gate.
        return 1 if unsound else 0

    i, p, states, done = nxt
    print(f"NEXT — cycle {i}: {p['id']} — {p['title']}")
    print(f"  invariant candidate: {p['invariant_candidate']}")
    if p.get("status"):
        print(f"  status: {p['status']}")
    outstanding = [t for t, s in zip(p["tools"], states) if s != "proven"]
    print(f"  {len(outstanding)} tool(s) to clear: {', '.join(sorted(outstanding))}")
    print()
    print("  A problem is CLEARED only when:")
    for line in probs["cleared_definition"].split(". ("):
        print(f"    {line.strip().rstrip('.')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
