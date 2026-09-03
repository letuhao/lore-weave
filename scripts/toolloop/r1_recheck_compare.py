"""Did D-SURFACING-IS-NECESSARY-BUT-NOT-SUFFICIENT's per-tool premises move?

THE ROW'S OWN CAUTION, 2026-08-31: "three neighbouring rows had their premises move under them
this week, one inverting completely. Whatever is chosen, the four other tools this row names
should be re-measured before anything is built for them -- this cycle only re-ran the decisive
one."

This compares a fresh run of the row's OWN batch (scenarios-c-r1-recheck.json) against what the
row records for each tool. Expectations are written HERE, before the numbers are read, so the
comparison cannot be fitted to whatever comes back.

WHAT THE ROW CLAIMS, per tool -- "All six are STILL called 0/5":

    composition_entity_override_edit   0/5, lost to glossary_entity_set_attributes
    composition_generate               0/5, lost to book_chapter_save_draft
    composition_build_cast_and_graph   REATTRIBUTED -- the model does the mandated prerequisite
                                       (categories before cast); not a sibling pick
    glossary_propose_batch             0/5, THE DECISIVE CASE, re-run 2026-08-30 and it held
    plan_bootstrap_apply               REMOVED from the list -- its supplier was never on the
                                       wire; that is a different defect
    tool_load                          0/5, lost to glossary_book_ontology_read

A TOOL THAT IS NOW CALLED IS A MOVED PREMISE, not a fixed defect: this row's claim is that
surfacing is necessary and not sufficient, so a tool that starts being called weakens the row's
population by one and must be recorded as such rather than celebrated.

🔴 THIS FILE'S FIRST VERSION PRINTED "NO PREMISE MOVED" WHILE READING ZERO ROWS, and the runner's
own summary said the opposite on the same file. It assumed two field names the raw records do not
use -- `tool_under_test` (the records carry a `scenario` id) and `tool` inside tool_calls (they
carry `toolCallName`) -- so every lookup missed, every tool reported "NOT IN THIS BATCH", and the
verdict was rendered over nothing. The non-vacuity guard below exists because of that: a
comparison that matched no run must ABORT, never conclude.

Reads a raw batch file. Writes nothing.
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

#: scenario id in the batch file -> the tool that scenario measures.
SCENARIO_TOOL = {
    "composition-entity-override-edit-namefix": "composition_entity_override_edit",
    "composition-generate": "composition_generate",
    "composition-glossary-build": "composition_build_cast_and_graph",
    "glossary-propose-batch": "glossary_propose_batch",
    "plan-bootstrap-apply": "plan_bootstrap_apply",
    "tool-load": "tool_load",
}

#: tool -> (what the row records, is it still part of the row's population)
CLAIM = {
    "composition_entity_override_edit": ("0/5, lost to glossary_entity_set_attributes", True),
    "composition_generate": ("0/5, lost to book_chapter_save_draft", True),
    "composition_build_cast_and_graph": ("REATTRIBUTED (prerequisite, not sibling pick)", False),
    "glossary_propose_batch": ("0/5, THE DECISIVE CASE", True),
    "plan_bootstrap_apply": ("REMOVED (supplier never on the wire)", False),
    "tool_load": ("0/5, lost to glossary_book_ontology_read", True),
}


def called_names(run: dict) -> list[str]:
    """Tool names actually invoked. The raw records use `toolCallName` on TOOL_CALL_START
    events; `tool` is the shape the CHAT STORE uses and is not what is on disk here."""
    out = []
    for c in run.get("tool_calls") or []:
        if not isinstance(c, dict):
            continue
        n = c.get("toolCallName") or c.get("tool")
        if n:
            out.append(n)
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: r1_recheck_compare.py <raw.json>")
        return 2
    path = pathlib.Path(sys.argv[1])
    if not path.exists():
        print(f"{path} does not exist -- the batch has not landed yet.")
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    runs = data if isinstance(data, list) else data.get("runs") or []

    called, total, errs = collections.Counter(), collections.Counter(), collections.Counter()
    others = collections.defaultdict(collections.Counter)

    for r in runs:
        if not isinstance(r, dict):
            continue
        tut = SCENARIO_TOOL.get(r.get("scenario"))
        if not tut:
            continue
        total[tut] += 1
        errs[tut] += bool(r.get("error"))
        names = called_names(r)
        if tut in names:
            called[tut] += 1
        for n in names:
            if n != tut:
                others[tut][n] += 1

    # NON-VACUITY. Without this the whole comparison renders a verdict over nothing -- which is
    # exactly what the first version of this file did.
    matched = sum(total.values())
    if matched == 0:
        print(f"ABORT, NOT A VERDICT: {len(runs)} runs read and NONE matched a known scenario id. "
              f"The field names this file reads are wrong for this batch, so no conclusion about "
              f"any premise is available. Scenario ids seen: "
              f"{sorted({r.get('scenario') for r in runs if isinstance(r, dict)})}")
        return 1
    print(f"{path.name}: {len(runs)} runs, {matched} matched a known scenario\n")

    moved = []
    for tool, (claim, in_population) in CLAIM.items():
        n, c = total[tool], called[tool]
        if not n:
            print(f"  {tool:34} NOT IN THIS BATCH")
            continue
        top = ", ".join(f"{k}({v})" for k, v in others[tool].most_common(2)) or "-"
        flag = ""
        if in_population and c > 0:
            flag = "   <- MOVED: the row says 0/5"
            moved.append((tool, c, n))
        print(f"  {tool:34} called {c}/{n}  err {errs[tool]}  instead: {top}{flag}")
        print(f"  {'':34} row records: {claim}")

    print("\n" + "=" * 90)
    if moved:
        print("PREMISES MOVED — the row's population shrinks and must say so:")
        for t, c, n in moved:
            print(f"    {t}: now called {c} of {n}, recorded as 0/5")
        print("  A tool that is now called does NOT vindicate the row; it removes an instance "
              "from it. Record before anything is built on the old count.")
    else:
        print("NO PREMISE MOVED: every tool the row still claims is called 0/N, as recorded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
