#!/usr/bin/env python3
"""Write EXERCISED ship-audit results back into a scenario file, citing the evidence.

    python scripts/toolloop/record_ship_exercised.py --dry-run
    python scripts/toolloop/record_ship_exercised.py --apply

🔴 WHY THIS EXISTS AND WHY IT IS NARROW. `gate.py`'s SHIP bar rejects any `ship_audit` value whose
first 40 characters contain one of `owed / not yet / todo / tbd / pending / n/a / later / skip`,
because "a ship_audit is what was EXERCISED" and an aspirational one is how a boundary sweep gets
recorded as done without being run. Cycle 2 exercised its cases — absent, tenancy and empty by
direct MCP probe, the Tier-A gate by the live batch's suspended cards, idempotency by a probe that
provisions and tears down its own fixture — and then left the results BESIDE the ledger instead of
IN it, so the gate correctly went on refusing.

THIS SCRIPT ONLY TRANSCRIBES, and every line it writes names the file the claim rests on. It will
not invent a result: a case with no evidence entry is left exactly as it was, and a case whose
evidence says the measurement was VACUOUS is written as vacuous rather than as a pass. That last
rule is the point — `world_delete`'s idempotency probe reported "STRICTLY IDEMPOTENT" and flagged
its own verdict: the first call changed nothing either, so it measured two no-ops. Transcribing that
as a pass would put a false green in a contract.

It is deliberately not part of the runner. Evidence should be written once, by hand, with the file
that backs it named in the sentence — not generated as a side effect of the run it is meant to
judge.
"""
from __future__ import annotations

import argparse
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCEN = ROOT / "scripts" / "toolloop" / "scenarios-c2-rerun.json"

E_SHIP = "docs/eval/toolloop/2026-08-14/c2-ship-probe.txt"
E_OPD = "docs/eval/toolloop/2026-08-14/c2-ship-probe-opdispatch.txt"
E_IDEM = "docs/eval/toolloop/2026-08-14/c2-idem.json"
E_RUN = "docs/eval/toolloop/2026-08-14/c2-arc.json"
E_IDEM2 = "docs/eval/toolloop/2026-08-14/c2-idem2.json"
E_IDEM3 = "docs/eval/toolloop/2026-08-14/c2-idem3.txt"   # the probe crashed before
#: writing JSON, so the terminal output is preserved instead — a citation must point at
#: something that exists.
E_IDEM4 = "docs/eval/toolloop/2026-08-14/c2-idem4.json"

#: scenario id -> {case: exercised sentence}. Absent keys are LEFT ALONE.
RECORD: dict[str, dict[str, str]] = {
    "world-delete": {
        "absent_case": f"EXERCISED by direct probe ({E_SHIP}): an absent world_id is refused with "
                       "'world not found — check the world_id (call world_list for valid ids)'.",
        "tenancy": f"EXERCISED by direct probe ({E_SHIP}): another owner's id is refused "
                   "IDENTICALLY to an absent one, so the refusal is no existence oracle.",
        "gate": f"EXERCISED live ({E_RUN}): called 4/5, left SUSPENDED on a Tier-A approval card on "
                "3 of 5 runs, and the store is UNCHANGED across all five. The card was never "
                "approved — this is a HARD delete.",
        "idempotency": f"EXERCISED and PASSED ({E_IDEM2}), on the SECOND attempt. The first was "
                       f"vacuous ({E_IDEM}) — _world_counts never counted the `worlds` table, so a "
                       "real delete produced an empty diff and the probe refused to call that a "
                       "pass. After f9d6a7c10 the same probe shows loreweave_book.worlds rows=1 -> "
                       "null on the first call and {} on the second, which refuses. The first call "
                       "MOVES the store, so the second call's no-op means something.",
    },
    "world-map-delete": {
        "absent_case": f"EXERCISED by direct probe ({E_SHIP}): an absent map_id is refused with "
                       "'map not found — check the map_id (call world_map_list for valid ids)'.",
        "tenancy": f"EXERCISED by direct probe ({E_SHIP}): a foreign id is refused IDENTICALLY to "
                   "an absent one.",
        "gate": f"EXERCISED live ({E_RUN}): the tool was called 5/5 through the chat path.",
        "idempotency": f"EXERCISED and PASSED ({E_IDEM}): first call moved loreweave_book."
                       "world_maps from 2 rows to 1; the second call refused and touched nothing. "
                       "The verdict comes from the STORE, not from the tool's two responses.",
    },
    "composition-arc-template-edit": {
        "gate": f"EXERCISED live ({E_RUN}): called 5/5 with the store UNCHANGED across all five "
                "runs, so a confirm token was minted and nothing was archived without approval.",
        "idempotency": f"NOT PROVEN, and blocked on a NAMED cause rather than unrun "
                       f"({E_IDEM3}): D-DATA-BAR-BLIND-TO-ACCOUNT-SCOPED-ARC-TEMPLATE. The probe "
                       "archived a real template — verified active -> archived by direct SQL — and "
                       "store_diff was {} on BOTH calls, because arc_template's book_id is NULL on "
                       "51 of 57 rows and the snapshot sweeps by book_id. The tool's own responses "
                       "were correct (already_archived false, then true); it is the STORE claim "
                       "that cannot be made. Do not read this as a pass.",
        "absent_case": f"EXERCISED by targeted probe ({E_OPD}). The generic sweep could NOT reach "
                       "this: the tool's only required argument is `op`, so all three of its cases "
                       "landed on the op-dispatch refusal and never touched arc_id. Re-probed with "
                       "op=archive + an absent arc_id: refused, 'not found or not accessible'.",
        "tenancy": f"EXERCISED by targeted probe ({E_OPD}): a foreign arc_id refuses IDENTICALLY "
                   "to an absent one.",
    },
    "composition-motif-link-edit": {
        "absent_case": f"EXERCISED by targeted probe ({E_OPD}), for the same op-dispatch reason: "
                       "op=create with absent from/to motif ids is refused 'not found or not "
                       "accessible'.",
        "tenancy": f"EXERCISED by targeted probe ({E_OPD}): foreign ids refuse IDENTICALLY.",
        "gate": f"EXERCISED live ({E_RUN}): called 4/5, left SUSPENDED on a Tier-A approval card on "
                "2 of 5 runs, store unchanged.",
    },
    "composition-authoring-run-review": {
        "tenancy": f"EXERCISED by direct probe ({E_SHIP}): another account's run_id is refused "
                   "'not found or not accessible', identical to an absent one.",
        "gate": f"EXERCISED live ({E_RUN}): called 5/5, left SUSPENDED on a Tier-A approval card on "
                "3 of 5 runs, store unchanged.",
    },
    "composition-generate": {
        "absent_case": f"EXERCISED by direct probe ({E_SHIP}): an absent project_id is refused "
                       "'not found or not accessible'.",
        "tenancy": f"EXERCISED by direct probe ({E_SHIP}): a foreign project_id refuses "
                   "IDENTICALLY to an absent one.",
    },
    "glossary-entity-restore": {
        "idempotency": f"EXERCISED and PASSED ({E_IDEM4}): first call {{restored: true}} and "
                       "loreweave_glossary.glossary_entities moves (its `latest` advances); second "
                       "call {{restored: false}} and the store is untouched. book_id had to be "
                       "passed explicitly — chat-service injects it from the ambient book and a "
                       "direct MCP call has none, which the tool correctly refused first.",
        "absent_case": f"EXERCISED by direct probe ({E_SHIP}): an absent entity_id is refused "
                       "'book not accessible'.",
        "tenancy": f"EXERCISED by direct probe ({E_SHIP}): a foreign entity_id refuses IDENTICALLY.",
        "gate": f"EXERCISED live ({E_RUN}): the tool was called 5/5 through the chat path.",
    },
    "world-map-create": {
        "absent_case": f"EXERCISED by direct probe ({E_SHIP}): an absent world_id is refused "
                       "'world not found — check the world_id (call world_list for valid ids)'.",
        "tenancy": f"EXERCISED by direct probe ({E_SHIP}): a foreign world_id refuses IDENTICALLY.",
        "gate": f"EXERCISED live ({E_RUN}): the tool was called 5/5 through the chat path.",
    },
}

OWED_WORDS = ("owed", "not yet", "todo", "tbd", "pending", "n/a", "later", "skip")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the file")
    a = ap.parse_args()

    d = json.loads(SCEN.read_text(encoding="utf-8"))
    changed = 0
    still_owed: list[str] = []
    for s in d["scenarios"]:
        rec = RECORD.get(s["id"]) or {}
        audit = s.get("ship_audit") or {}
        for case, value in list(audit.items()):
            new = rec.get(case)
            if new and isinstance(value, str) and any(
                    w in value.lower()[:40] for w in OWED_WORDS):
                audit[case] = new
                changed += 1
                print(f"  {s['id']:34} {case:12} <- {new[:76]}")
        for case, value in audit.items():
            if isinstance(value, str) and any(w in value.lower()[:40] for w in OWED_WORDS):
                still_owed.append(f"{s['id']}.{case}")

    print(f"\n{changed} case(s) transcribed from evidence")
    if still_owed:
        print(f"{len(still_owed)} case(s) STILL OWED — no evidence exists, left untouched:")
        for x in still_owed:
            print(f"  {x}")
    if a.apply:
        SCEN.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nwrote {SCEN}")
    else:
        print("\n(dry run — pass --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
